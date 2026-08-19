from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from agentscope.domain.models import NormalizedSession
from agentscope.sources.base import (
    CollectRequest,
    DiscoveryContext,
    SourceCapabilities,
    SourceCollectionSummary,
    SourceDiscovery,
)
from agentscope.storage.repository import Repository


_FORMAT_VERSION = "index-state-v1"


def _read_index(path: Path) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
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
            entries.append(value)
    return entries


def _state_for(
    root: Path,
    entry: dict[str, Any],
) -> tuple[Path, dict[str, Any]] | None:
    session_id = entry.get("sessionId")
    session_dir = entry.get("sessionDir")
    work_dir = entry.get("workDir")
    values = (session_id, session_dir, work_dir)
    if not all(isinstance(value, str) and value for value in values):
        return None

    state_path = root / str(session_dir) / "state.json"
    if not state_path.is_file():
        return None
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(state, dict):
        return None
    if not isinstance(state.get("createdAt"), str):
        return None
    if not isinstance(state.get("updatedAt"), str):
        return None
    return state_path, state


def _valid_entries(
    root: Path,
    index_path: Path,
) -> list[tuple[dict[str, Any], Path, dict[str, Any]]]:
    valid: list[tuple[dict[str, Any], Path, dict[str, Any]]] = []
    try:
        entries = _read_index(index_path)
    except (OSError, json.JSONDecodeError):
        return valid
    for entry in entries:
        resolved = _state_for(root, entry)
        if resolved is None:
            continue
        state_path, state = resolved
        valid.append((entry, state_path, state))
    return valid


def _content_hash(
    index_path: Path,
    valid_entries: list[tuple[dict[str, Any], Path, dict[str, Any]]],
) -> str:
    digest = hashlib.sha256()
    digest.update(index_path.read_bytes())
    for _, state_path, _ in sorted(valid_entries, key=lambda item: str(item[1])):
        digest.update(str(state_path).encode("utf-8"))
        digest.update(state_path.read_bytes())
    return digest.hexdigest()


def _unchanged(repository: Repository, path: Path, digest: str) -> bool:
    state = repository.get_import_state("kimi", str(path))
    return bool(state and state.get("content_hash") == digest)


def _save_import_state(repository: Repository, path: Path, digest: str) -> None:
    stat = path.stat()
    repository.save_import_state(
        "kimi",
        str(path),
        size=stat.st_size,
        modified_at=stat.st_mtime,
        content_hash=digest,
        last_offset=stat.st_size,
        status="complete",
    )


class KimiAdapter:
    source_name = "kimi"

    def discover(self, context: DiscoveryContext) -> SourceDiscovery:
        root = context.overrides.get(
            self.source_name,
            context.user_home / ".kimi-code",
        )
        index_path = root / "session_index.jsonl"
        if not index_path.is_file():
            return SourceDiscovery(
                source=self.source_name,
                detected=False,
                roots=(root,),
                diagnostic="No Kimi session index found",
            )

        valid = _valid_entries(root, index_path)
        if not valid:
            return SourceDiscovery(
                source=self.source_name,
                detected=False,
                roots=(root,),
                diagnostic=(
                    "Kimi session index found but no supported state.json records"
                ),
            )

        return SourceDiscovery(
            source=self.source_name,
            detected=True,
            roots=(root,),
            format_version=_FORMAT_VERSION,
            artifacts=(index_path,),
        )

    def capabilities(self) -> SourceCapabilities:
        return SourceCapabilities(sessions=True)

    def collect(self, request: CollectRequest) -> SourceCollectionSummary:
        summary = SourceCollectionSummary()
        if not request.discovery.artifacts:
            return summary

        repository: Repository = request.repository
        root = request.discovery.roots[0]
        index_path = request.discovery.artifacts[0]
        summary.files_seen = 1
        valid = _valid_entries(root, index_path)
        if not valid:
            summary.errors = 1
            repository.record_import_error(
                self.source_name,
                str(index_path),
                None,
                "format",
                "Kimi session index has no supported state.json records",
            )
            return summary

        digest = _content_hash(index_path, valid)
        if not request.full_rescan and _unchanged(repository, index_path, digest):
            summary.files_skipped = 1
            return summary

        user_id = repository.upsert_user(request.user) if request.user else None
        machine_id = (
            repository.upsert_machine(request.machine) if request.machine else None
        )
        for entry, state_path, state in valid:
            try:
                session_id = repository.upsert_session(
                    NormalizedSession(
                        external_session_id=str(entry["sessionId"]),
                        source=self.source_name,
                        started_at=str(state["createdAt"]),
                        ended_at=str(state["updatedAt"]),
                        project_path=str(entry["workDir"]),
                        originator="kimi_code",
                        provider="moonshot",
                        raw_file_path=str(state_path),
                        metadata={"format_version": _FORMAT_VERSION},
                    )
                )
                if user_id is not None or machine_id is not None:
                    repository.associate_session_identity(
                        session_id,
                        user_id,
                        machine_id,
                    )
                summary.sessions_imported += 1
            except Exception as exc:
                summary.errors += 1
                repository.record_import_error(
                    self.source_name,
                    str(state_path),
                    None,
                    "import",
                    str(exc),
                )

        if summary.errors == 0:
            _save_import_state(repository, index_path, digest)
            summary.files_imported = 1
        return summary
