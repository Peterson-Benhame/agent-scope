from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from agentscope.analytics.filters import AnalyticsFilter
from agentscope.storage.repository import Repository


@dataclass(slots=True)
class AnalyticsSummary:
    sessions: int = 0
    turns: int = 0
    messages: int = 0
    tool_calls: int = 0
    input_tokens: int = 0
    cached_input_tokens: int = 0
    cache_write_input_tokens: int = 0
    output_tokens: int = 0
    reasoning_output_tokens: int = 0
    total_tokens: int = 0
    tokens_saved: int = 0
    compression_savings_usd: float = 0.0
    cache_savings_usd: float = 0.0
    total_savings_usd: float = 0.0
    observed_cost_usd: float | None = None
    estimated_raw_cost_usd: float | None = None

    @property
    def cache_ratio(self) -> float:
        return (self.cached_input_tokens / self.input_tokens) if self.input_tokens else 0.0


class AnalyticsService:
    def __init__(
        self,
        repository: Repository,
        filters: AnalyticsFilter | None = None,
    ):
        self.repository = repository
        self.filters = filters or AnalyticsFilter()

    @staticmethod
    def _nullable_sum(row, key: str):
        return row[key] if row and row[key] is not None else None

    @staticmethod
    def _percent_change(
        current: float | int | None,
        previous: float | int | None,
    ) -> float | None:
        if current is None or previous is None or float(previous) == 0.0:
            return None
        return ((float(current) - float(previous)) / abs(float(previous))) * 100.0

    def _where(
        self,
        *,
        date_expression: str | None = None,
        project_expression: str | None = None,
        model_expression: str | None = None,
        source_expression: str | None = None,
        user_expression: str | None = None,
        machine_expression: str | None = None,
        required: list[str] | None = None,
    ) -> tuple[str, list[object]]:
        clauses = list(required or [])
        params: list[object] = []

        if self.filters.from_date is not None and date_expression:
            clauses.append(f"substr({date_expression}, 1, 10) >= ?")
            params.append(self.filters.from_date.isoformat())
        if self.filters.to_date is not None and date_expression:
            clauses.append(f"substr({date_expression}, 1, 10) <= ?")
            params.append(self.filters.to_date.isoformat())
        if self.filters.project is not None and project_expression:
            clauses.append(f"{project_expression} = ?")
            params.append(self.filters.project)
        if self.filters.model is not None and model_expression:
            clauses.append(f"{model_expression} = ?")
            params.append(self.filters.model)
        if self.filters.source is not None and source_expression:
            clauses.append(f"{source_expression} = ?")
            params.append(self.filters.source)
        if self.filters.user is not None and user_expression:
            clauses.append(f"{user_expression} = ?")
            params.append(self.filters.user)
        if self.filters.machine is not None and machine_expression:
            clauses.append(f"{machine_expression} = ?")
            params.append(self.filters.machine)

        return (" WHERE " + " AND ".join(clauses) if clauses else "", params)

    def _count(
        self,
        conn,
        *,
        table_sql: str,
        date_expression: str,
        project_expression: str = "p.name",
        model_expression: str = "COALESCE(m.name, sm.name)",
        source_expression: str = "src.name",
        user_expression: str = "COALESCE(u.display_name, u.stable_key)",
        machine_expression: str = "COALESCE(mc.display_name, mc.stable_key)",
    ) -> int:
        where, params = self._where(
            date_expression=date_expression,
            project_expression=project_expression,
            model_expression=model_expression,
            source_expression=source_expression,
            user_expression=user_expression,
            machine_expression=machine_expression,
        )
        row = conn.execute(
            f"SELECT COUNT(*) AS n {table_sql}{where}",
            params,
        ).fetchone()
        return int(row["n"])

    def summary(self) -> AnalyticsSummary:
        user_expr = "COALESCE(u.display_name, u.stable_key)"
        machine_expr = "COALESCE(mc.display_name, mc.stable_key)"
        with self.repository.database.connect() as conn:
            sessions_where, sessions_params = self._where(
                date_expression="s.started_at",
                project_expression="p.name",
                model_expression="sm.name",
                source_expression="src.name",
                user_expression=user_expr,
                machine_expression=machine_expr,
            )
            sessions = int(
                conn.execute(
                    """
                    SELECT COUNT(*) AS n
                    FROM sessions s
                    LEFT JOIN projects p ON p.id=s.project_id
                    LEFT JOIN models sm ON sm.id=s.model_id
                    JOIN sources src ON src.id=s.source_id
                    LEFT JOIN users u ON u.id=s.user_id
                    LEFT JOIN machines mc ON mc.id=s.machine_id
                    """ + sessions_where,
                    sessions_params,
                ).fetchone()["n"]
            )

            turns = self._count(
                conn,
                table_sql="""
                    FROM turns tr
                    JOIN sessions s ON s.id=tr.session_id
                    LEFT JOIN projects p ON p.id=s.project_id
                    LEFT JOIN models m ON m.id=tr.model_id
                    LEFT JOIN models sm ON sm.id=s.model_id
                    JOIN sources src ON src.id=s.source_id
                    LEFT JOIN users u ON u.id=s.user_id
                    LEFT JOIN machines mc ON mc.id=s.machine_id
                """,
                date_expression="COALESCE(tr.started_at, s.started_at)",
            )
            messages = self._count(
                conn,
                table_sql="""
                    FROM messages msg
                    JOIN sessions s ON s.id=msg.session_id
                    LEFT JOIN projects p ON p.id=s.project_id
                    LEFT JOIN models sm ON sm.id=s.model_id
                    LEFT JOIN models m ON m.id=s.model_id
                    JOIN sources src ON src.id=s.source_id
                    LEFT JOIN users u ON u.id=s.user_id
                    LEFT JOIN machines mc ON mc.id=s.machine_id
                """,
                date_expression="msg.timestamp",
                model_expression="sm.name",
            )
            tool_calls = self._count(
                conn,
                table_sql="""
                    FROM tool_calls tc
                    JOIN sessions s ON s.id=tc.session_id
                    LEFT JOIN projects p ON p.id=s.project_id
                    LEFT JOIN models sm ON sm.id=s.model_id
                    LEFT JOIN models m ON m.id=s.model_id
                    JOIN sources src ON src.id=s.source_id
                    LEFT JOIN users u ON u.id=s.user_id
                    LEFT JOIN machines mc ON mc.id=s.machine_id
                """,
                date_expression="tc.timestamp",
                model_expression="sm.name",
            )

            token_where, token_params = self._where(
                date_expression="tu.timestamp",
                project_expression="p.name",
                model_expression="COALESCE(tm.name, sm.name)",
                source_expression="src.name",
                user_expression=user_expr,
                machine_expression=machine_expr,
            )
            tokens = conn.execute(
                """
                SELECT
                    COALESCE(SUM(tu.input_tokens), 0) AS input_tokens,
                    COALESCE(SUM(tu.cached_input_tokens), 0) AS cached_input_tokens,
                    COALESCE(SUM(tu.cache_write_input_tokens), 0) AS cache_write_input_tokens,
                    COALESCE(SUM(tu.output_tokens), 0) AS output_tokens,
                    COALESCE(SUM(tu.reasoning_output_tokens), 0) AS reasoning_output_tokens,
                    COALESCE(SUM(tu.total_tokens), 0) AS total_tokens
                FROM token_usage tu
                JOIN sessions s ON s.id=tu.session_id
                LEFT JOIN projects p ON p.id=s.project_id
                LEFT JOIN models tm ON tm.id=tu.model_id
                LEFT JOIN models sm ON sm.id=s.model_id
                JOIN sources src ON src.id=s.source_id
                LEFT JOIN users u ON u.id=s.user_id
                LEFT JOIN machines mc ON mc.id=s.machine_id
                """ + token_where,
                token_params,
            ).fetchone()

            optimization_where, optimization_params = self._where(
                date_expression="op.timestamp",
                project_expression="p.name",
                model_expression="COALESCE(om.name, sm.name)",
                source_expression="src.name",
                user_expression=user_expr,
                machine_expression=machine_expr,
            )
            optimization = conn.execute(
                """
                SELECT
                    COALESCE(SUM(op.tokens_saved), 0) AS tokens_saved,
                    COALESCE(SUM(op.compression_savings_usd), 0) AS compression_savings_usd,
                    COALESCE(SUM(op.cache_savings_usd), 0) AS cache_savings_usd
                FROM optimizations op
                LEFT JOIN sessions s ON s.id=op.session_id
                LEFT JOIN projects p ON p.id=s.project_id
                LEFT JOIN models om ON om.id=op.model_id
                LEFT JOIN models sm ON sm.id=s.model_id
                LEFT JOIN sources src ON src.id=s.source_id
                LEFT JOIN users u ON u.id=s.user_id
                LEFT JOIN machines mc ON mc.id=s.machine_id
                """ + optimization_where,
                optimization_params,
            ).fetchone()

            cost_where, cost_params = self._where(
                date_expression="c.period_start",
                project_expression="p.name",
                model_expression="COALESCE(cm.name, sm.name)",
                source_expression="src.name",
                user_expression=user_expr,
                machine_expression=machine_expr,
            )
            cost = conn.execute(
                """
                SELECT
                    SUM(c.observed_cost_usd) AS observed_cost_usd,
                    SUM(c.estimated_raw_cost_usd) AS estimated_raw_cost_usd,
                    SUM(c.compression_savings_usd) AS compression_savings_usd,
                    SUM(c.cache_savings_usd) AS cache_savings_usd,
                    SUM(c.total_savings_usd) AS total_savings_usd
                FROM costs c
                LEFT JOIN sessions s ON s.id=c.session_id
                LEFT JOIN projects p ON p.id=s.project_id
                LEFT JOIN models cm ON cm.id=c.model_id
                LEFT JOIN models sm ON sm.id=s.model_id
                LEFT JOIN sources src ON src.id=s.source_id
                LEFT JOIN users u ON u.id=s.user_id
                LEFT JOIN machines mc ON mc.id=s.machine_id
                """ + cost_where,
                cost_params,
            ).fetchone()

        compression = (
            float(cost["compression_savings_usd"])
            if cost and cost["compression_savings_usd"] is not None
            else float(optimization["compression_savings_usd"] or 0)
        )
        cache = (
            float(cost["cache_savings_usd"])
            if cost and cost["cache_savings_usd"] is not None
            else float(optimization["cache_savings_usd"] or 0)
        )
        total_savings = (
            float(cost["total_savings_usd"])
            if cost and cost["total_savings_usd"] is not None
            else compression + cache
        )
        return AnalyticsSummary(
            sessions=sessions,
            turns=turns,
            messages=messages,
            tool_calls=tool_calls,
            input_tokens=int(tokens["input_tokens"]),
            cached_input_tokens=int(tokens["cached_input_tokens"]),
            cache_write_input_tokens=int(tokens["cache_write_input_tokens"]),
            output_tokens=int(tokens["output_tokens"]),
            reasoning_output_tokens=int(tokens["reasoning_output_tokens"]),
            total_tokens=int(tokens["total_tokens"]),
            tokens_saved=int(optimization["tokens_saved"] or 0),
            compression_savings_usd=compression,
            cache_savings_usd=cache,
            total_savings_usd=total_savings,
            observed_cost_usd=self._nullable_sum(cost, "observed_cost_usd"),
            estimated_raw_cost_usd=self._nullable_sum(cost, "estimated_raw_cost_usd"),
        )

    def comparison(self) -> dict[str, float | None] | None:
        previous_filters = self.filters.previous_period()
        if previous_filters is None:
            return None

        current = self.summary()
        previous = AnalyticsService(self.repository, previous_filters).summary()
        return {
            "sessions_pct": self._percent_change(current.sessions, previous.sessions),
            "total_tokens_pct": self._percent_change(current.total_tokens, previous.total_tokens),
            "cache_ratio_pp": (current.cache_ratio - previous.cache_ratio) * 100.0,
            "observed_cost_usd_pct": self._percent_change(
                current.observed_cost_usd,
                previous.observed_cost_usd,
            ),
            "total_savings_usd_pct": self._percent_change(
                current.total_savings_usd,
                previous.total_savings_usd,
            ),
        }

    def _usage_dimension_where(self, date_expression: str) -> tuple[str, list[object]]:
        return self._where(
            date_expression=date_expression,
            project_expression="p.name",
            model_expression="COALESCE(tm.name, sm.name)",
            source_expression="src.name",
            user_expression="COALESCE(u.display_name, u.stable_key)",
            machine_expression="COALESCE(mc.display_name, mc.stable_key)",
        )

    def by_project(self) -> list[dict[str, Any]]:
        where, params = self._usage_dimension_where("tu.timestamp")
        with self.repository.database.connect() as conn:
            rows = conn.execute(
                """
                SELECT
                    COALESCE(p.name, '(unknown)') AS project,
                    COUNT(DISTINCT s.id) AS sessions,
                    COALESCE(SUM(tu.input_tokens), 0) AS input_tokens,
                    COALESCE(SUM(tu.cached_input_tokens), 0) AS cached_input_tokens,
                    COALESCE(SUM(tu.output_tokens), 0) AS output_tokens
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
                ORDER BY input_tokens DESC, project
                """,
                params,
            ).fetchall()
        return [dict(row) for row in rows]

    def by_model(self) -> list[dict[str, Any]]:
        where, params = self._usage_dimension_where("tu.timestamp")
        with self.repository.database.connect() as conn:
            rows = conn.execute(
                """
                SELECT
                    COALESCE(tm.name, sm.name, '(unknown)') AS model,
                    COUNT(DISTINCT tu.session_id) AS sessions,
                    COALESCE(SUM(tu.input_tokens), 0) AS input_tokens,
                    COALESCE(SUM(tu.cached_input_tokens), 0) AS cached_input_tokens,
                    COALESCE(SUM(tu.output_tokens), 0) AS output_tokens
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
                ORDER BY input_tokens DESC, model
                """,
                params,
            ).fetchall()
        return [dict(row) for row in rows]

    def _by_identity(self, dimension: str) -> list[dict[str, Any]]:
        if dimension not in {"user", "machine"}:
            raise ValueError(f"Unsupported identity dimension: {dimension}")
        id_column = "s.user_id" if dimension == "user" else "s.machine_id"
        table = "users" if dimension == "user" else "machines"
        alias = "u" if dimension == "user" else "mc"
        label = f"COALESCE({alias}.display_name, {alias}.stable_key)"
        where, params = self._where(
            date_expression="s.started_at",
            project_expression="p.name",
            model_expression="sm.name",
            source_expression="src.name",
            user_expression="COALESCE(u.display_name, u.stable_key)",
            machine_expression="COALESCE(mc.display_name, mc.stable_key)",
            required=[f"{id_column} IS NOT NULL"],
        )
        key_column = "user_id" if dimension == "user" else "machine_id"
        with self.repository.database.connect() as conn:
            rows = conn.execute(
                f"""
                WITH scoped AS (
                    SELECT s.id, s.user_id, s.machine_id
                    FROM sessions s
                    LEFT JOIN projects p ON p.id=s.project_id
                    LEFT JOIN models sm ON sm.id=s.model_id
                    JOIN sources src ON src.id=s.source_id
                    LEFT JOIN users u ON u.id=s.user_id
                    LEFT JOIN machines mc ON mc.id=s.machine_id
                    {where}
                ),
                token_totals AS (
                    SELECT sc.{key_column} AS identity_id,
                           COALESCE(SUM(tu.input_tokens), 0) AS input_tokens,
                           COALESCE(SUM(tu.cached_input_tokens), 0) AS cached_input_tokens,
                           COALESCE(SUM(tu.output_tokens), 0) AS output_tokens,
                           COALESCE(SUM(tu.total_tokens), 0) AS total_tokens
                    FROM scoped sc
                    LEFT JOIN token_usage tu ON tu.session_id=sc.id
                    GROUP BY sc.{key_column}
                ),
                cost_totals AS (
                    SELECT sc.{key_column} AS identity_id,
                           SUM(c.observed_cost_usd) AS observed_cost_usd
                    FROM scoped sc
                    LEFT JOIN costs c ON c.session_id=sc.id
                    GROUP BY sc.{key_column}
                ),
                session_totals AS (
                    SELECT {key_column} AS identity_id, COUNT(*) AS sessions
                    FROM scoped
                    GROUP BY {key_column}
                )
                SELECT {label} AS {dimension},
                       st.sessions,
                       tt.input_tokens,
                       tt.cached_input_tokens,
                       tt.output_tokens,
                       tt.total_tokens,
                       ct.observed_cost_usd
                FROM session_totals st
                JOIN {table} {alias} ON {alias}.id=st.identity_id
                JOIN token_totals tt ON tt.identity_id=st.identity_id
                LEFT JOIN cost_totals ct ON ct.identity_id=st.identity_id
                ORDER BY tt.input_tokens DESC, {dimension}
                """,
                params,
            ).fetchall()
        return [dict(row) for row in rows]

    def by_user(self) -> list[dict[str, Any]]:
        return self._by_identity("user")

    def by_machine(self) -> list[dict[str, Any]]:
        return self._by_identity("machine")

    def by_agent(self) -> list[dict[str, Any]]:
        where, params = self._where(
            date_expression="COALESCE(sa.started_at, s.started_at)",
            project_expression="p.name",
            model_expression="sm.name",
            source_expression="src.name",
            user_expression="COALESCE(u.display_name, u.stable_key)",
            machine_expression="COALESCE(mc.display_name, mc.stable_key)",
        )
        with self.repository.database.connect() as conn:
            rows = conn.execute(
                """
                SELECT a.name AS agent, a.type AS agent_type,
                       COUNT(DISTINCT sa.session_id) AS sessions,
                       COUNT(*) AS evidence_count
                FROM session_agents sa
                JOIN agents a ON a.id=sa.agent_id
                JOIN sessions s ON s.id=sa.session_id
                LEFT JOIN projects p ON p.id=s.project_id
                LEFT JOIN models sm ON sm.id=s.model_id
                JOIN sources src ON src.id=s.source_id
                LEFT JOIN users u ON u.id=s.user_id
                LEFT JOIN machines mc ON mc.id=s.machine_id
                """ + where + """
                GROUP BY a.id, a.name, a.type
                ORDER BY sessions DESC, agent
                """,
                params,
            ).fetchall()
        return [dict(row) for row in rows]

    def by_skill(self) -> list[dict[str, Any]]:
        where, params = self._where(
            date_expression="COALESCE(ss.first_seen_at, s.started_at)",
            project_expression="p.name",
            model_expression="sm.name",
            source_expression="src.name",
            user_expression="COALESCE(u.display_name, u.stable_key)",
            machine_expression="COALESCE(mc.display_name, mc.stable_key)",
        )
        with self.repository.database.connect() as conn:
            rows = conn.execute(
                """
                SELECT sk.name AS skill, ss.usage_type,
                       COUNT(DISTINCT ss.session_id) AS sessions,
                       COUNT(*) AS evidence_count
                FROM session_skills ss
                JOIN skills sk ON sk.id=ss.skill_id
                JOIN sessions s ON s.id=ss.session_id
                LEFT JOIN projects p ON p.id=s.project_id
                LEFT JOIN models sm ON sm.id=s.model_id
                JOIN sources src ON src.id=s.source_id
                LEFT JOIN users u ON u.id=s.user_id
                LEFT JOIN machines mc ON mc.id=s.machine_id
                """ + where + """
                GROUP BY sk.id, sk.name, ss.usage_type
                ORDER BY skill, usage_type
                """,
                params,
            ).fetchall()
        return [dict(row) for row in rows]

    def by_tool(self) -> list[dict[str, Any]]:
        where, params = self._where(
            date_expression="tc.timestamp",
            project_expression="p.name",
            model_expression="sm.name",
            source_expression="src.name",
            user_expression="COALESCE(u.display_name, u.stable_key)",
            machine_expression="COALESCE(mc.display_name, mc.stable_key)",
        )
        with self.repository.database.connect() as conn:
            rows = conn.execute(
                """
                SELECT t.name AS tool, t.category,
                       COUNT(*) AS calls,
                       SUM(CASE WHEN tc.status IN ('completed', 'success') THEN 1 ELSE 0 END) AS successful_calls,
                       AVG(tc.duration_ms) AS average_duration_ms,
                       COALESCE(SUM(tc.input_size), 0) AS input_size,
                       COALESCE(SUM(tc.output_size), 0) AS output_size
                FROM tool_calls tc
                JOIN tools t ON t.id=tc.tool_id
                JOIN sessions s ON s.id=tc.session_id
                LEFT JOIN projects p ON p.id=s.project_id
                LEFT JOIN models sm ON sm.id=s.model_id
                JOIN sources src ON src.id=s.source_id
                LEFT JOIN users u ON u.id=s.user_id
                LEFT JOIN machines mc ON mc.id=s.machine_id
                """ + where + """
                GROUP BY t.id, t.name, t.category
                ORDER BY calls DESC, tool
                """,
                params,
            ).fetchall()
        return [dict(row) for row in rows]

    def by_day(self) -> list[dict[str, Any]]:
        where, params = self._usage_dimension_where("tu.timestamp")
        with self.repository.database.connect() as conn:
            rows = conn.execute(
                """
                SELECT substr(tu.timestamp, 1, 10) AS day,
                       COALESCE(SUM(tu.input_tokens), 0) AS input_tokens,
                       COALESCE(SUM(tu.cached_input_tokens), 0) AS cached_input_tokens,
                       COALESCE(SUM(tu.output_tokens), 0) AS output_tokens
                FROM token_usage tu
                JOIN sessions s ON s.id=tu.session_id
                LEFT JOIN projects p ON p.id=s.project_id
                LEFT JOIN models tm ON tm.id=tu.model_id
                LEFT JOIN models sm ON sm.id=s.model_id
                JOIN sources src ON src.id=s.source_id
                LEFT JOIN users u ON u.id=s.user_id
                LEFT JOIN machines mc ON mc.id=s.machine_id
                """ + where + """
                GROUP BY substr(tu.timestamp, 1, 10)
                ORDER BY day
                """,
                params,
            ).fetchall()
        return [dict(row) for row in rows]

    def optimizer_summary(self) -> list[dict[str, Any]]:
        where, params = self._where(
            date_expression="op.timestamp",
            project_expression="p.name",
            model_expression="COALESCE(om.name, sm.name)",
            source_expression="src.name",
            user_expression="COALESCE(u.display_name, u.stable_key)",
            machine_expression="COALESCE(mc.display_name, mc.stable_key)",
        )
        with self.repository.database.connect() as conn:
            rows = conn.execute(
                """
                SELECT o.name AS optimizer,
                       COUNT(op.id) AS events,
                       COALESCE(SUM(op.original_tokens), 0) AS original_tokens,
                       COALESCE(SUM(op.optimized_tokens), 0) AS optimized_tokens,
                       COALESCE(SUM(op.tokens_saved), 0) AS tokens_saved,
                       COALESCE(SUM(op.compression_savings_usd), 0) AS compression_savings_usd
                FROM optimizations op
                JOIN optimizers o ON o.id=op.optimizer_id
                LEFT JOIN sessions s ON s.id=op.session_id
                LEFT JOIN projects p ON p.id=s.project_id
                LEFT JOIN models om ON om.id=op.model_id
                LEFT JOIN models sm ON sm.id=s.model_id
                LEFT JOIN sources src ON src.id=s.source_id
                LEFT JOIN users u ON u.id=s.user_id
                LEFT JOIN machines mc ON mc.id=s.machine_id
                """ + where + """
                GROUP BY o.id, o.name
                ORDER BY optimizer
                """,
                params,
            ).fetchall()
        return [dict(row) for row in rows]

    def savings_by_day(self) -> list[dict[str, Any]]:
        where, params = self._where(
            date_expression="op.timestamp",
            project_expression="p.name",
            model_expression="COALESCE(om.name, sm.name)",
            source_expression="src.name",
            user_expression="COALESCE(u.display_name, u.stable_key)",
            machine_expression="COALESCE(mc.display_name, mc.stable_key)",
        )
        with self.repository.database.connect() as conn:
            rows = conn.execute(
                """
                SELECT substr(op.timestamp, 1, 10) AS day,
                       COALESCE(SUM(op.tokens_saved), 0) AS tokens_saved,
                       COALESCE(SUM(op.compression_savings_usd), 0) AS compression_savings_usd,
                       COALESCE(SUM(op.cache_savings_usd), 0) AS cache_savings_usd
                FROM optimizations op
                LEFT JOIN sessions s ON s.id=op.session_id
                LEFT JOIN projects p ON p.id=s.project_id
                LEFT JOIN models om ON om.id=op.model_id
                LEFT JOIN models sm ON sm.id=s.model_id
                LEFT JOIN sources src ON src.id=s.source_id
                LEFT JOIN users u ON u.id=s.user_id
                LEFT JOIN machines mc ON mc.id=s.machine_id
                """ + where + """
                GROUP BY substr(op.timestamp, 1, 10)
                ORDER BY day
                """,
                params,
            ).fetchall()
        return [dict(row) for row in rows]

    def cost_by_day(self) -> list[dict[str, Any]]:
        where, params = self._where(
            date_expression="c.period_start",
            project_expression="p.name",
            model_expression="COALESCE(cm.name, sm.name)",
            source_expression="src.name",
            user_expression="COALESCE(u.display_name, u.stable_key)",
            machine_expression="COALESCE(mc.display_name, mc.stable_key)",
            required=["c.period_start IS NOT NULL"],
        )
        with self.repository.database.connect() as conn:
            rows = conn.execute(
                """
                SELECT substr(c.period_start, 1, 10) AS day,
                       SUM(c.observed_cost_usd) AS observed_cost_usd,
                       SUM(c.estimated_raw_cost_usd) AS estimated_raw_cost_usd
                FROM costs c
                LEFT JOIN sessions s ON s.id=c.session_id
                LEFT JOIN projects p ON p.id=s.project_id
                LEFT JOIN models cm ON cm.id=c.model_id
                LEFT JOIN models sm ON sm.id=s.model_id
                LEFT JOIN sources src ON src.id=s.source_id
                LEFT JOIN users u ON u.id=s.user_id
                LEFT JOIN machines mc ON mc.id=s.machine_id
                """ + where + """
                GROUP BY substr(c.period_start, 1, 10)
                ORDER BY day
                """,
                params,
            ).fetchall()
        return [dict(row) for row in rows]

    def data_quality(self) -> dict[str, object]:
        with self.repository.database.connect() as conn:
            import_errors = int(
                conn.execute("SELECT COUNT(*) AS n FROM import_errors").fetchone()["n"]
            )
            unknown_model_sessions = int(
                conn.execute(
                    "SELECT COUNT(*) AS n FROM sessions WHERE model_id IS NULL"
                ).fetchone()["n"]
            )
            token_row = conn.execute(
                """
                SELECT
                    COALESCE(SUM(tu.input_tokens), 0) AS total_input_tokens,
                    COALESCE(SUM(
                        CASE WHEN COALESCE(tu.model_id, s.model_id) IS NULL
                             THEN tu.input_tokens ELSE 0 END
                    ), 0) AS unknown_input_tokens
                FROM token_usage tu
                JOIN sessions s ON s.id=tu.session_id
                """
            ).fetchone()
            total_input_tokens = int(token_row["total_input_tokens"] or 0)
            unknown_input_tokens = int(token_row["unknown_input_tokens"] or 0)
            confidence_rows = conn.execute(
                """
                SELECT correlation_confidence, COUNT(*) AS n
                FROM optimizations
                GROUP BY correlation_confidence
                ORDER BY correlation_confidence
                """
            ).fetchall()
            skill_evidence_rows = int(
                conn.execute("SELECT COUNT(*) AS n FROM session_skills").fetchone()["n"]
            )
            agent_evidence_rows = int(
                conn.execute("SELECT COUNT(*) AS n FROM session_agents").fetchone()["n"]
            )

        return {
            "import_errors": import_errors,
            "unknown_model_sessions": unknown_model_sessions,
            "unknown_model_token_share": (
                unknown_input_tokens / total_input_tokens
                if total_input_tokens
                else None
            ),
            "optimization_confidence": {
                str(row["correlation_confidence"]): int(row["n"])
                for row in confidence_rows
            },
            "skill_evidence_rows": skill_evidence_rows,
            "agent_evidence_rows": agent_evidence_rows,
        }
