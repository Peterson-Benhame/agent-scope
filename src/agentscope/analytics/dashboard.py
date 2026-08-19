from __future__ import annotations

from typing import Any

from agentscope.analytics.filters import AnalyticsFilter
from agentscope.analytics.service import AnalyticsService, AnalyticsSummary
from agentscope.storage.repository import Repository


class DashboardAnalyticsService(AnalyticsService):
    """Filter-aware aggregates used only by the VS Code dashboard contract."""

    def __init__(
        self,
        repository: Repository,
        filters: AnalyticsFilter | None = None,
    ) -> None:
        super().__init__(repository, filters)

    def _where(
        self,
        *,
        date_expression: str | None = None,
        **kwargs: Any,
    ) -> tuple[str, list[object]]:
        local_expression = (
            self.filters.local_date_expression(date_expression)
            if date_expression
            else None
        )
        return super()._where(date_expression=local_expression, **kwargs)

    def _usage_where(self, date_expression: str) -> tuple[str, list[object]]:
        return self._where(
            date_expression=date_expression,
            project_expression="p.name",
            model_expression="COALESCE(tm.name, sm.name)",
            source_expression="src.name",
            user_expression="COALESCE(u.display_name, u.stable_key)",
            machine_expression="COALESCE(mc.display_name, mc.stable_key)",
        )

    def _active_session_ids(self) -> set[int]:
        session_where, session_params = self._where(
            date_expression="s.started_at",
            project_expression="p.name",
            model_expression="sm.name",
            source_expression="src.name",
            user_expression="COALESCE(u.display_name, u.stable_key)",
            machine_expression="COALESCE(mc.display_name, mc.stable_key)",
            required=["s.started_at IS NOT NULL"],
        )
        usage_where, usage_params = self._usage_where("tu.timestamp")

        with self.repository.database.connect() as conn:
            started_rows = conn.execute(
                """
                SELECT DISTINCT s.id AS session_id
                FROM sessions s
                LEFT JOIN projects p ON p.id=s.project_id
                LEFT JOIN models sm ON sm.id=s.model_id
                JOIN sources src ON src.id=s.source_id
                LEFT JOIN users u ON u.id=s.user_id
                LEFT JOIN machines mc ON mc.id=s.machine_id
                """ + session_where,
                session_params,
            ).fetchall()
            usage_rows = conn.execute(
                """
                SELECT DISTINCT s.id AS session_id
                FROM token_usage tu
                JOIN sessions s ON s.id=tu.session_id
                LEFT JOIN projects p ON p.id=s.project_id
                LEFT JOIN models tm ON tm.id=tu.model_id
                LEFT JOIN models sm ON sm.id=s.model_id
                JOIN sources src ON src.id=s.source_id
                LEFT JOIN users u ON u.id=s.user_id
                LEFT JOIN machines mc ON mc.id=s.machine_id
                """ + usage_where,
                usage_params,
            ).fetchall()

        return {
            int(row["session_id"])
            for row in [*started_rows, *usage_rows]
        }

    def summary(self) -> AnalyticsSummary:
        summary = super().summary()
        summary.sessions = len(self._active_session_ids())
        return summary

    def by_project(self) -> list[dict[str, Any]]:
        where, params = self._usage_where("tu.timestamp")
        with self.repository.database.connect() as conn:
            rows = conn.execute(
                """
                SELECT COALESCE(p.name, '(unknown)') AS project,
                       COUNT(DISTINCT s.id) AS sessions,
                       COALESCE(SUM(tu.total_tokens), 0) AS total_tokens
                FROM token_usage tu
                JOIN sessions s ON s.id=tu.session_id
                LEFT JOIN projects p ON p.id=s.project_id
                LEFT JOIN models tm ON tm.id=tu.model_id
                LEFT JOIN models sm ON sm.id=s.model_id
                JOIN sources src ON src.id=s.source_id
                LEFT JOIN users u ON u.id=s.user_id
                LEFT JOIN machines mc ON mc.id=s.machine_id
                """ + where + """
                GROUP BY COALESCE(p.name, '(unknown)')
                ORDER BY total_tokens DESC, project
                """,
                params,
            ).fetchall()
        return [dict(row) for row in rows]

    def by_model(self) -> list[dict[str, Any]]:
        where, params = self._usage_where("tu.timestamp")
        with self.repository.database.connect() as conn:
            rows = conn.execute(
                """
                SELECT COALESCE(tm.name, sm.name, '(unknown)') AS model,
                       COUNT(DISTINCT s.id) AS sessions,
                       COALESCE(SUM(tu.total_tokens), 0) AS total_tokens
                FROM token_usage tu
                JOIN sessions s ON s.id=tu.session_id
                LEFT JOIN projects p ON p.id=s.project_id
                LEFT JOIN models tm ON tm.id=tu.model_id
                LEFT JOIN models sm ON sm.id=s.model_id
                JOIN sources src ON src.id=s.source_id
                LEFT JOIN users u ON u.id=s.user_id
                LEFT JOIN machines mc ON mc.id=s.machine_id
                """ + where + """
                GROUP BY COALESCE(tm.name, sm.name, '(unknown)')
                ORDER BY total_tokens DESC, model
                """,
                params,
            ).fetchall()
        return [dict(row) for row in rows]

    def by_source(self) -> list[dict[str, Any]]:
        where, params = self._usage_where("tu.timestamp")
        with self.repository.database.connect() as conn:
            rows = conn.execute(
                """
                SELECT src.name AS source,
                       COUNT(DISTINCT s.id) AS sessions,
                       COALESCE(SUM(tu.total_tokens), 0) AS total_tokens
                FROM token_usage tu
                JOIN sessions s ON s.id=tu.session_id
                LEFT JOIN projects p ON p.id=s.project_id
                LEFT JOIN models tm ON tm.id=tu.model_id
                LEFT JOIN models sm ON sm.id=s.model_id
                JOIN sources src ON src.id=s.source_id
                LEFT JOIN users u ON u.id=s.user_id
                LEFT JOIN machines mc ON mc.id=s.machine_id
                """ + where + """
                GROUP BY src.name
                ORDER BY total_tokens DESC, source
                """,
                params,
            ).fetchall()
        return [dict(row) for row in rows]

    @staticmethod
    def _known_savings(
        cost_row: dict[str, Any] | None,
        optimization_row: dict[str, Any] | None,
    ) -> float | None:
        if cost_row is not None and cost_row.get("total_savings_usd") is not None:
            return float(cost_row["total_savings_usd"])

        if cost_row is not None:
            compression = cost_row.get("compression_savings_usd")
            cache = cost_row.get("cache_savings_usd")
            if compression is not None or cache is not None:
                return float(compression or 0.0) + float(cache or 0.0)

        if optimization_row is not None:
            compression = optimization_row.get("compression_savings_usd")
            cache = optimization_row.get("cache_savings_usd")
            if compression is not None or cache is not None:
                return float(compression or 0.0) + float(cache or 0.0)

        return None

    def by_day(self) -> list[dict[str, Any]]:
        session_day = self.filters.local_date_expression("s.started_at")
        usage_day = self.filters.local_date_expression("tu.timestamp")
        cost_day = self.filters.local_date_expression("c.period_start")
        optimization_day = self.filters.local_date_expression("op.timestamp")

        session_where, session_params = self._where(
            date_expression="s.started_at",
            project_expression="p.name",
            model_expression="sm.name",
            source_expression="src.name",
            user_expression="COALESCE(u.display_name, u.stable_key)",
            machine_expression="COALESCE(mc.display_name, mc.stable_key)",
            required=["s.started_at IS NOT NULL"],
        )
        usage_where, usage_params = self._usage_where("tu.timestamp")
        cost_where, cost_params = self._where(
            date_expression="c.period_start",
            project_expression="p.name",
            model_expression="COALESCE(cm.name, sm.name)",
            source_expression="src.name",
            user_expression="COALESCE(u.display_name, u.stable_key)",
            machine_expression="COALESCE(mc.display_name, mc.stable_key)",
            required=["c.period_start IS NOT NULL"],
        )
        optimization_where, optimization_params = self._where(
            date_expression="op.timestamp",
            project_expression="p.name",
            model_expression="COALESCE(om.name, sm.name)",
            source_expression="src.name",
            user_expression="COALESCE(u.display_name, u.stable_key)",
            machine_expression="COALESCE(mc.display_name, mc.stable_key)",
        )

        with self.repository.database.connect() as conn:
            started_session_rows = conn.execute(
                f"""
                SELECT {session_day} AS day,
                       s.id AS session_id
                FROM sessions s
                LEFT JOIN projects p ON p.id=s.project_id
                LEFT JOIN models sm ON sm.id=s.model_id
                JOIN sources src ON src.id=s.source_id
                LEFT JOIN users u ON u.id=s.user_id
                LEFT JOIN machines mc ON mc.id=s.machine_id
                """ + session_where,
                session_params,
            ).fetchall()

            usage_session_rows = conn.execute(
                f"""
                SELECT DISTINCT {usage_day} AS day,
                       s.id AS session_id
                FROM token_usage tu
                JOIN sessions s ON s.id=tu.session_id
                LEFT JOIN projects p ON p.id=s.project_id
                LEFT JOIN models tm ON tm.id=tu.model_id
                LEFT JOIN models sm ON sm.id=s.model_id
                JOIN sources src ON src.id=s.source_id
                LEFT JOIN users u ON u.id=s.user_id
                LEFT JOIN machines mc ON mc.id=s.machine_id
                """ + usage_where,
                usage_params,
            ).fetchall()

            usage_rows = conn.execute(
                f"""
                SELECT {usage_day} AS day,
                       COALESCE(SUM(tu.input_tokens), 0) AS input_tokens,
                       COALESCE(SUM(tu.cached_input_tokens), 0) AS cached_input_tokens,
                       COALESCE(SUM(tu.total_tokens), 0) AS total_tokens
                FROM token_usage tu
                JOIN sessions s ON s.id=tu.session_id
                LEFT JOIN projects p ON p.id=s.project_id
                LEFT JOIN models tm ON tm.id=tu.model_id
                LEFT JOIN models sm ON sm.id=s.model_id
                JOIN sources src ON src.id=s.source_id
                LEFT JOIN users u ON u.id=s.user_id
                LEFT JOIN machines mc ON mc.id=s.machine_id
                """ + usage_where + f"""
                GROUP BY {usage_day}
                ORDER BY day
                """,
                usage_params,
            ).fetchall()

            cost_rows = conn.execute(
                f"""
                SELECT {cost_day} AS day,
                       SUM(c.observed_cost_usd) AS observed_cost_usd,
                       SUM(c.estimated_raw_cost_usd) AS estimated_cost_usd,
                       SUM(c.total_savings_usd) AS total_savings_usd,
                       SUM(c.compression_savings_usd) AS compression_savings_usd,
                       SUM(c.cache_savings_usd) AS cache_savings_usd
                FROM costs c
                LEFT JOIN sessions s ON s.id=c.session_id
                LEFT JOIN projects p ON p.id=s.project_id
                LEFT JOIN models cm ON cm.id=c.model_id
                LEFT JOIN models sm ON sm.id=s.model_id
                LEFT JOIN sources src ON src.id=s.source_id
                LEFT JOIN users u ON u.id=s.user_id
                LEFT JOIN machines mc ON mc.id=s.machine_id
                """ + cost_where + f"""
                GROUP BY {cost_day}
                ORDER BY day
                """,
                cost_params,
            ).fetchall()

            optimization_rows = conn.execute(
                f"""
                SELECT {optimization_day} AS day,
                       SUM(op.compression_savings_usd) AS compression_savings_usd,
                       SUM(op.cache_savings_usd) AS cache_savings_usd
                FROM optimizations op
                LEFT JOIN sessions s ON s.id=op.session_id
                LEFT JOIN projects p ON p.id=s.project_id
                LEFT JOIN models om ON om.id=op.model_id
                LEFT JOIN models sm ON sm.id=s.model_id
                LEFT JOIN sources src ON src.id=s.source_id
                LEFT JOIN users u ON u.id=s.user_id
                LEFT JOIN machines mc ON mc.id=s.machine_id
                """ + optimization_where + f"""
                GROUP BY {optimization_day}
                ORDER BY day
                """,
                optimization_params,
            ).fetchall()

        active_sessions_by_day: dict[str, set[int]] = {}
        for row in [*started_session_rows, *usage_session_rows]:
            day = str(row["day"])
            active_sessions_by_day.setdefault(day, set()).add(int(row["session_id"]))

        sessions = {
            day: len(session_ids)
            for day, session_ids in active_sessions_by_day.items()
        }
        usage = {str(row["day"]): dict(row) for row in usage_rows}
        costs = {str(row["day"]): dict(row) for row in cost_rows}
        optimizations = {str(row["day"]): dict(row) for row in optimization_rows}
        days = sorted(set(sessions) | set(usage) | set(costs) | set(optimizations))

        result: list[dict[str, Any]] = []
        for day in days:
            usage_row = usage.get(day)
            cost_row = costs.get(day)
            optimization_row = optimizations.get(day)
            input_tokens = int(usage_row["input_tokens"] or 0) if usage_row else 0
            cached_tokens = int(usage_row["cached_input_tokens"] or 0) if usage_row else 0
            result.append(
                {
                    "date": day,
                    "sessions": sessions.get(day, 0),
                    "total_tokens": int(usage_row["total_tokens"] or 0) if usage_row else 0,
                    "cache_ratio": cached_tokens / input_tokens if input_tokens else None,
                    "observed_cost_usd": (
                        float(cost_row["observed_cost_usd"])
                        if cost_row and cost_row["observed_cost_usd"] is not None
                        else None
                    ),
                    "estimated_cost_usd": (
                        float(cost_row["estimated_cost_usd"])
                        if cost_row and cost_row["estimated_cost_usd"] is not None
                        else None
                    ),
                    "estimated_savings_usd": self._known_savings(
                        cost_row,
                        optimization_row,
                    ),
                }
            )
        return result