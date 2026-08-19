from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from agentscope.analytics.filters import AnalyticsFilter
from agentscope.storage.repository import Repository


@dataclass(frozen=True, slots=True)
class TeamAnalyticsSummary:
    users: int = 0
    machines: int = 0
    sessions: int = 0
    input_tokens: int = 0
    cached_input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    observed_cost_usd: float | None = None
    estimated_raw_cost_usd: float | None = None
    total_savings_usd: float | None = None

    @property
    def cache_ratio(self) -> float:
        return (
            self.cached_input_tokens / self.input_tokens
            if self.input_tokens
            else 0.0
        )


class TeamAnalyticsService:
    def __init__(
        self,
        repository: Repository,
        filters: AnalyticsFilter | None = None,
    ):
        self.repository = repository
        self.filters = filters or AnalyticsFilter()

    def _where(
        self,
        *,
        date_expression: str,
        model_expression: str = "COALESCE(tm.name, sm.name)",
        required: list[str] | None = None,
    ) -> tuple[str, list[object]]:
        clauses: list[str] = list(required or [])
        params: list[object] = []
        filters = self.filters

        if filters.from_date is not None:
            clauses.append(f"substr({date_expression}, 1, 10) >= ?")
            params.append(filters.from_date.isoformat())
        if filters.to_date is not None:
            clauses.append(f"substr({date_expression}, 1, 10) <= ?")
            params.append(filters.to_date.isoformat())
        if filters.project is not None:
            clauses.append("p.name = ?")
            params.append(filters.project)
        if filters.model is not None:
            clauses.append(f"{model_expression} = ?")
            params.append(filters.model)
        if filters.source is not None:
            clauses.append("src.name = ?")
            params.append(filters.source)
        if filters.user is not None:
            clauses.append("COALESCE(u.display_name, u.stable_key) = ?")
            params.append(filters.user)
        if filters.machine is not None:
            clauses.append("COALESCE(mc.display_name, mc.stable_key) = ?")
            params.append(filters.machine)

        return (" WHERE " + " AND ".join(clauses) if clauses else "", params)

    @staticmethod
    def _nullable_float(row, key: str) -> float | None:
        if row is None or row[key] is None:
            return None
        return float(row[key])

    def summary(self) -> TeamAnalyticsSummary:
        session_where, session_params = self._where(
            date_expression="s.started_at",
            model_expression="sm.name",
        )
        token_where, token_params = self._where(date_expression="tu.timestamp")
        cost_where, cost_params = self._where(
            date_expression="COALESCE(c.period_start, s.started_at)",
            model_expression="COALESCE(cm.name, sm.name)",
        )

        with self.repository.database.connect() as conn:
            counts = conn.execute(
                """
                SELECT COUNT(DISTINCT u.id) AS users,
                       COUNT(DISTINCT mc.id) AS machines,
                       COUNT(DISTINCT s.id) AS sessions
                FROM sessions s
                JOIN sources src ON src.id=s.source_id
                LEFT JOIN projects p ON p.id=s.project_id
                LEFT JOIN models sm ON sm.id=s.model_id
                LEFT JOIN users u ON u.id=s.user_id
                LEFT JOIN machines mc ON mc.id=s.machine_id
                """ + session_where,
                session_params,
            ).fetchone()
            tokens = conn.execute(
                """
                SELECT COALESCE(SUM(tu.input_tokens), 0) AS input_tokens,
                       COALESCE(SUM(tu.cached_input_tokens), 0) AS cached_input_tokens,
                       COALESCE(SUM(tu.output_tokens), 0) AS output_tokens,
                       COALESCE(SUM(tu.total_tokens), 0) AS total_tokens
                FROM token_usage tu
                JOIN sessions s ON s.id=tu.session_id
                JOIN sources src ON src.id=s.source_id
                LEFT JOIN projects p ON p.id=s.project_id
                LEFT JOIN models tm ON tm.id=tu.model_id
                LEFT JOIN models sm ON sm.id=s.model_id
                LEFT JOIN users u ON u.id=s.user_id
                LEFT JOIN machines mc ON mc.id=s.machine_id
                """ + token_where,
                token_params,
            ).fetchone()
            costs = conn.execute(
                """
                SELECT SUM(c.observed_cost_usd) AS observed_cost_usd,
                       SUM(c.estimated_raw_cost_usd) AS estimated_raw_cost_usd
                FROM costs c
                LEFT JOIN sessions s ON s.id=c.session_id
                LEFT JOIN sources src ON src.id=s.source_id
                LEFT JOIN projects p ON p.id=s.project_id
                LEFT JOIN models cm ON cm.id=c.model_id
                LEFT JOIN models sm ON sm.id=s.model_id
                LEFT JOIN users u ON u.id=s.user_id
                LEFT JOIN machines mc ON mc.id=s.machine_id
                """ + cost_where,
                cost_params,
            ).fetchone()

        savings_rows = self.savings_by_user()
        savings = (
            sum(float(row["total_savings_usd"]) for row in savings_rows)
            if savings_rows
            else None
        )

        return TeamAnalyticsSummary(
            users=int(counts["users"] or 0),
            machines=int(counts["machines"] or 0),
            sessions=int(counts["sessions"] or 0),
            input_tokens=int(tokens["input_tokens"] or 0),
            cached_input_tokens=int(tokens["cached_input_tokens"] or 0),
            output_tokens=int(tokens["output_tokens"] or 0),
            total_tokens=int(tokens["total_tokens"] or 0),
            observed_cost_usd=self._nullable_float(costs, "observed_cost_usd"),
            estimated_raw_cost_usd=self._nullable_float(
                costs,
                "estimated_raw_cost_usd",
            ),
            total_savings_usd=savings,
        )

    def _usage_by(self, expression: str, alias: str) -> list[dict[str, Any]]:
        where, params = self._where(date_expression="tu.timestamp")
        with self.repository.database.connect() as conn:
            rows = conn.execute(
                f"""
                SELECT {expression} AS {alias},
                       COUNT(DISTINCT s.id) AS sessions,
                       COALESCE(SUM(tu.input_tokens), 0) AS input_tokens,
                       COALESCE(SUM(tu.cached_input_tokens), 0) AS cached_input_tokens,
                       COALESCE(SUM(tu.output_tokens), 0) AS output_tokens,
                       COALESCE(SUM(tu.total_tokens), 0) AS total_tokens
                FROM token_usage tu
                JOIN sessions s ON s.id=tu.session_id
                JOIN sources src ON src.id=s.source_id
                LEFT JOIN projects p ON p.id=s.project_id
                LEFT JOIN models tm ON tm.id=tu.model_id
                LEFT JOIN models sm ON sm.id=s.model_id
                LEFT JOIN users u ON u.id=s.user_id
                LEFT JOIN machines mc ON mc.id=s.machine_id
                {where}
                GROUP BY {expression}
                ORDER BY total_tokens DESC, {alias}
                """,
                params,
            ).fetchall()
        return [dict(row) for row in rows]

    def by_user(self) -> list[dict[str, Any]]:
        return self._usage_by(
            "COALESCE(u.display_name, u.stable_key, '(unknown)')",
            "user",
        )

    def by_machine(self) -> list[dict[str, Any]]:
        return self._usage_by(
            "COALESCE(mc.display_name, mc.stable_key, '(unknown)')",
            "machine",
        )

    def by_project(self) -> list[dict[str, Any]]:
        return self._usage_by("COALESCE(p.name, '(unknown)')", "project")

    def by_source(self) -> list[dict[str, Any]]:
        return self._usage_by("src.name", "source")

    def by_model(self) -> list[dict[str, Any]]:
        return self._usage_by(
            "COALESCE(tm.name, sm.name, '(unknown)')",
            "model",
        )

    def by_day(self) -> list[dict[str, Any]]:
        where, params = self._where(date_expression="tu.timestamp")
        with self.repository.database.connect() as conn:
            rows = conn.execute(
                """
                SELECT substr(tu.timestamp, 1, 10) AS day,
                       COUNT(DISTINCT s.id) AS sessions,
                       COALESCE(SUM(tu.input_tokens), 0) AS input_tokens,
                       COALESCE(SUM(tu.cached_input_tokens), 0) AS cached_input_tokens,
                       COALESCE(SUM(tu.output_tokens), 0) AS output_tokens,
                       COALESCE(SUM(tu.total_tokens), 0) AS total_tokens
                FROM token_usage tu
                JOIN sessions s ON s.id=tu.session_id
                JOIN sources src ON src.id=s.source_id
                LEFT JOIN projects p ON p.id=s.project_id
                LEFT JOIN models tm ON tm.id=tu.model_id
                LEFT JOIN models sm ON sm.id=s.model_id
                LEFT JOIN users u ON u.id=s.user_id
                LEFT JOIN machines mc ON mc.id=s.machine_id
                """ + where + """
                GROUP BY substr(tu.timestamp, 1, 10)
                ORDER BY day
                """,
                params,
            ).fetchall()
        return [dict(row) for row in rows]

    def _cost_by(self, expression: str, alias: str) -> list[dict[str, Any]]:
        where, params = self._where(
            date_expression="COALESCE(c.period_start, s.started_at)",
            model_expression="COALESCE(cm.name, sm.name)",
            required=[
                "(c.observed_cost_usd IS NOT NULL "
                "OR c.estimated_raw_cost_usd IS NOT NULL)"
            ],
        )
        with self.repository.database.connect() as conn:
            rows = conn.execute(
                f"""
                SELECT {expression} AS {alias},
                       SUM(c.observed_cost_usd) AS observed_cost_usd,
                       SUM(c.estimated_raw_cost_usd) AS estimated_raw_cost_usd
                FROM costs c
                JOIN sessions s ON s.id=c.session_id
                JOIN sources src ON src.id=s.source_id
                LEFT JOIN projects p ON p.id=s.project_id
                LEFT JOIN models cm ON cm.id=c.model_id
                LEFT JOIN models sm ON sm.id=s.model_id
                LEFT JOIN users u ON u.id=s.user_id
                LEFT JOIN machines mc ON mc.id=s.machine_id
                {where}
                GROUP BY {expression}
                ORDER BY COALESCE(SUM(c.observed_cost_usd), 0) +
                         COALESCE(SUM(c.estimated_raw_cost_usd), 0) DESC,
                         {alias}
                """,
                params,
            ).fetchall()
        return [dict(row) for row in rows]

    def cost_by_user(self) -> list[dict[str, Any]]:
        return self._cost_by(
            "COALESCE(u.display_name, u.stable_key, '(unknown)')",
            "user",
        )

    def cost_by_project(self) -> list[dict[str, Any]]:
        return self._cost_by("COALESCE(p.name, '(unknown)')", "project")

    def cost_by_source(self) -> list[dict[str, Any]]:
        return self._cost_by("src.name", "source")

    def cost_by_model(self) -> list[dict[str, Any]]:
        return self._cost_by(
            "COALESCE(cm.name, sm.name, '(unknown)')",
            "model",
        )

    def _savings_by(self, expression: str, alias: str) -> list[dict[str, Any]]:
        where, params = self._where(
            date_expression="s.started_at",
            model_expression="sm.name",
            required=["(cs.savings IS NOT NULL OR os.savings IS NOT NULL)"],
        )
        with self.repository.database.connect() as conn:
            rows = conn.execute(
                f"""
                WITH cost_savings AS (
                    SELECT session_id, SUM(total_savings_usd) AS savings
                    FROM costs
                    WHERE total_savings_usd IS NOT NULL
                    GROUP BY session_id
                ),
                optimizer_savings AS (
                    SELECT session_id,
                           SUM(
                               COALESCE(compression_savings_usd, 0) +
                               COALESCE(cache_savings_usd, 0)
                           ) AS savings
                    FROM optimizations
                    WHERE compression_savings_usd IS NOT NULL
                       OR cache_savings_usd IS NOT NULL
                    GROUP BY session_id
                )
                SELECT {expression} AS {alias},
                       SUM(
                           CASE
                               WHEN cs.savings IS NOT NULL THEN cs.savings
                               ELSE os.savings
                           END
                       ) AS total_savings_usd
                FROM sessions s
                JOIN sources src ON src.id=s.source_id
                LEFT JOIN projects p ON p.id=s.project_id
                LEFT JOIN models sm ON sm.id=s.model_id
                LEFT JOIN users u ON u.id=s.user_id
                LEFT JOIN machines mc ON mc.id=s.machine_id
                LEFT JOIN cost_savings cs ON cs.session_id=s.id
                LEFT JOIN optimizer_savings os ON os.session_id=s.id
                {where}
                GROUP BY {expression}
                ORDER BY total_savings_usd DESC, {alias}
                """,
                params,
            ).fetchall()
        return [dict(row) for row in rows]

    def savings_by_user(self) -> list[dict[str, Any]]:
        return self._savings_by(
            "COALESCE(u.display_name, u.stable_key, '(unknown)')",
            "user",
        )

    def savings_by_project(self) -> list[dict[str, Any]]:
        return self._savings_by("COALESCE(p.name, '(unknown)')", "project")

    def savings_by_source(self) -> list[dict[str, Any]]:
        return self._savings_by("src.name", "source")

    def savings_by_model(self) -> list[dict[str, Any]]:
        return self._savings_by("COALESCE(sm.name, '(unknown)')", "model")

    def data_quality(self) -> dict[str, Any]:
        session_where, session_params = self._where(
            date_expression="s.started_at",
            model_expression="sm.name",
        )
        token_where, token_params = self._where(date_expression="tu.timestamp")
        optimization_where, optimization_params = self._where(
            date_expression="op.timestamp",
            model_expression="COALESCE(om.name, sm.name)",
        )

        with self.repository.database.connect() as conn:
            identity_rows = conn.execute(
                """
                SELECT COALESCE(u.identity_confidence, 'unknown') AS confidence,
                       COUNT(DISTINCT u.id) AS users
                FROM sessions s
                JOIN sources src ON src.id=s.source_id
                LEFT JOIN projects p ON p.id=s.project_id
                LEFT JOIN models sm ON sm.id=s.model_id
                LEFT JOIN users u ON u.id=s.user_id
                LEFT JOIN machines mc ON mc.id=s.machine_id
                """ + session_where + """
                GROUP BY COALESCE(u.identity_confidence, 'unknown')
                ORDER BY confidence
                """,
                session_params,
            ).fetchall()
            model_tokens = conn.execute(
                """
                SELECT COALESCE(SUM(tu.total_tokens), 0) AS total_tokens,
                       COALESCE(
                           SUM(
                               CASE
                                   WHEN tu.model_id IS NULL
                                    AND s.model_id IS NULL
                                   THEN tu.total_tokens ELSE 0
                               END
                           ),
                           0
                       ) AS unknown_model_tokens
                FROM token_usage tu
                JOIN sessions s ON s.id=tu.session_id
                JOIN sources src ON src.id=s.source_id
                LEFT JOIN projects p ON p.id=s.project_id
                LEFT JOIN models tm ON tm.id=tu.model_id
                LEFT JOIN models sm ON sm.id=s.model_id
                LEFT JOIN users u ON u.id=s.user_id
                LEFT JOIN machines mc ON mc.id=s.machine_id
                """ + token_where,
                token_params,
            ).fetchone()
            coverage_rows = conn.execute(
                """
                SELECT src.name AS source,
                       COUNT(DISTINCT s.id) AS sessions,
                       CASE WHEN EXISTS(
                           SELECT 1
                           FROM token_usage tx
                           JOIN sessions sx ON sx.id=tx.session_id
                           WHERE sx.source_id=src.id
                       ) THEN 1 ELSE 0 END AS has_tokens,
                       CASE WHEN EXISTS(
                           SELECT 1
                           FROM token_usage tx
                           JOIN sessions sx ON sx.id=tx.session_id
                           WHERE sx.source_id=src.id
                             AND tx.cached_input_tokens IS NOT NULL
                       ) THEN 1 ELSE 0 END AS has_cache,
                       CASE WHEN EXISTS(
                           SELECT 1
                           FROM costs cx
                           JOIN sessions sx ON sx.id=cx.session_id
                           WHERE sx.source_id=src.id
                             AND (
                                 cx.observed_cost_usd IS NOT NULL
                                 OR cx.estimated_raw_cost_usd IS NOT NULL
                             )
                       ) THEN 1 ELSE 0 END AS has_cost
                FROM sessions s
                JOIN sources src ON src.id=s.source_id
                LEFT JOIN projects p ON p.id=s.project_id
                LEFT JOIN models sm ON sm.id=s.model_id
                LEFT JOIN users u ON u.id=s.user_id
                LEFT JOIN machines mc ON mc.id=s.machine_id
                """ + session_where + """
                GROUP BY src.id, src.name
                ORDER BY src.name
                """,
                session_params,
            ).fetchall()
            import_errors = int(
                conn.execute(
                    "SELECT COUNT(*) AS n FROM import_errors"
                ).fetchone()["n"]
            )
            confidence_rows = conn.execute(
                """
                SELECT COALESCE(
                           op.correlation_confidence,
                           'unknown'
                       ) AS confidence,
                       COUNT(*) AS events
                FROM optimizations op
                LEFT JOIN sessions s ON s.id=op.session_id
                LEFT JOIN sources src ON src.id=s.source_id
                LEFT JOIN projects p ON p.id=s.project_id
                LEFT JOIN models om ON om.id=op.model_id
                LEFT JOIN models sm ON sm.id=s.model_id
                LEFT JOIN users u ON u.id=s.user_id
                LEFT JOIN machines mc ON mc.id=s.machine_id
                """ + optimization_where + """
                GROUP BY COALESCE(op.correlation_confidence, 'unknown')
                ORDER BY confidence
                """,
                optimization_params,
            ).fetchall()

        total_tokens = int(model_tokens["total_tokens"] or 0)
        unknown_tokens = int(model_tokens["unknown_model_tokens"] or 0)
        return {
            "identity_confidence": [dict(row) for row in identity_rows],
            "unknown_model_tokens": unknown_tokens,
            "total_tokens": total_tokens,
            "unknown_model_ratio": (
                unknown_tokens / total_tokens if total_tokens else 0.0
            ),
            "source_coverage": [
                {
                    "source": row["source"],
                    "sessions": int(row["sessions"] or 0),
                    "has_tokens": bool(row["has_tokens"]),
                    "has_cache": bool(row["has_cache"]),
                    "has_cost": bool(row["has_cost"]),
                }
                for row in coverage_rows
            ],
            "import_errors": import_errors,
            "optimization_confidence": [
                dict(row) for row in confidence_rows
            ],
            "unsupported_provider_diagnostics": None,
            "diagnostics_note": "Não transportado pelo Team Bundle v1",
        }
