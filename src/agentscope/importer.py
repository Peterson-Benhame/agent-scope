from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from agentscope.collectors.codex import collect_codex_rollout
from agentscope.collectors.headroom import collect_headroom
from agentscope.correlation import correlate_optimization
from agentscope.storage.repository import Repository


@dataclass(slots=True)
class ImportSummary:
    files_seen: int = 0
    files_imported: int = 0
    files_skipped: int = 0
    sessions_imported: int = 0
    optimizations_imported: int = 0
    errors: int = 0


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _unchanged(repo: Repository, source: str, path: Path, digest: str) -> bool:
    state = repo.get_import_state(source, str(path))
    return bool(state and state.get("content_hash") == digest and state.get("size") == path.stat().st_size)


def _save_state(repo: Repository, source: str, path: Path, digest: str, status: str = "complete") -> None:
    stat = path.stat()
    repo.save_import_state(
        source,
        str(path),
        size=stat.st_size,
        modified_at=stat.st_mtime,
        content_hash=digest,
        last_offset=stat.st_size,
        status=status,
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


def _import_codex_file(repo: Repository, path: Path) -> None:
    data = collect_codex_rollout(path)
    session_id = repo.upsert_session(data.session)
    turn_ids: dict[str, int] = {}
    for turn in data.turns:
        turn_ids[turn.external_turn_id] = repo.upsert_turn(session_id, turn)
    for message in data.messages:
        repo.insert_message(session_id, turn_ids.get(message.turn_external_id or ""), message)
    for call in data.tool_calls:
        call.category = _tool_category(call.name)
        repo.insert_tool_call(session_id, turn_ids.get(call.turn_external_id or ""), call)
    for usage in data.token_usage:
        repo.insert_token_usage(session_id, turn_ids.get(usage.turn_external_id or ""), usage)
    for evidence in data.agent_evidence:
        repo.upsert_agent_evidence(session_id, evidence)
    for evidence in data.skill_evidence:
        repo.upsert_skill_evidence(session_id, evidence)
    for line, error in data.parse_errors:
        repo.record_import_error("codex", str(path), line, "parse", error)


def collect_sources(
    repository: Repository,
    *,
    codex_home: Path | None = None,
    headroom_home: Path | None = None,
    full_rescan: bool = False,
) -> ImportSummary:
    summary = ImportSummary()

    if codex_home:
        sessions_root = codex_home / "sessions"
        if sessions_root.exists():
            for path in sorted(sessions_root.rglob("*.jsonl")):
                summary.files_seen += 1
                try:
                    digest = _hash_file(path)
                    if not full_rescan and _unchanged(repository, "codex", path, digest):
                        summary.files_skipped += 1
                        continue
                    _import_codex_file(repository, path)
                    _save_state(repository, "codex", path, digest)
                    summary.files_imported += 1
                    summary.sessions_imported += 1
                except Exception as exc:
                    summary.errors += 1
                    repository.record_import_error("codex", str(path), None, "import", str(exc))

    if headroom_home and headroom_home.exists():
        source_files = [p for p in [headroom_home / "proxy_savings.json", *sorted(headroom_home.glob("*.jsonl"))] if p.exists()]
        changed = full_rescan or not source_files
        digests: dict[Path, str] = {}
        for path in source_files:
            summary.files_seen += 1
            digest = _hash_file(path)
            digests[path] = digest
            if full_rescan or not _unchanged(repository, "headroom", path, digest):
                changed = True
            else:
                summary.files_skipped += 1
        if changed and source_files:
            data = collect_headroom(headroom_home)
            candidates = repository.session_candidates()
            for optimization in data.optimizations:
                correlation = correlate_optimization(optimization, candidates)
                optimization.confidence = correlation.confidence
                optimization.session_external_id = correlation.session_external_id
                session_id = (
                    repository.session_id_by_external(correlation.session_external_id)
                    if correlation.session_external_id
                    else None
                )
                repository.insert_optimization(optimization, session_id=session_id)
                summary.optimizations_imported += 1
            if data.lifetime:
                compression = data.lifetime.get("compression_savings_usd")
                cache = data.lifetime.get("cache_savings_usd")
                observed = data.lifetime.get("total_input_cost_usd")
                total_savings = (float(compression or 0) + float(cache or 0)) if (compression is not None or cache is not None) else None
                repository.insert_cost(
                    session_id=None,
                    model_id=None,
                    estimated_raw_cost_usd=None,
                    observed_cost_usd=float(observed) if observed is not None else None,
                    compression_savings_usd=float(compression) if compression is not None else None,
                    cache_savings_usd=float(cache) if cache is not None else None,
                    total_savings_usd=total_savings,
                    pricing_source="headroom:lifetime",
                    pricing_version="proxy_savings",
                    snapshot_key="headroom:lifetime",
                )
            for path, digest in digests.items():
                _save_state(repository, "headroom", path, digest)
                summary.files_imported += 1

    return summary
