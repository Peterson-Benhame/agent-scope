from __future__ import annotations

from dataclasses import dataclass

from agentscope.analytics.filters import AnalyticsFilter
from agentscope.storage.repository import Repository


@dataclass(frozen=True, slots=True)
class BillingSemantics:
    mode: str
    confidence: str
    estimated_cost_basis: str
    is_observed_spend: bool = False


def _usage_context_table_exists(repository: Repository) -> bool:
    with repository.database.connect() as conn:
        row = conn.execute(
            """
            SELECT 1
            FROM sqlite_master
            WHERE type='table' AND name='session_usage_context'
            """
        ).fetchone()
    return row is not None


def _scope_clauses(filters: AnalyticsFilter) -> tuple[list[str], list[object]]:
    clauses: list[str] = []
    params: list[object] = []
    usage_day = filters.local_date_expression("tu.timestamp")

    if filters.from_date is not None:
        clauses.append(f"{usage_day} >= ?")
        params.append(filters.from_date.isoformat())
    if filters.to_date is not None:
        clauses.append(f"{usage_day} <= ?")
        params.append(filters.to_date.isoformat())
    if filters.project is not None:
        clauses.append("p.name = ?")
        params.append(filters.project)
    if filters.model is not None:
        clauses.append("COALESCE(tm.name, sm.name) = ?")
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

    return clauses, params


def billing_semantics(
    repository: Repository,
    filters: AnalyticsFilter,
) -> BillingSemantics:
    has_context = _usage_context_table_exists(repository)
    clauses, params = _scope_clauses(filters)
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    context_join = (
        "LEFT JOIN session_usage_context suc ON suc.session_id=s.id"
        if has_context
        else ""
    )
    mode_expression = "COALESCE(suc.billing_mode, 'unknown')" if has_context else "'unknown'"
    confidence_expression = (
        "COALESCE(suc.billing_confidence, 'unknown')" if has_context else "'unknown'"
    )

    with repository.database.connect() as conn:
        rows = conn.execute(
            f"""
            SELECT {mode_expression} AS billing_mode,
                   {confidence_expression} AS billing_confidence,
                   COUNT(*) AS events
            FROM token_usage tu
            JOIN sessions s ON s.id=tu.session_id
            LEFT JOIN projects p ON p.id=s.project_id
            LEFT JOIN models tm ON tm.id=tu.model_id
            LEFT JOIN models sm ON sm.id=s.model_id
            JOIN sources src ON src.id=s.source_id
            LEFT JOIN users u ON u.id=s.user_id
            LEFT JOIN machines mc ON mc.id=s.machine_id
            {context_join}
            {where}
            GROUP BY {mode_expression}, {confidence_expression}
            """,
            params,
        ).fetchall()

    if not rows:
        return BillingSemantics(
            mode="unknown",
            confidence="unknown",
            estimated_cost_basis="openai_api_equivalent",
        )

    modes = {str(row["billing_mode"] or "unknown") for row in rows}
    if len(modes) > 1:
        return BillingSemantics(
            mode="mixed",
            confidence="mixed",
            estimated_cost_basis="openai_api_equivalent",
        )

    mode = next(iter(modes))
    confidences = {str(row["billing_confidence"] or "unknown") for row in rows}
    confidence = next(iter(confidences)) if len(confidences) == 1 else "mixed"
    basis = "openai_api_estimate" if mode == "api" else "openai_api_equivalent"
    return BillingSemantics(
        mode=mode,
        confidence=confidence,
        estimated_cost_basis=basis,
    )
