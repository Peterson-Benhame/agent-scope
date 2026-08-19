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


class GeminiAdapter:
    source_name = "gemini"

    def discover(self, context: DiscoveryContext) -> SourceDiscovery:
        root = context.overrides.get(self.source_name, context.user_home / ".gemini")
        tmp_root = root / "tmp"
        candidates = (
            tuple(sorted(tmp_root.glob("*/chats/session-*.jsonl")))
            if tmp_root.exists()
            else ()
        )
        supported = tuple(path for path in candidates if _supported_session(path))
        if supported:
            return SourceDiscovery(
                source=self.source_name,
                detected=True,
                roots=(root,),
                format_version=_FORMAT_VERSION,
                artifacts=supported,
                diagnostic=(
                    "Some Gemini sessions use an unsupported structure"
                    if len(supported) != len(candidates)
                    else None
                ),
            )
        return SourceDiscovery(
            source=self.source_name,
            detected=False,
            roots=(root,),
            artifacts=(),
            diagnostic=(
                "Gemini unsupported session structure"
                if candidates
                else "No Gemini session files found"
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
                session_id = _persist_session(repository, path)
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


def _records(path: Path) -> list[tuple[int, dict[str, Any]]]:
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


def _supported_session(path: Path) -> bool:
    try:
        records = _records(path)
    except (OSError, json.JSONDecodeError):
        return False
    if not records:
        return False
    metadata = records[0][1]
    return (
        isinstance(metadata.get("sessionId"), str)
        and isinstance(metadata.get("projectHash"), str)
        and isinstance(metadata.get("startTime"), str)
    )


def _content_text(content: Any) -> str | None:
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return None
    parts = [
        item.get("text")
        for item in content
        if isinstance(item, dict) and isinstance(item.get("text"), str)
    ]
    return "\n".join(parts) if parts else None


def _persist_tool_calls(
    repository: Repository,
    session_id: int,
    external_id: str,
    record: dict[str, Any],
    path: Path,
    line_number: int,
) -> None:
    tool_calls = record.get("toolCalls")
    if not isinstance(tool_calls, list):
        return
    for index, tool in enumerate(tool_calls):
        if not isinstance(tool, dict):
            continue
        name = tool.get("name")
        if not isinstance(name, str) or not name.strip():
            continue
        args = tool.get("args")
        encoded = json.dumps(args, ensure_ascii=False, sort_keys=True)
        repository.insert_tool_call(
            session_id,
            None,
            NormalizedToolCall(
                name=name.strip(),
                timestamp=str(tool.get("timestamp") or record.get("timestamp") or ""),
                external_call_id=(str(tool.get("id")) if tool.get("id") else None),
                session_external_id=external_id,
                status=(str(tool.get("status")) if tool.get("status") else None),
                provider="google",
                category="tool",
                input_size=len(encoded),
                source_file=str(path),
                source_line=line_number * 1000 + index,
            ),
        )


def _persist_session(repository: Repository, path: Path) -> int:
    records = _records(path)
    if not records or not _supported_session(path):
        raise ValueError("Unsupported Gemini session structure")
    metadata = records[0][1]
    external_id = str(metadata["sessionId"])
    model = next(
        (
            normalize_model_name(record.get("model"))
            for _, record in records[1:]
            if record.get("type") == "gemini"
            and normalize_model_name(record.get("model")) is not None
        ),
        None,
    )
    session_id = repository.upsert_session(
        NormalizedSession(
            external_session_id=external_id,
            source="gemini",
            started_at=str(metadata["startTime"]),
            ended_at=(
                str(metadata.get("lastUpdated"))
                if isinstance(metadata.get("lastUpdated"), str)
                else None
            ),
            provider="google",
            model=model,
            raw_file_path=str(path),
            metadata={
                "format_version": _FORMAT_VERSION,
                "project_hash": str(metadata["projectHash"]),
                "kind": metadata.get("kind"),
            },
        )
    )

    for line_number, record in records[1:]:
        record_type = record.get("type")
        if record_type not in {"user", "gemini"}:
            continue
        timestamp = str(record.get("timestamp") or "")
        repository.insert_message(
            session_id,
            None,
            NormalizedMessage(
                role="user" if record_type == "user" else "assistant",
                timestamp=timestamp,
                content=_content_text(record.get("content")),
                session_external_id=external_id,
                source_file=str(path),
                source_line=line_number,
            ),
        )
        if record_type != "gemini":
            continue

        _persist_tool_calls(
            repository,
            session_id,
            external_id,
            record,
            path,
            line_number,
        )
        tokens = record.get("tokens")
        if not isinstance(tokens, dict):
            continue
        repository.insert_token_usage(
            session_id,
            None,
            NormalizedTokenUsage(
                timestamp=timestamp,
                session_external_id=external_id,
                model=normalize_model_name(record.get("model")),
                input_tokens=_int_or_none(tokens.get("input")),
                cached_input_tokens=_int_or_none(tokens.get("cached")),
                output_tokens=_int_or_none(tokens.get("output")),
                reasoning_output_tokens=_int_or_none(tokens.get("thoughts")),
                total_tokens=_int_or_none(tokens.get("total")),
                source_file=str(path),
                source_line=line_number,
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
    state = repository.get_import_state("gemini", str(path))
    return bool(
        state
        and state.get("content_hash") == digest
        and state.get("size") == path.stat().st_size
    )


def _save_state(repository: Repository, path: Path, digest: str) -> None:
    stat = path.stat()
    repository.save_import_state(
        "gemini",
        str(path),
        size=stat.st_size,
        modified_at=stat.st_mtime,
        content_hash=digest,
        last_offset=stat.st_size,
        status="complete",
    )
