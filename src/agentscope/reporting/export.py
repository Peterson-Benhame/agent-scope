from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from agentscope.analytics.filters import AnalyticsFilter
from agentscope.analytics.service import AnalyticsService
from agentscope.storage.repository import Repository


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def _query(
    repository: Repository,
    sql: str,
    params: list[object] | None = None,
) -> list[dict[str, Any]]:
    with repository.database.connect() as conn:
        return [dict(row) for row in conn.execute(sql, params or []).fetchall()]


def _where(
    filters: AnalyticsFilter,
    *,
    date_expression: str | None = None,
    project_expression: str | None = None,
    model_expression: str | None = None,
    source_expression: str | None = None,
) -> tuple[str, list[object]]:
    clauses: list[str] = []
    params: list[object] = []

    if filters.from_date is not None and date_expression:
        clauses.append(f"substr({date_expression}, 1, 10) >= ?")
        params.append(filters.from_date.isoformat())
    if filters.to_date is not None and date_expression:
        clauses.append(f"substr({date_expression}, 1, 10) <= ?")
        params.append(filters.to_date.isoformat())
    if filters.project is not None and project_expression:
        clauses.append(f"{project_expression} = ?")
        params.append(filters.project)
    if filters.model is not None and model_expression:
        clauses.append(f"{model_expression} = ?")
        params.append(filters.model)
    if filters.source is not None and source_expression:
        clauses.append(f"{source_expression} = ?")
        params.append(filters.source)

    return (" WHERE " + " AND ".join(clauses) if clauses else "", params)


def export_datasets(
    repository: Repository,
    analytics: AnalyticsService,
    output_dir: Path,
    *,
    filters: AnalyticsFilter | None = None,
    include_content: bool = False,
) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    active_filters = filters or analytics.filters
    if active_filters != analytics.filters:
        analytics = AnalyticsService(repository, active_filters)

    sessions_where, sessions_params = _where(
        active_filters,
        date_expression="s.started_at",
        project_expression="p.name",
        model_expression="m.name",
        source_expression="src.name",
    )
    token_where, token_params = _where(
        active_filters,
        date_expression="tu.timestamp",
        project_expression="p.name",
        model_expression="COALESCE(m.name, sm.name)",
        source_expression="src.name",
    )
    cost_where, cost_params = _where(
        active_filters,
        date_expression="c.period_start",
        project_expression="p.name",
        model_expression="COALESCE(cm.name, sm.name)",
        source_expression="src.name",
    )
    tool_where, tool_params = _where(
        active_filters,
        date_expression="tc.timestamp",
        project_expression="p.name",
        model_expression="sm.name",
        source_expression="src.name",
    )
    optimization_where, optimization_params = _where(
        active_filters,
        date_expression="op.timestamp",
        project_expression="p.name",
        model_expression="COALESCE(m.name, sm.name)",
        source_expression="src.name",
    )

    datasets: dict[str, list[dict[str, Any]]] = {
        "sessions": _query(
            repository,
            """
            SELECT s.external_session_id AS session_id,
                   COALESCE(p.name, '(unknown)') AS project,
                   s.started_at, s.ended_at, s.originator, s.provider,
                   m.name AS model, src.name AS source, s.cli_version
            FROM sessions s
            LEFT JOIN projects p ON p.id=s.project_id
            LEFT JOIN models m ON m.id=s.model_id
            JOIN sources src ON src.id=s.source_id
            """ + sessions_where + " ORDER BY s.started_at, s.id",
            sessions_params,
        ),
        "token_usage": _query(
            repository,
            """
            SELECT s.external_session_id AS session_id, tu.timestamp,
                   COALESCE(m.name, sm.name) AS model, src.name AS source,
                   tu.input_tokens, tu.cached_input_tokens,
                   tu.cache_write_input_tokens, tu.output_tokens,
                   tu.reasoning_output_tokens, tu.total_tokens, tu.context_window
            FROM token_usage tu
            JOIN sessions s ON s.id=tu.session_id
            LEFT JOIN projects p ON p.id=s.project_id
            LEFT JOIN models m ON m.id=tu.model_id
            LEFT JOIN models sm ON sm.id=s.model_id
            JOIN sources src ON src.id=s.source_id
            """ + token_where + " ORDER BY tu.timestamp, tu.id",
            token_params,
        ),
        "costs": _query(
            repository,
            """
            SELECT c.period_start, c.period_end, c.estimated_raw_cost_usd,
                   c.observed_cost_usd, c.estimated_cost_after_optimization_usd,
                   c.compression_savings_usd, c.cache_savings_usd,
                   c.total_savings_usd, c.pricing_source, c.pricing_version
            FROM costs c
            LEFT JOIN sessions s ON s.id=c.session_id
            LEFT JOIN projects p ON p.id=s.project_id
            LEFT JOIN models cm ON cm.id=c.model_id
            LEFT JOIN models sm ON sm.id=s.model_id
            LEFT JOIN sources src ON src.id=s.source_id
            """ + cost_where + " ORDER BY c.id",
            cost_params,
        ),
        "agents": analytics.by_agent(),
        "skills": analytics.by_skill(),
        "tool_calls": _query(
            repository,
            """
            SELECT s.external_session_id AS session_id, t.name AS tool, t.category,
                   tc.timestamp, tc.duration_ms, tc.status, tc.input_size, tc.output_size
            FROM tool_calls tc
            JOIN sessions s ON s.id=tc.session_id
            JOIN tools t ON t.id=tc.tool_id
            LEFT JOIN projects p ON p.id=s.project_id
            LEFT JOIN models sm ON sm.id=s.model_id
            JOIN sources src ON src.id=s.source_id
            """ + tool_where + " ORDER BY tc.timestamp, tc.id",
            tool_params,
        ),
        "optimizations": _query(
            repository,
            """
            SELECT o.name AS optimizer, s.external_session_id AS session_id,
                   op.timestamp, COALESCE(m.name, sm.name) AS model,
                   op.original_tokens, op.optimized_tokens, op.tokens_saved,
                   op.compression_percent, op.cache_read_tokens,
                   op.compression_savings_usd, op.cache_savings_usd,
                   op.observed_input_cost_usd, op.correlation_confidence
            FROM optimizations op
            JOIN optimizers o ON o.id=op.optimizer_id
            LEFT JOIN sessions s ON s.id=op.session_id
            LEFT JOIN projects p ON p.id=s.project_id
            LEFT JOIN models m ON m.id=op.model_id
            LEFT JOIN models sm ON sm.id=s.model_id
            LEFT JOIN sources src ON src.id=s.source_id
            """ + optimization_where + " ORDER BY op.timestamp, op.id",
            optimization_params,
        ),
        "usage_by_project": analytics.by_project(),
        "usage_by_model": analytics.by_model(),
        "usage_by_day": analytics.by_day(),
    }

    created: list[Path] = []
    for name, rows in datasets.items():
        path = output_dir / f"{name}.csv"
        _write_csv(path, rows)
        created.append(path)

    json_path = output_dir / "datasets.json"
    json_path.write_text(
        json.dumps(datasets, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    created.append(json_path)

    if include_content:
        message_where, message_params = _where(
            active_filters,
            date_expression="msg.timestamp",
            project_expression="p.name",
            model_expression="sm.name",
            source_expression="src.name",
        )
        messages = _query(
            repository,
            """
            SELECT s.external_session_id AS session_id, msg.timestamp,
                   msg.role, msg.phase, msg.content_type, msg.content
            FROM messages msg
            JOIN sessions s ON s.id=msg.session_id
            LEFT JOIN projects p ON p.id=s.project_id
            LEFT JOIN models sm ON sm.id=s.model_id
            JOIN sources src ON src.id=s.source_id
            """ + message_where + " ORDER BY msg.timestamp, msg.id",
            message_params,
        )
        full_path = output_dir / "messages_full.json"
        full_path.write_text(
            json.dumps(messages, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        created.append(full_path)

    return created
