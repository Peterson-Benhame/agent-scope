from __future__ import annotations

from dataclasses import dataclass
from typing import Any

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
    def __init__(self, repository: Repository):
        self.repository = repository

    @staticmethod
    def _nullable_sum(row, key: str):
        return row[key] if row and row[key] is not None else None

    def summary(self) -> AnalyticsSummary:
        with self.repository.database.connect() as conn:
            counts = {
                name: conn.execute(f"SELECT COUNT(*) AS n FROM {name}").fetchone()["n"]
                for name in ("sessions", "turns", "messages", "tool_calls")
            }
            tokens = conn.execute(
                """
                SELECT
                    COALESCE(SUM(input_tokens), 0) AS input_tokens,
                    COALESCE(SUM(cached_input_tokens), 0) AS cached_input_tokens,
                    COALESCE(SUM(cache_write_input_tokens), 0) AS cache_write_input_tokens,
                    COALESCE(SUM(output_tokens), 0) AS output_tokens,
                    COALESCE(SUM(reasoning_output_tokens), 0) AS reasoning_output_tokens,
                    COALESCE(SUM(total_tokens), 0) AS total_tokens
                FROM token_usage
                """
            ).fetchone()
            optimization = conn.execute(
                """
                SELECT
                    COALESCE(SUM(tokens_saved), 0) AS tokens_saved,
                    COALESCE(SUM(compression_savings_usd), 0) AS compression_savings_usd,
                    COALESCE(SUM(cache_savings_usd), 0) AS cache_savings_usd
                FROM optimizations
                """
            ).fetchone()
            cost = conn.execute(
                """
                SELECT
                    SUM(observed_cost_usd) AS observed_cost_usd,
                    SUM(estimated_raw_cost_usd) AS estimated_raw_cost_usd,
                    SUM(compression_savings_usd) AS compression_savings_usd,
                    SUM(cache_savings_usd) AS cache_savings_usd,
                    SUM(total_savings_usd) AS total_savings_usd
                FROM costs
                """
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
            sessions=int(counts["sessions"]),
            turns=int(counts["turns"]),
            messages=int(counts["messages"]),
            tool_calls=int(counts["tool_calls"]),
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

    def by_project(self) -> list[dict[str, Any]]:
        with self.repository.database.connect() as conn:
            rows = conn.execute(
                """
                SELECT
                    COALESCE(p.name, '(unknown)') AS project,
                    COUNT(DISTINCT s.id) AS sessions,
                    COALESCE(SUM(tu.input_tokens), 0) AS input_tokens,
                    COALESCE(SUM(tu.cached_input_tokens), 0) AS cached_input_tokens,
                    COALESCE(SUM(tu.output_tokens), 0) AS output_tokens
                FROM sessions s
                LEFT JOIN projects p ON p.id=s.project_id
                LEFT JOIN token_usage tu ON tu.session_id=s.id
                GROUP BY COALESCE(p.name, '(unknown)')
                ORDER BY input_tokens DESC, project
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def by_model(self) -> list[dict[str, Any]]:
        with self.repository.database.connect() as conn:
            rows = conn.execute(
                """
                SELECT
                    COALESCE(m.name, '(unknown)') AS model,
                    COUNT(DISTINCT tu.session_id) AS sessions,
                    COALESCE(SUM(tu.input_tokens), 0) AS input_tokens,
                    COALESCE(SUM(tu.cached_input_tokens), 0) AS cached_input_tokens,
                    COALESCE(SUM(tu.output_tokens), 0) AS output_tokens
                FROM token_usage tu
                LEFT JOIN models m ON m.id=tu.model_id
                GROUP BY COALESCE(m.name, '(unknown)')
                ORDER BY input_tokens DESC, model
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def by_agent(self) -> list[dict[str, Any]]:
        with self.repository.database.connect() as conn:
            rows = conn.execute(
                """
                SELECT a.name AS agent, a.type AS agent_type,
                       COUNT(DISTINCT sa.session_id) AS sessions,
                       COUNT(*) AS evidence_count
                FROM session_agents sa
                JOIN agents a ON a.id=sa.agent_id
                GROUP BY a.id, a.name, a.type
                ORDER BY sessions DESC, agent
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def by_skill(self) -> list[dict[str, Any]]:
        with self.repository.database.connect() as conn:
            rows = conn.execute(
                """
                SELECT sk.name AS skill, ss.usage_type,
                       COUNT(DISTINCT ss.session_id) AS sessions,
                       COUNT(*) AS evidence_count
                FROM session_skills ss
                JOIN skills sk ON sk.id=ss.skill_id
                GROUP BY sk.id, sk.name, ss.usage_type
                ORDER BY skill, usage_type
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def by_tool(self) -> list[dict[str, Any]]:
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
                GROUP BY t.id, t.name, t.category
                ORDER BY calls DESC, tool
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def by_day(self) -> list[dict[str, Any]]:
        with self.repository.database.connect() as conn:
            rows = conn.execute(
                """
                SELECT substr(timestamp, 1, 10) AS day,
                       COALESCE(SUM(input_tokens), 0) AS input_tokens,
                       COALESCE(SUM(cached_input_tokens), 0) AS cached_input_tokens,
                       COALESCE(SUM(output_tokens), 0) AS output_tokens
                FROM token_usage
                GROUP BY substr(timestamp, 1, 10)
                ORDER BY day
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def optimizer_summary(self) -> list[dict[str, Any]]:
        with self.repository.database.connect() as conn:
            rows = conn.execute(
                """
                SELECT o.name AS optimizer,
                       COUNT(op.id) AS events,
                       COALESCE(SUM(op.original_tokens), 0) AS original_tokens,
                       COALESCE(SUM(op.optimized_tokens), 0) AS optimized_tokens,
                       COALESCE(SUM(op.tokens_saved), 0) AS tokens_saved,
                       COALESCE(SUM(op.compression_savings_usd), 0) AS compression_savings_usd
                FROM optimizers o
                LEFT JOIN optimizations op ON op.optimizer_id=o.id
                GROUP BY o.id, o.name
                ORDER BY optimizer
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def savings_by_day(self) -> list[dict[str, Any]]:
        with self.repository.database.connect() as conn:
            rows = conn.execute(
                """
                SELECT substr(timestamp, 1, 10) AS day,
                       COALESCE(SUM(tokens_saved), 0) AS tokens_saved,
                       COALESCE(SUM(compression_savings_usd), 0) AS compression_savings_usd,
                       COALESCE(SUM(cache_savings_usd), 0) AS cache_savings_usd
                FROM optimizations
                GROUP BY substr(timestamp, 1, 10)
                ORDER BY day
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def cost_by_day(self) -> list[dict[str, Any]]:
        with self.repository.database.connect() as conn:
            rows = conn.execute(
                """
                SELECT substr(period_start, 1, 10) AS day,
                       SUM(observed_cost_usd) AS observed_cost_usd,
                       SUM(estimated_raw_cost_usd) AS estimated_raw_cost_usd
                FROM costs
                WHERE period_start IS NOT NULL
                GROUP BY substr(period_start, 1, 10)
                ORDER BY day
                """
            ).fetchall()
        return [dict(row) for row in rows]
