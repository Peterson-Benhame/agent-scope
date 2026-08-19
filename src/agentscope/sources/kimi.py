from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from agentscope.domain.models import NormalizedSession, NormalizedTokenUsage
from agentscope.sources.base import (
    CollectRequest,
    DiscoveryContext,
    SourceCapabilities,
    SourceCollectionSummary,
    SourceDiscovery,
)
from agentscope.storage.repository import Repository


class KimiAdapter:
    source_name = "kimi"

    def discover(self, context: DiscoveryContext) -> SourceDiscovery:
        root = context.overrides.get(self.source_name, context.user_home / ".kimi-code")
        sessions_root = root / "sessions"
        candidates = (
            tuple(sorted(sessions_root.glob("*/*/state.json")))
            if sessions_root.exists()
            else ()
        )
        supported = tuple(path for path in candidates if _supported_state(path))
        if supported:
            return SourceDiscovery(
                source=self.source_name,
                detected=True,
                roots=(root,),
                format_version="session-v1",
                artifacts=supported,
                diagnostic=(
                    "Some Kimi sessions use an unsupported state structure"
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
                "Kimi unsupported session state structure"
                if candidates
                else "No Kimi sessions found"
            ),
        )

    def capabilities(self) -> SourceCapabilities:
        return SourceCapabilities(sessions=True, tokens=True, cache=True)

    def collect(self, request: CollectRequest) -> SourceCollectionSummary:
        summary = SourceCollectionSummary()
        repository: Repository = request.repository
        user_id = repository.upsert_user(request.user) if request.user else None
        machine_id = repository.upsert_machine(request.machine) if request.machine else None
        for state_path in request.discovery.artifacts:
            summary.files_seen += 1
            wire_path = state_path.parent / "agents" / "main" / "wire.jsonl"
            digest, size, modified_at = _session_fingerprint(state_path, wire_path)
            if not request.full_rescan and _unchanged(
                repository, state_path, digest, size
            ):
                summary.files_skipped += 1
                continue
            try:
                session_id = _persist_session(repository, state_path, wire_path)
                if user_id is not None or machine_id is not None:
                    repository.associate_session_identity(session_id, user_id, machine_id)
                repository.save_import_state(
                    "kimi",
                    str(state_path),
                    size=size,
                    modified_at=modified_at,
                    content_hash=digest,
                    last_offset=size,
                    status="complete",
                )
                summary.files_imported += 1
                summary.sessions_imported += 1
            except Exception as exc:
                summary.errors += 1
                repository.record_import_error(
                    "kimi", str(state_path), None, "import", str(exc)
                )
        return summary


def _read_state(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("Kimi state must be an object")
    return value


def _supported_state(path: Path) -> bool:
    try:
        state = _read_state(path)
    except (OSError, json.JSONDecodeError, ValueError):
        return False
    return isinstance(state.get("sessionId"), str) and isinstance(
        state.get("workDir"), str
    )


def _wire_records(path: Path) -> list[tuple[int, dict[str, Any]]]:
    if not path.exists():
        return []
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


def _persist_session(repository: Repository, state_path: Path, wire_path: Path) -> int:
    state = _read_state(state_path)
    if not _supported_state(state_path):
        raise ValueError("Unsupported Kimi session state structure")
    external_id = str(state["sessionId"])
    session_id = repository.upsert_session(
        NormalizedSession(
            external_session_id=external_id,
            source="kimi",
            started_at=_optional_str(state.get("createdAt")),
            ended_at=_optional_str(state.get("updatedAt")),
            project_path=str(state["workDir"]),
            provider="moonshot",
            raw_file_path=str(state_path),
            metadata={"format_version": "session-v1"},
        )
    )
    default_timestamp = (
        _optional_str(state.get("updatedAt"))
        or _optional_str(state.get("createdAt"))
        or ""
    )
    for line_number, record in _wire_records(wire_path):
        if record.get("type") != "StatusUpdate":
            continue
        payload = record.get("payload")
        if not isinstance(payload, dict):
            continue
        token_usage = payload.get("token_usage")
        if not isinstance(token_usage, dict):
            continue
        input_other = _int(token_usage.get("input_other"))
        cache_read = _int(token_usage.get("input_cache_read"))
        cache_write = _int(token_usage.get("input_cache_creation"))
        output = _int(token_usage.get("output"))
        input_tokens = input_other + cache_read + cache_write
        repository.insert_token_usage(
            session_id,
            None,
            NormalizedTokenUsage(
                timestamp=default_timestamp,
                session_external_id=external_id,
                input_tokens=input_tokens,
                cached_input_tokens=cache_read,
                cache_write_input_tokens=cache_write,
                output_tokens=output,
                total_tokens=input_tokens + output,
                context_window=_int_or_none(payload.get("max_context_tokens")),
                source_file=str(wire_path),
                source_line=line_number,
            ),
        )
    return session_id


def _int(value: Any) -> int:
    return int(value) if isinstance(value, (int, float)) else 0


def _int_or_none(value: Any) -> int | None:
    return int(value) if isinstance(value, (int, float)) else None


def _optional_str(value: Any) -> str | None:
    return str(value) if isinstance(value, str) and value else None


def _session_fingerprint(state_path: Path, wire_path: Path) -> tuple[str, int, float]:
    digest = hashlib.sha256()
    size = 0
    modified_at = 0.0
    for path in (state_path, wire_path):
        if not path.exists():
            continue
        stat = path.stat()
        size += stat.st_size
        modified_at = max(modified_at, stat.st_mtime)
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    return digest.hexdigest(), size, modified_at


def _unchanged(
    repository: Repository,
    state_path: Path,
    digest: str,
    size: int,
) -> bool:
    state = repository.get_import_state("kimi", str(state_path))
    return bool(
        state
        and state.get("content_hash") == digest
        and state.get("size") == size
    )
