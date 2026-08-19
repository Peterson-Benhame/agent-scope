from __future__ import annotations

from dataclasses import dataclass, replace

from agentscope.config import AgentScopeConfig
from agentscope.importer import collect_registered_sources
from agentscope.storage.repository import Repository


@dataclass(frozen=True, slots=True)
class IdentityBackfillSummary:
    sessions_scanned: int
    sessions_updated: int
    sessions_without_user: int
    sessions_without_machine: int
    errors: int


def _identity_counts(
    repository: Repository,
    sources: frozenset[str] | None,
) -> tuple[int, int, int, int]:
    clauses: list[str] = []
    params: list[object] = []
    if sources:
        placeholders = ",".join("?" for _ in sources)
        clauses.append(f"src.name IN ({placeholders})")
        params.extend(sorted(sources))
    where = f" WHERE {' AND '.join(clauses)}" if clauses else ""

    with repository.database.connect() as conn:
        row = conn.execute(
            """
            SELECT COUNT(*) AS total,
                   SUM(CASE WHEN s.user_id IS NULL THEN 1 ELSE 0 END) AS no_user,
                   SUM(CASE WHEN s.machine_id IS NULL THEN 1 ELSE 0 END) AS no_machine,
                   SUM(
                       CASE
                           WHEN s.user_id IS NULL OR s.machine_id IS NULL THEN 1
                           ELSE 0
                       END
                   ) AS incomplete
            FROM sessions s
            JOIN sources src ON src.id=s.source_id
            """ + where,
            params,
        ).fetchone()

    return (
        int(row["total"] or 0),
        int(row["no_user"] or 0),
        int(row["no_machine"] or 0),
        int(row["incomplete"] or 0),
    )


def backfill_local_identity(
    repository: Repository,
    config: AgentScopeConfig,
    *,
    sources: frozenset[str] | None = None,
) -> IdentityBackfillSummary:
    active_sources = sources if sources is not None else config.enabled_sources
    before_total, _, _, before_incomplete = _identity_counts(
        repository,
        active_sources,
    )
    scoped_config = replace(config, enabled_sources=active_sources)
    collected = collect_registered_sources(
        repository,
        scoped_config,
        full_rescan=True,
        progress=None,
    )
    _, after_no_user, after_no_machine, after_incomplete = _identity_counts(
        repository,
        active_sources,
    )

    return IdentityBackfillSummary(
        sessions_scanned=before_total,
        sessions_updated=max(0, before_incomplete - after_incomplete),
        sessions_without_user=after_no_user,
        sessions_without_machine=after_no_machine,
        errors=collected.errors,
    )
