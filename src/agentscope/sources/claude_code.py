from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from agentscope.domain.model_normalization import normalize_model_name
from agentscope.domain.models import (
    NormalizedMessage,
    NormalizedSession,
    NormalizedTokenUsage,
    NormalizedToolCall,
)
from agentscope.sources.base import (
    CollectRequest,
    DiscoveryContext,
    SourceCapabilities,
    SourceCollectionSummary,
    SourceDiscovery,
)
from agentscope.storage.repository import Repository


_FORMAT_VERSION = "jsonl-v1"
_ALLOWED_RECORD_TYPES = {"user", "assistant"}


class ClaudeCodeAdapter:
    source_name = "claude_code"

    def discover(self, context: DiscoveryContext) -> SourceDiscovery:
        root = context.overrides.get(self.source_name, context.user_home / ".claude")
        projects = root / "projects"
        candidates = tuple(sorted(projects.rglob("*.jsonl"))) if projects.exists() else ()
        supported: list[Path] = []
        unsupported = False
        for path in candidates:
            if _supported_transcript(path):
                supported.append(path)
            else:
                unsupported = True

        if supported:
            return SourceDiscovery(
                source=self.source_name,
                detected=True,
                roots=(root,),
                format_version=_FORMAT_VERSION,
                artifacts=tuple(supported),
                diagnostic=(
                    "Some Claude Code transcripts use an unsupported structure"
                    if unsupported
                    else None
                ),
            )
        return SourceDiscovery(
            source=self.source_name,
            detected=False,
            roots=(root,),
            artifacts=(),
            diagnostic=(
                "Claude Code unsupported transcript structure"
                if candidates
                else "No Claude Code transcripts found"
            ),
        )

    def capabilities(self) -> SourceCapabilities:
        return SourceCapabilities(
            sessions=True,
            messages=True,
            tokens=True,
            cache=True,
            tools=True,
        )

    def collect(self, request: CollectRequest) -> SourceCollectionSummary:
        summary = SourceCollectionSummary()
        repository: Repository = request.repository
        user_id = repository.upsert_user(request.user) if request.user else None
        machine_id = repository.upsert_machine(request.machine) if request.machine else None

        for path in request.discovery.artifacts:
            summary.files_seen += 1
            digest = _hash_file(path)
            if not request.full_rescan and _unchanged(repository, path, digest):
                summary.files_skipped += 1
                continue
            try:
                session_id = _persist_transcript(repository, path)
                if user_id is not None or machine_id is not None:
                    repository.associate_session_identity(session_id, user_id, machine_id)
                _save_state(repository, path, digest)
                summary.files_imported += 1
                summary.sessions_imported += 1
            except Exception as exc:
                summary.errors += 1
                repository.record_import_error(
                    self.source_name,
                    str(path),
                    None,
                    "import",
                    str(exc),
                )
        return summary


def _read_records(path: Path) -> list[tuple[int, dict[str, Any]]]:
    records: list[tuple[int, dict[str, Any]]] = []
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    for line_number, raw in enumerate(lines, start=1):
        if not raw.strip():
            continue
        try:
            value = json.loads(raw)
        except json.JSONDecodeError:
            if line_number == len(lines):
                continue
            raise
        if isinstance(value, dict):
            records.append((line_number, value))
    return records


def _supported_transcript(path: Path) -> bool:
    try:
        records = _read_records(path)
    except (OSError, json.JSONDecodeError):
        return False
    if not records:
        return False
    return all(
        record.get("type") in _ALLOWED_RECORD_TYPES
        and isinstance(record.get("sessionId"), str)
        for _, record in records
    )


def _message_text(message: dict[str, Any]) -> str | None:
    content = message.get("content")
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return None
    parts = [
        item.get("text")
        for item in content
        if isinstance(item, dict)
        and item.get("type") == "text"
        and isinstance(item.get("text"), str)
    ]
    return "\n".join(parts) if parts else None


def _persist_transcript(repository: Repository, path: Path) -> int:
    records = _read_records(path)
    if not records or not _supported_transcript(path):
        raise ValueError("Unsupported Claude Code transcript structure")

    session_external_id = str(records[0][1]["sessionId"])
    started_at = str(records[0][1].get("timestamp") or "") or None
    ended_at = str(records[-1][1].get("timestamp") or "") or None
    project_path = next(
        (
            str(record["cwd"])
            for _, record in records
            if isinstance(record.get("cwd"), str)
        ),
        None,
    )
    model = next(
        (
            normalize_model_name(message.get("model"))
            for _, record in records
            if record.get("type") == "assistant"
            and isinstance((message := record.get("message")), dict)
            and normalize_model_name(message.get("model")) is not None
        ),
        None,
    )
    session_id = repository.upsert_session(
        NormalizedSession(
            external_session_id=session_external_id,
            source="claude_code",
            started_at=started_at,
            ended_at=ended_at,
            project_path=project_path,
            provider="anthropic",
            model=model,
            raw_file_path=str(path),
            metadata={"format_version": _FORMAT_VERSION},
        )
    )

    for line_number, record in records:
        timestamp = str(record.get("timestamp") or "")
        message = record.get("message")
        if not isinstance(message, dict):
            continue
        role = str(message.get("role") or record.get("type") or "unknown")
        repository.insert_message(
            session_id,
            None,
            NormalizedMessage(
                role=role,
                timestamp=timestamp,
                content=_message_text(message),
                session_external_id=session_external_id,
                source_file=str(path),
                source_line=line_number,
            ),
        )
        if record.get("type") != "assistant":
            continue

        explicit_model = normalize_model_name(message.get("model"))
        usage = message.get("usage")
        if isinstance(usage, dict):
            uncached_input = _int_or_none(usage.get("input_tokens"))
            cached_input = _int_or_none(usage.get("cache_read_input_tokens"))
            cache_write = _int_or_none(usage.get("cache_creation_input_tokens"))
            output_tokens = _int_or_none(usage.get("output_tokens"))
            input_tokens = (
                int(uncached_input or 0)
                + int(cached_input or 0)
                + int(cache_write or 0)
            )
            repository.insert_token_usage(
                session_id,
                None,
                NormalizedTokenUsage(
                    timestamp=timestamp,
                    session_external_id=session_external_id,
                    model=explicit_model,
                    input_tokens=input_tokens,
                    cached_input_tokens=cached_input,
                    cache_write_input_tokens=cache_write,
                    output_tokens=output_tokens,
                    total_tokens=input_tokens + int(output_tokens or 0),
                    source_file=str(path),
                    source_line=line_number,
                ),
            )

        content = message.get("content")
        if isinstance(content, list):
            for index, item in enumerate(content):
                if not isinstance(item, dict) or item.get("type") != "tool_use":
                    continue
                tool_input = item.get("input")
                encoded = json.dumps(tool_input, ensure_ascii=False, sort_keys=True)
                repository.insert_tool_call(
                    session_id,
                    None,
                    NormalizedToolCall(
                        name=str(item.get("name") or "unknown"),
                        timestamp=timestamp,
                        external_call_id=(
                            str(item.get("id")) if item.get("id") else None
                        ),
                        session_external_id=session_external_id,
                        provider="anthropic",
                        category="tool",
                        input_size=len(encoded),
                        source_file=str(path),
                        source_line=line_number * 1000 + index,
                    ),
                )
    return session_id


def _int_or_none(value: Any) -> int | None:
    return int(value) if isinstance(value, (int, float)) else None


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _unchanged(repository: Repository, path: Path, digest: str) -> bool:
    state = repository.get_import_state("claude_code", str(path))
    return bool(
        state
        and state.get("content_hash") == digest
        and state.get("size") == path.stat().st_size
    )


def _save_state(repository: Repository, path: Path, digest: str) -> None:
    stat = path.stat()
    repository.save_import_state(
        "claude_code",
        str(path),
        size=stat.st_size,
        modified_at=stat.st_mtime,
        content_hash=digest,
        last_offset=stat.st_size,
        status="complete",
    )
