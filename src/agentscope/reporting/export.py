from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

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


def _query(repository: Repository, sql: str) -> list[dict[str, Any]]:
    with repository.database.connect() as conn:
        return [dict(row) for row in conn.execute(sql).fetchall()]


def export_datasets(
    repository: Repository,
    analytics: AnalyticsService,
    output_dir: Path,
    *,
    include_content: bool = False,
) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    datasets: dict[str, list[dict[str, Any]]] = {
        "sessions": _query(repository, """
            SELECT s.external_session_id AS session_id,
                   COALESCE(p.name, '(unknown)') AS project,
                   s.started_at, s.ended_at, s.originator, s.provider,
                   m.name AS model, s.cli_version
            FROM sessions s
            LEFT JOIN projects p ON p.id=s.project_id
            LEFT JOIN models m ON m.id=s.model_id
            ORDER BY s.started_at, s.id
        """),
        "token_usage": _query(repository, """
            SELECT s.external_session_id AS session_id, tu.timestamp, m.name AS model,
                   tu.input_tokens, tu.cached_input_tokens, tu.cache_write_input_tokens,
                   tu.output_tokens, tu.reasoning_output_tokens, tu.total_tokens, tu.context_window
            FROM token_usage tu
            JOIN sessions s ON s.id=tu.session_id
            LEFT JOIN models m ON m.id=tu.model_id
            ORDER BY tu.timestamp, tu.id
        """),
        "costs": _query(repository, """
            SELECT c.period_start, c.period_end, c.estimated_raw_cost_usd, c.observed_cost_usd,
                   c.estimated_cost_after_optimization_usd, c.compression_savings_usd,
                   c.cache_savings_usd, c.total_savings_usd, c.pricing_source, c.pricing_version
            FROM costs c ORDER BY c.id
        """),
        "agents": analytics.by_agent(),
        "skills": analytics.by_skill(),
        "tool_calls": _query(repository, """
            SELECT s.external_session_id AS session_id, t.name AS tool, t.category,
                   tc.timestamp, tc.duration_ms, tc.status, tc.input_size, tc.output_size
            FROM tool_calls tc
            JOIN sessions s ON s.id=tc.session_id
            JOIN tools t ON t.id=tc.tool_id
            ORDER BY tc.timestamp, tc.id
        """),
        "optimizations": _query(repository, """
            SELECT o.name AS optimizer, s.external_session_id AS session_id,
                   op.timestamp, m.name AS model, op.original_tokens, op.optimized_tokens,
                   op.tokens_saved, op.compression_percent, op.cache_read_tokens,
                   op.compression_savings_usd, op.cache_savings_usd,
                   op.observed_input_cost_usd, op.correlation_confidence
            FROM optimizations op
            JOIN optimizers o ON o.id=op.optimizer_id
            LEFT JOIN sessions s ON s.id=op.session_id
            LEFT JOIN models m ON m.id=op.model_id
            ORDER BY op.timestamp, op.id
        """),
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
    json_path.write_text(json.dumps(datasets, ensure_ascii=False, indent=2), encoding="utf-8")
    created.append(json_path)

    if include_content:
        messages = _query(repository, """
            SELECT s.external_session_id AS session_id, m.timestamp, m.role, m.phase,
                   m.content_type, m.content
            FROM messages m
            JOIN sessions s ON s.id=m.session_id
            ORDER BY m.timestamp, m.id
        """)
        full_path = output_dir / "messages_full.json"
        full_path.write_text(json.dumps(messages, ensure_ascii=False, indent=2), encoding="utf-8")
        created.append(full_path)

    return created
