from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from agentscope.analytics.dashboard import DashboardAnalyticsService
from agentscope.analytics.filters import AnalyticsFilter
from agentscope.billing import billing_semantics
from agentscope.extension.contracts import (
    SNAPSHOT_SCHEMA,
    SNAPSHOT_VERSION,
    AvailabilityItem,
    SnapshotAvailability,
    SnapshotBilling,
    SnapshotDimensions,
    SnapshotQuality,
    SnapshotSummary,
    to_dict,
)
from agentscope.storage.repository import Repository
from agentscope.usage_context import ensure_usage_context_schema


def _dimension_values(repository: Repository, table: str, expression: str) -> list[str]:
    with repository.database.connect() as conn:
        rows = conn.execute(
            f"SELECT DISTINCT {expression} AS value FROM {table} "
            "WHERE value IS NOT NULL AND trim(value) <> '' ORDER BY value"
        ).fetchall()
    return [str(row["value"]) for row in rows]


def _dimensions(repository: Repository) -> SnapshotDimensions:
    return SnapshotDimensions(
        projects=_dimension_values(repository, "projects", "name"),
        models=_dimension_values(repository, "models", "name"),
        sources=_dimension_values(repository, "sources", "name"),
        users=_dimension_values(
            repository,
            "users",
            "COALESCE(display_name, stable_key)",
        ),
        machines=_dimension_values(
            repository,
            "machines",
            "COALESCE(display_name, stable_key)",
        ),
    )


def _freshness(repository: Repository) -> dict[str, object]:
    with repository.database.connect() as conn:
        row = conn.execute(
            """
            SELECT MAX(last_imported_at) AS last_imported_at,
                   COUNT(*) AS artifacts_tracked
            FROM import_state
            WHERE status='complete'
            """
        ).fetchone()
    return {
        "last_imported_at": (
            str(row["last_imported_at"])
            if row["last_imported_at"] is not None
            else None
        ),
        "artifacts_tracked": int(row["artifacts_tracked"] or 0),
    }


def _identity_confidence(repository: Repository) -> dict[str, int]:
    with repository.database.connect() as conn:
        rows = conn.execute(
            """
            SELECT identity_confidence, COUNT(*) AS n
            FROM users
            GROUP BY identity_confidence
            ORDER BY identity_confidence
            """
        ).fetchall()
    return {str(row["identity_confidence"]): int(row["n"]) for row in rows}


def _scope_clauses(
    filters: AnalyticsFilter,
    *,
    date_expression: str,
    model_expression: str,
) -> tuple[list[str], list[object]]:
    clauses: list[str] = []
    params: list[object] = []
    local_day = filters.local_date_expression(date_expression)
    if filters.from_date is not None:
        clauses.append(f"{local_day} >= ?")
        params.append(filters.from_date.isoformat())
    if filters.to_date is not None:
        clauses.append(f"{local_day} <= ?")
        params.append(filters.to_date.isoformat())
    if filters.project is not None:
        clauses.append("p.name = ?")
        params.append(filters.project)
    if filters.source is not None:
        clauses.append("src.name = ?")
        params.append(filters.source)
    if filters.user is not None:
        clauses.append("COALESCE(u.display_name, u.stable_key) = ?")
        params.append(filters.user)
    if filters.machine is not None:
        clauses.append("COALESCE(mc.display_name, mc.stable_key) = ?")
        params.append(filters.machine)
    if filters.model is not None:
        clauses.append(f"{model_expression} = ?")
        params.append(filters.model)
    return clauses, params


def _tokens_without_model(repository: Repository, filters: AnalyticsFilter) -> int:
    clauses, params = _scope_clauses(
        filters,
        date_expression="tu.timestamp",
        model_expression="COALESCE(tm.name, sm.name)",
    )
    clauses.insert(0, "COALESCE(tu.model_id, s.model_id) IS NULL")
    with repository.database.connect() as conn:
        row = conn.execute(
            """
            SELECT COUNT(*) AS n
            FROM token_usage tu
            JOIN sessions s ON s.id=tu.session_id
            LEFT JOIN projects p ON p.id=s.project_id
            LEFT JOIN models tm ON tm.id=tu.model_id
            LEFT JOIN models sm ON sm.id=s.model_id
            JOIN sources src ON src.id=s.source_id
            LEFT JOIN users u ON u.id=s.user_id
            LEFT JOIN machines mc ON mc.id=s.machine_id
            WHERE """ + " AND ".join(clauses),
            params,
        ).fetchone()
    return int(row["n"])


def _has_savings_evidence(repository: Repository, filters: AnalyticsFilter) -> bool:
    cost_clauses, cost_params = _scope_clauses(
        filters,
        date_expression="c.period_start",
        model_expression="COALESCE(cm.name, sm.name)",
    )
    cost_clauses.insert(
        0,
        "(c.compression_savings_usd IS NOT NULL "
        "OR c.cache_savings_usd IS NOT NULL "
        "OR c.total_savings_usd IS NOT NULL)",
    )
    optimization_clauses, optimization_params = _scope_clauses(
        filters,
        date_expression="op.timestamp",
        model_expression="COALESCE(om.name, sm.name)",
    )
    optimization_clauses.insert(
        0,
        "(op.compression_savings_usd IS NOT NULL OR op.cache_savings_usd IS NOT NULL)",
    )
    with repository.database.connect() as conn:
        cost_row = conn.execute(
            """
            SELECT COUNT(*) AS n
            FROM costs c
            LEFT JOIN sessions s ON s.id=c.session_id
            LEFT JOIN projects p ON p.id=s.project_id
            LEFT JOIN models cm ON cm.id=c.model_id
            LEFT JOIN models sm ON sm.id=s.model_id
            LEFT JOIN sources src ON src.id=s.source_id
            LEFT JOIN users u ON u.id=s.user_id
            LEFT JOIN machines mc ON mc.id=s.machine_id
            WHERE """ + " AND ".join(cost_clauses),
            cost_params,
        ).fetchone()
        if int(cost_row["n"]) > 0:
            return True
        optimization_row = conn.execute(
            """
            SELECT COUNT(*) AS n
            FROM optimizations op
            LEFT JOIN sessions s ON s.id=op.session_id
            LEFT JOIN projects p ON p.id=s.project_id
            LEFT JOIN models om ON om.id=op.model_id
            LEFT JOIN models sm ON sm.id=s.model_id
            LEFT JOIN sources src ON src.id=s.source_id
            LEFT JOIN users u ON u.id=s.user_id
            LEFT JOIN machines mc ON mc.id=s.machine_id
            WHERE """ + " AND ".join(optimization_clauses),
            optimization_params,
        ).fetchone()
    return int(optimization_row["n"]) > 0


def _availability(value: float | None, reason: str) -> AvailabilityItem:
    return AvailabilityItem(
        available=value is not None,
        reason=None if value is not None else reason,
    )


def build_extension_snapshot(
    repository: Repository,
    filters: AnalyticsFilter,
    *,
    period: str | None,
    database_path: Path,
) -> dict[str, object]:
    ensure_usage_context_schema(repository)
    dashboard = DashboardAnalyticsService(repository, filters)
    summary = dashboard.summary()
    quality = dashboard.data_quality()
    optimization_confidence = quality.get("optimization_confidence", {})
    if not isinstance(optimization_confidence, dict):
        optimization_confidence = {}

    observed_cost = summary.observed_cost_usd
    estimated_cost = summary.estimated_raw_cost_usd
    estimated_savings = (
        summary.total_savings_usd
        if _has_savings_evidence(repository, filters)
        else None
    )
    availability = SnapshotAvailability(
        observed_cost=_availability(observed_cost, "source_does_not_report_cost"),
        estimated_cost=_availability(estimated_cost, "insufficient_pricing_data"),
        estimated_savings=_availability(estimated_savings, "no_optimization_data"),
    )
    billing = billing_semantics(repository, filters)

    return {
        "schema": SNAPSHOT_SCHEMA,
        "version": SNAPSHOT_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "database": str(database_path),
        "freshness": _freshness(repository),
        "filters": {
            "from": filters.from_date.isoformat() if filters.from_date else None,
            "to": filters.to_date.isoformat() if filters.to_date else None,
            "period": period,
            "project": filters.project,
            "model": filters.model,
            "source": filters.source,
            "user": filters.user,
            "machine": filters.machine,
        },
        "summary": to_dict(
            SnapshotSummary(
                sessions=summary.sessions,
                total_tokens=summary.total_tokens,
                tokens_saved=summary.tokens_saved,
                cache_ratio=summary.cache_ratio if summary.input_tokens else None,
                observed_cost_usd=observed_cost,
                estimated_cost_usd=estimated_cost,
                estimated_savings_usd=estimated_savings,
            )
        ),
        "billing": to_dict(
            SnapshotBilling(
                mode=billing.mode,
                confidence=billing.confidence,
                estimated_cost_basis=billing.estimated_cost_basis,
                is_observed_spend=billing.is_observed_spend,
            )
        ),
        "availability": to_dict(availability),
        "series": {"daily": dashboard.by_day()},
        "breakdowns": {
            "projects": dashboard.by_project(),
            "models": dashboard.by_model(),
            "sources": dashboard.by_source(),
            "clients": dashboard.by_client(),
        },
        "dimensions": to_dict(_dimensions(repository)),
        "quality": to_dict(
            SnapshotQuality(
                import_errors=int(quality.get("import_errors", 0) or 0),
                tokens_without_model=_tokens_without_model(repository, filters),
                identity_confidence=_identity_confidence(repository),
                correlation_confidence={
                    str(key): int(value)
                    for key, value in optimization_confidence.items()
                },
            )
        ),
    }
