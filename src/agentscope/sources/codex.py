from __future__ import annotations

import hashlib
from pathlib import Path

from agentscope.collectors.codex import collect_codex_rollout
from agentscope.sources.base import (
    CollectRequest,
    DiscoveryContext,
    SourceCapabilities,
    SourceCollectionSummary,
    SourceDiscovery,
)
from agentscope.storage.repository import Repository
from agentscope.usage_context import (
    infer_codex_usage_context,
    persist_session_usage_context,
)


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _unchanged(repository: Repository, path: Path, digest: str) -> bool:
    state = repository.get_import_state("codex", str(path))
    return bool(
        state
        and state.get("content_hash") == digest
        and state.get("size") == path.stat().st_size
    )


def _save_state(repository: Repository, path: Path, digest: str) -> None:
    stat = path.stat()
    repository.save_import_state(
        "codex",
        str(path),
        size=stat.st_size,
        modified_at=stat.st_mtime,
        content_hash=digest,
        last_offset=stat.st_size,
        status="complete",
    )


def _tool_category(name: str) -> str:
    lower = name.lower()
    if "agent" in lower:
        return "agent_collaboration"
    if lower in {"exec", "shell", "shell_command"}:
        return "shell"
    if "github" in lower or lower.startswith("gh"):
        return "github"
    if "browser" in lower:
        return "browser"
    if "file" in lower or "read" in lower or "write" in lower:
        return "filesystem"
    if "mcp" in lower:
        return "mcp"
    return "other"


def _has_source_reported_usage(repository: Repository, session_id: int) -> bool:
    with repository.database.connect() as conn:
        row = conn.execute(
            """
            SELECT 1
            FROM token_usage
            WHERE session_id=? AND token_source='source_reported'
            LIMIT 1
            """,
            (session_id,),
        ).fetchone()
    return row is not None


def _delete_fallback_usage(repository: Repository, session_id: int) -> None:
    with repository.database.connect() as conn:
        conn.execute(
            "DELETE FROM token_usage WHERE session_id=? AND token_source='tiktoken_estimate'",
            (session_id,),
        )


def _insert_token_usage(
    repository: Repository,
    session_id: int,
    turn_id: int | None,
    usage,
) -> int:
    usage_id = repository.insert_token_usage(session_id, turn_id, usage)
    with repository.database.connect() as conn:
        conn.execute(
            "UPDATE token_usage SET token_source=? WHERE id=?",
            (usage.token_source, usage_id),
        )
    return usage_id


def _import_rollout(repository: Repository, path: Path) -> int:
    data = collect_codex_rollout(path)
    session_id = repository.upsert_session(data.session)
    persist_session_usage_context(
        repository,
        session_id,
        infer_codex_usage_context(data.session),
    )
    turn_ids: dict[str, int] = {}
    for turn in data.turns:
        turn_ids[turn.external_turn_id] = repository.upsert_turn(session_id, turn)
    for message in data.messages:
        repository.insert_message(
            session_id,
            turn_ids.get(message.turn_external_id or ""),
            message,
        )
    for call in data.tool_calls:
        call.category = _tool_category(call.name)
        repository.insert_tool_call(
            session_id,
            turn_ids.get(call.turn_external_id or ""),
            call,
        )

    has_new_source_usage = any(
        usage.token_source == "source_reported" for usage in data.token_usage
    )
    if has_new_source_usage:
        _delete_fallback_usage(repository, session_id)
    existing_source_usage = _has_source_reported_usage(repository, session_id)

    for usage in data.token_usage:
        if usage.token_source == "tiktoken_estimate" and existing_source_usage:
            continue
        _insert_token_usage(
            repository,
            session_id,
            turn_ids.get(usage.turn_external_id or ""),
            usage,
        )
    for evidence in data.agent_evidence:
        repository.upsert_agent_evidence(session_id, evidence)
    for evidence in data.skill_evidence:
        repository.upsert_skill_evidence(session_id, evidence)
    for line, error in data.parse_errors:
        repository.record_import_error("codex", str(path), line, "parse", error)
    return session_id


class CodexAdapter:
    source_name = "codex"

    def discover(self, context: DiscoveryContext) -> SourceDiscovery:
        root = context.overrides.get("codex", context.user_home / ".codex")
        sessions_root = root / "sessions"
        artifacts = (
            tuple(sorted(sessions_root.rglob("*.jsonl")))
            if sessions_root.exists()
            else ()
        )
        return SourceDiscovery(
            source=self.source_name,
            detected=bool(artifacts),
            roots=(root,),
            format_version="rollout-jsonl" if artifacts else None,
            artifacts=artifacts,
            diagnostic=None if artifacts else "No Codex rollout files found",
        )

    def capabilities(self) -> SourceCapabilities:
        return SourceCapabilities(
            sessions=True,
            messages=True,
            tokens=True,
            cache=True,
            tools=True,
            agents=True,
            skills=True,
        )

    def collect(self, request: CollectRequest) -> SourceCollectionSummary:
        summary = SourceCollectionSummary()
        repository = request.repository
        user_id = repository.upsert_user(request.user) if request.user else None
        machine_id = (
            repository.upsert_machine(request.machine) if request.machine else None
        )
        for path in request.discovery.artifacts:
            summary.files_seen += 1
            try:
                digest = _hash_file(path)
                if not request.full_rescan and _unchanged(repository, path, digest):
                    summary.files_skipped += 1
                    continue
                session_id = _import_rollout(repository, path)
                if user_id is not None or machine_id is not None:
                    repository.associate_session_identity(
                        session_id,
                        user_id,
                        machine_id,
                    )
                _save_state(repository, path, digest)
                summary.files_imported += 1
                summary.sessions_imported += 1
            except Exception as exc:
                summary.errors += 1
                repository.record_import_error(
                    "codex",
                    str(path),
                    None,
                    "import",
                    str(exc),
                )
        return summary
