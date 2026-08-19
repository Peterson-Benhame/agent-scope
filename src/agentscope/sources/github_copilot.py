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
from agentscope.sources.format_detection import require_known_version
from agentscope.storage.repository import Repository


_SUPPORTED_VERSIONS = {"1"}


class GitHubCopilotAdapter:
    source_name = "github_copilot"

    def discover(self, context: DiscoveryContext) -> SourceDiscovery:
        root = context.overrides.get(self.source_name, context.user_home / ".copilot")
        state_root = root / "session-state"
        candidates = (
            tuple(sorted(state_root.glob("*/events.jsonl")))
            if state_root.exists()
            else ()
        )
        supported: list[Path] = []
        diagnostic: str | None = None
        for path in candidates:
            version = _event_version(path)
            support = require_known_version(
                str(version) if version is not None else None,
                _SUPPORTED_VERSIONS,
                self.source_name,
            )
            if support.supported:
                supported.append(path)
            elif diagnostic is None:
                diagnostic = support.diagnostic

        if supported:
            return SourceDiscovery(
                source=self.source_name,
                detected=True,
                roots=(root,),
                format_version="events-v1",
                artifacts=tuple(supported),
                diagnostic=diagnostic,
            )
        return SourceDiscovery(
            source=self.source_name,
            detected=False,
            roots=(root,),
            artifacts=(),
            diagnostic=diagnostic or "No GitHub Copilot session events found",
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
                session_id = _persist_events(repository, path)
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
    values: list[tuple[int, dict[str, Any]]] = []
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    for line_number, raw in enumerate(lines, start=1):
        if not raw.strip():
            continue
        try:
            record = json.loads(raw)
        except json.JSONDecodeError:
            if line_number == len(lines):
                continue
            raise
        if isinstance(record, dict):
            values.append((line_number, record))
    return values


def _event_version(path: Path) -> int | None:
    try:
        for _, record in _records(path):
            if record.get("type") != "session.start":
                continue
            data = record.get("data")
            if isinstance(data, dict) and isinstance(data.get("version"), int):
                return int(data["version"])
    except (OSError, json.JSONDecodeError):
        return None
    return None


def _timestamp(data: dict[str, Any], fallback: str | None = None) -> str:
    return str(
        data.get("timestamp")
        or data.get("startTime")
        or fallback
        or ""
    )


def _persist_events(repository: Repository, path: Path) -> int:
    records = _records(path)
    start = next(
        (
            record.get("data")
            for _, record in records
            if record.get("type") == "session.start"
            and isinstance(record.get("data"), dict)
        ),
        None,
    )
    if not isinstance(start, dict):
        raise ValueError("GitHub Copilot events missing session.start")
    support = require_known_version(
        str(start.get("version")) if start.get("version") is not None else None,
        _SUPPORTED_VERSIONS,
        "github_copilot",
    )
    if not support.supported:
        raise ValueError(support.diagnostic or "Unsupported GitHub Copilot events")

    shutdown = next(
        (
            record.get("data")
            for _, record in reversed(records)
            if record.get("type") == "session.shutdown"
            and isinstance(record.get("data"), dict)
        ),
        {},
    )
    session_external_id = str(start.get("sessionId") or path.parent.name)
    context = start.get("context") if isinstance(start.get("context"), dict) else {}
    model = normalize_model_name(
        shutdown.get("currentModel") if isinstance(shutdown, dict) else None
    )
    session_id = repository.upsert_session(
        NormalizedSession(
            external_session_id=session_external_id,
            source="github_copilot",
            started_at=_timestamp(start) or None,
            ended_at=(
                _timestamp(shutdown) or None if isinstance(shutdown, dict) else None
            ),
            project_path=(
                str(context.get("cwd")) if isinstance(context.get("cwd"), str) else None
            ),
            provider="github-copilot",
            model=model,
            cli_version=(
                str(start.get("copilotVersion"))
                if start.get("copilotVersion") is not None
                else None
            ),
            raw_file_path=str(path),
            metadata={"format_version": "events-v1"},
        )
    )

    for line_number, record in records:
        event_type = str(record.get("type") or "")
        data = record.get("data")
        if not isinstance(data, dict):
            continue
        timestamp = _timestamp(data, _timestamp(start))
        if event_type in {"user.message", "assistant.message"}:
            role = "user" if event_type == "user.message" else "assistant"
            content = data.get("content")
            repository.insert_message(
                session_id,
                None,
                NormalizedMessage(
                    role=role,
                    timestamp=timestamp,
                    content=str(content) if isinstance(content, str) else None,
                    session_external_id=session_external_id,
                    source_file=str(path),
                    source_line=line_number,
                ),
            )
            requests = data.get("toolRequests")
            if isinstance(requests, list):
                for index, request in enumerate(requests):
                    if not isinstance(request, dict):
                        continue
                    arguments = request.get("arguments")
                    encoded = json.dumps(arguments, ensure_ascii=False, sort_keys=True)
                    repository.insert_tool_call(
                        session_id,
                        None,
                        NormalizedToolCall(
                            name=str(request.get("name") or "unknown"),
                            timestamp=timestamp,
                            external_call_id=(
                                str(request.get("toolCallId"))
                                if request.get("toolCallId")
                                else None
                            ),
                            session_external_id=session_external_id,
                            provider="github-copilot",
                            category="tool",
                            input_size=len(encoded),
                            source_file=str(path),
                            source_line=line_number * 1000 + index,
                        ),
                    )

    if isinstance(shutdown, dict):
        metrics = shutdown.get("modelMetrics")
        if isinstance(metrics, dict):
            for model_name, model_metrics in metrics.items():
                if not isinstance(model_metrics, dict):
                    continue
                usage = model_metrics.get("usage")
                if not isinstance(usage, dict):
                    continue
                input_tokens = _int_or_none(usage.get("inputTokens"))
                output_tokens = _int_or_none(usage.get("outputTokens"))
                repository.insert_token_usage(
                    session_id,
                    None,
                    NormalizedTokenUsage(
                        timestamp=_timestamp(shutdown, _timestamp(start)),
                        session_external_id=session_external_id,
                        model=normalize_model_name(str(model_name)),
                        input_tokens=input_tokens,
                        cached_input_tokens=_int_or_none(usage.get("cacheReadTokens")),
                        cache_write_input_tokens=_int_or_none(usage.get("cacheWriteTokens")),
                        output_tokens=output_tokens,
                        reasoning_output_tokens=_int_or_none(usage.get("reasoningTokens")),
                        total_tokens=(
                            int(input_tokens or 0) + int(output_tokens or 0)
                            if input_tokens is not None or output_tokens is not None
                            else None
                        ),
                        source_file=str(path),
                        source_line=900000,
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
    state = repository.get_import_state("github_copilot", str(path))
    return bool(
        state
        and state.get("content_hash") == digest
        and state.get("size") == path.stat().st_size
    )


def _save_state(repository: Repository, path: Path, digest: str) -> None:
    stat = path.stat()
    repository.save_import_state(
        "github_copilot",
        str(path),
        size=stat.st_size,
        modified_at=stat.st_mtime,
        content_hash=digest,
        last_offset=stat.st_size,
        status="complete",
    )
