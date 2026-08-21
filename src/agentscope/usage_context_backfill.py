from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass

from agentscope.domain.models import NormalizedSession
from agentscope.storage.repository import Repository
from agentscope.usage_context import (
    ensure_usage_context_schema,
    infer_codex_usage_context,
    persist_session_usage_context,
)


@dataclass(frozen=True, slots=True)
class UsageContextBackfillSummary:
    sessions_scanned: int
    sessions_updated: int
    sessions_existing: int
    clients: dict[str, int]
    billing_modes: dict[str, int]
    errors: int


def _metadata(raw: str | None) -> dict[str, object]:
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {}
    return value if isinstance(value, dict) else {}


def _source_filter(sources: frozenset[str] | None) -> tuple[str, list[object]]:
    if not sources:
        return "", []
    placeholders = ",".join("?" for _ in sources)
    return f" WHERE src.name IN ({placeholders})", list(sorted(sources))


def backfill_usage_context(
    repository: Repository,
    *,
    sources: frozenset[str] | None = frozenset({"codex"}),
) -> UsageContextBackfillSummary:
    ensure_usage_context_schema(repository)
    where, params = _source_filter(sources)
    with repository.database.connect() as conn:
        rows = conn.execute(
            """
            SELECT s.id,
                   s.external_session_id,
                   s.started_at,
                   s.ended_at,
                   s.originator,
                   s.provider,
                   s.cli_version,
                   s.raw_file_path,
                   s.metadata_json,
                   p.path AS project_path,
                   sm.name AS model,
                   src.name AS source,
                   CASE WHEN uc.session_id IS NULL THEN 0 ELSE 1 END AS has_context
            FROM sessions s
            JOIN sources src ON src.id=s.source_id
            LEFT JOIN projects p ON p.id=s.project_id
            LEFT JOIN models sm ON sm.id=s.model_id
            LEFT JOIN session_usage_context uc ON uc.session_id=s.id
            """ + where + """
            ORDER BY s.id
            """,
            params,
        ).fetchall()

    updated = 0
    existing = 0
    errors = 0
    for row in rows:
        if bool(row["has_context"]):
            existing += 1
            continue
        if str(row["source"]) != "codex":
            continue
        try:
            session = NormalizedSession(
                external_session_id=str(row["external_session_id"]),
                source=str(row["source"]),
                started_at=row["started_at"],
                ended_at=row["ended_at"],
                project_path=row["project_path"],
                originator=row["originator"],
                provider=row["provider"],
                model=row["model"],
                cli_version=row["cli_version"],
                raw_file_path=row["raw_file_path"],
                metadata=_metadata(row["metadata_json"]),
            )
            persist_session_usage_context(
                repository,
                int(row["id"]),
                infer_codex_usage_context(session),
            )
            updated += 1
        except (ValueError, TypeError, KeyError, json.JSONDecodeError):
            errors += 1

    with repository.database.connect() as conn:
        client_rows = conn.execute(
            """
            SELECT uc.client, COUNT(*) AS n
            FROM session_usage_context uc
            JOIN sessions s ON s.id=uc.session_id
            JOIN sources src ON src.id=s.source_id
            """ + where + """
            GROUP BY uc.client
            ORDER BY uc.client
            """,
            params,
        ).fetchall()
        billing_rows = conn.execute(
            """
            SELECT uc.billing_mode, COUNT(*) AS n
            FROM session_usage_context uc
            JOIN sessions s ON s.id=uc.session_id
            JOIN sources src ON src.id=s.source_id
            """ + where + """
            GROUP BY uc.billing_mode
            ORDER BY uc.billing_mode
            """,
            params,
        ).fetchall()

    clients = Counter({str(row["client"]): int(row["n"]) for row in client_rows})
    billing_modes = Counter(
        {str(row["billing_mode"]): int(row["n"]) for row in billing_rows}
    )
    return UsageContextBackfillSummary(
        sessions_scanned=len(rows),
        sessions_updated=updated,
        sessions_existing=existing,
        clients=dict(clients),
        billing_modes=dict(billing_modes),
        errors=errors,
    )
