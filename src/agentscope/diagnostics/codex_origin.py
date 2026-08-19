from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from agentscope.analytics.filters import AnalyticsFilter
from agentscope.storage.repository import Repository


@dataclass(frozen=True, slots=True)
class CodexClientClassification:
    client: str
    evidence: tuple[str, ...]


def classify_codex_client(
    *,
    originator: str | None,
    metadata_source: str | None,
    thread_source: str | None,
) -> CodexClientClassification:
    evidence_values = (
        ("originator", originator),
        ("source", metadata_source),
        ("thread_source", thread_source),
    )

    def matches(value: str | None, tokens: tuple[str, ...]) -> bool:
        if not value:
            return False
        normalized = value.strip().lower().replace("-", "_")
        return any(token in normalized for token in tokens)

    classifications = (
        ("vscode", ("vscode", "vs_code")),
        ("cli", ("codex_cli", "_cli", "cli_")),
        ("web", ("codex_web", "_web", "web_")),
        ("app", ("codex_app", "desktop_app", "desktop")),
    )
    for client, tokens in classifications:
        matched = tuple(
            f"{field}={value}"
            for field, value in evidence_values
            if matches(value, tokens)
        )
        if matched:
            return CodexClientClassification(client=client, evidence=matched)

    return CodexClientClassification(client="unknown", evidence=())


class CodexOriginDiagnostics:
    """Inspect Codex session origin using only evidence already stored locally."""

    def __init__(
        self,
        repository: Repository,
        filters: AnalyticsFilter | None = None,
    ) -> None:
        self.repository = repository
        self.filters = filters or AnalyticsFilter()

    def _where(self) -> tuple[str, list[object]]:
        clauses = ["src.name = 'codex'"]
        params: list[object] = []
        filters = self.filters
        if filters.from_date is not None:
            clauses.append("substr(tu.timestamp, 1, 10) >= ?")
            params.append(filters.from_date.isoformat())
        if filters.to_date is not None:
            clauses.append("substr(tu.timestamp, 1, 10) <= ?")
            params.append(filters.to_date.isoformat())
        if filters.project is not None:
            clauses.append("p.name = ?")
            params.append(filters.project)
        if filters.model is not None:
            clauses.append("COALESCE(tm.name, sm.name) = ?")
            params.append(filters.model)
        if filters.user is not None:
            clauses.append("COALESCE(u.display_name, u.stable_key) = ?")
            params.append(filters.user)
        if filters.machine is not None:
            clauses.append("COALESCE(mc.display_name, mc.stable_key) = ?")
            params.append(filters.machine)
        return "WHERE " + " AND ".join(clauses), params

    @staticmethod
    def _metadata(raw: str | None) -> dict[str, Any]:
        if not raw:
            return {}
        try:
            value = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return {}
        return value if isinstance(value, dict) else {}

    def inspect(self) -> dict[str, object]:
        where, params = self._where()
        with self.repository.database.connect() as conn:
            rows = conn.execute(
                """
                SELECT s.external_session_id,
                       s.started_at,
                       s.originator,
                       s.provider,
                       s.metadata_json,
                       p.name AS project,
                       COALESCE(u.display_name, u.stable_key) AS user,
                       COALESCE(mc.display_name, mc.stable_key) AS machine,
                       MIN(tu.timestamp) AS first_activity_at,
                       MAX(tu.timestamp) AS last_activity_at,
                       COALESCE(SUM(tu.total_tokens), 0) AS total_tokens,
                       GROUP_CONCAT(DISTINCT COALESCE(tm.name, sm.name)) AS models
                FROM token_usage tu
                JOIN sessions s ON s.id=tu.session_id
                JOIN sources src ON src.id=s.source_id
                LEFT JOIN projects p ON p.id=s.project_id
                LEFT JOIN models tm ON tm.id=tu.model_id
                LEFT JOIN models sm ON sm.id=s.model_id
                LEFT JOIN users u ON u.id=s.user_id
                LEFT JOIN machines mc ON mc.id=s.machine_id
                """ + where + """
                GROUP BY s.id
                ORDER BY first_activity_at, s.external_session_id
                """,
                params,
            ).fetchall()

        sessions: list[dict[str, object]] = []
        client_totals: dict[str, dict[str, object]] = {}
        for row in rows:
            metadata = self._metadata(row["metadata_json"])
            metadata_source = metadata.get("source")
            thread_source = metadata.get("thread_source")
            classification = classify_codex_client(
                originator=row["originator"],
                metadata_source=(
                    str(metadata_source) if metadata_source is not None else None
                ),
                thread_source=(
                    str(thread_source) if thread_source is not None else None
                ),
            )
            token_count = int(row["total_tokens"] or 0)
            raw_models = str(row["models"] or "")
            models = sorted({item for item in raw_models.split(",") if item})
            sessions.append(
                {
                    "external_session_id": str(row["external_session_id"]),
                    "started_at": row["started_at"],
                    "first_activity_at": row["first_activity_at"],
                    "last_activity_at": row["last_activity_at"],
                    "project": row["project"],
                    "provider": row["provider"],
                    "originator": row["originator"],
                    "metadata_source": metadata_source,
                    "thread_source": thread_source,
                    "user": row["user"],
                    "machine": row["machine"],
                    "models": models,
                    "client": classification.client,
                    "evidence": list(classification.evidence),
                    "total_tokens": token_count,
                }
            )
            aggregate = client_totals.setdefault(
                classification.client,
                {"client": classification.client, "sessions": 0, "total_tokens": 0},
            )
            aggregate["sessions"] = int(aggregate["sessions"]) + 1
            aggregate["total_tokens"] = int(aggregate["total_tokens"]) + token_count

        clients = sorted(
            client_totals.values(),
            key=lambda item: (-int(item["total_tokens"]), str(item["client"])),
        )
        return {
            "summary": {
                "sessions": len(sessions),
                "total_tokens": sum(int(item["total_tokens"]) for item in sessions),
                "unclassified_sessions": sum(
                    1 for item in sessions if item["client"] == "unknown"
                ),
                "clients": clients,
            },
            "sessions": sessions,
        }
