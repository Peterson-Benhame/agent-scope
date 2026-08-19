from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from agentscope.analytics.filters import AnalyticsFilter
from agentscope.storage.repository import Repository


TEAM_BUNDLE_SCHEMA = "agentscope-team-bundle"
TEAM_BUNDLE_VERSION = 1


def canonical_bundle_payload(bundle: dict) -> bytes:
    payload = {
        key: value
        for key, value in bundle.items()
        if key not in {"generated_at", "bundle_id"}
    }
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def compute_bundle_id(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _stable_key(*parts: object) -> str:
    payload = "|".join("" if part is None else str(part) for part in parts)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _session_where(
    filters: AnalyticsFilter,
    *,
    include_dates: bool = True,
) -> tuple[str, list[object]]:
    clauses: list[str] = []
    params: list[object] = []
    if include_dates and filters.from_date is not None:
        clauses.append("substr(s.started_at, 1, 10) >= ?")
        params.append(filters.from_date.isoformat())
    if include_dates and filters.to_date is not None:
        clauses.append("substr(s.started_at, 1, 10) <= ?")
        params.append(filters.to_date.isoformat())
    if filters.project is not None:
        clauses.append("p.name = ?")
        params.append(filters.project)
    if filters.model is not None:
        clauses.append("m.name = ?")
        params.append(filters.model)
    if filters.source is not None:
        clauses.append("src.name = ?")
        params.append(filters.source)
    if filters.user is not None:
        clauses.append("(u.display_name = ? OR u.stable_key = ?)")
        params.extend((filters.user, filters.user))
    if filters.machine is not None:
        clauses.append("(mc.display_name = ? OR mc.stable_key = ?)")
        params.extend((filters.machine, filters.machine))
    return (" WHERE " + " AND ".join(clauses) if clauses else "", params)


def _event_date_clause(
    filters: AnalyticsFilter,
    expression: str,
) -> tuple[str, list[object]]:
    clauses: list[str] = []
    params: list[object] = []
    if filters.from_date is not None:
        clauses.append(f"substr({expression}, 1, 10) >= ?")
        params.append(filters.from_date.isoformat())
    if filters.to_date is not None:
        clauses.append(f"substr({expression}, 1, 10) <= ?")
        params.append(filters.to_date.isoformat())
    return (" AND " + " AND ".join(clauses) if clauses else "", params)


def _timestamp_in_filter(value: str | None, filters: AnalyticsFilter) -> bool:
    if filters.from_date is None and filters.to_date is None:
        return True
    if not value:
        return False
    day = value[:10]
    if filters.from_date is not None and day < filters.from_date.isoformat():
        return False
    if filters.to_date is not None and day > filters.to_date.isoformat():
        return False
    return True


def _query_sessions(
    repository: Repository,
    filters: AnalyticsFilter,
    *,
    include_dates: bool = True,
) -> list[dict[str, Any]]:
    where, params = _session_where(filters, include_dates=include_dates)
    with repository.database.connect() as conn:
        rows = conn.execute(
            """
            SELECT s.id, s.external_session_id, s.started_at, s.ended_at,
                   s.originator, s.provider, s.cli_version,
                   src.name AS source, p.name AS project, m.name AS model,
                   u.stable_key AS user_key, u.display_name AS user_name,
                   u.provider_user_id, u.provider AS user_provider,
                   u.identity_confidence,
                   mc.stable_key AS machine_key, mc.display_name AS machine_name,
                   mc.os AS machine_os
            FROM sessions s
            JOIN sources src ON src.id=s.source_id
            LEFT JOIN projects p ON p.id=s.project_id
            LEFT JOIN models m ON m.id=s.model_id
            LEFT JOIN users u ON u.id=s.user_id
            LEFT JOIN machines mc ON mc.id=s.machine_id
            """ + where + " ORDER BY src.name, s.external_session_id, s.id",
            params,
        ).fetchall()
    return [dict(row) for row in rows]


def _selected_placeholders(session_ids: list[int]) -> str:
    return ",".join("?" for _ in session_ids)


def _event_key(
    kind: str,
    session_key: str | None,
    scope_key: str,
    local_key: str,
) -> str:
    return _stable_key(kind, session_key or scope_key, local_key)


def _global_optimization_records(
    repository: Repository,
    filters: AnalyticsFilter,
) -> list[dict[str, Any]]:
    if any(
        value is not None
        for value in (
            filters.project,
            filters.source,
            filters.user,
            filters.machine,
        )
    ):
        return []

    clauses = ["op.session_id IS NULL"]
    params: list[object] = []
    if filters.from_date is not None:
        clauses.append("substr(op.timestamp, 1, 10) >= ?")
        params.append(filters.from_date.isoformat())
    if filters.to_date is not None:
        clauses.append("substr(op.timestamp, 1, 10) <= ?")
        params.append(filters.to_date.isoformat())
    if filters.model is not None:
        clauses.append("m.name = ?")
        params.append(filters.model)

    with repository.database.connect() as conn:
        rows = conn.execute(
            """
            SELECT op.*, o.name AS optimizer, o.version AS optimizer_version,
                   m.name AS model
            FROM optimizations op
            JOIN optimizers o ON o.id=op.optimizer_id
            LEFT JOIN models m ON m.id=op.model_id
            WHERE """ + " AND ".join(clauses) + " ORDER BY op.timestamp, op.id",
            params,
        ).fetchall()

    return [
        {
            "event_key": _stable_key(
                "optimization",
                "global",
                row["optimizer"],
                row["optimizer_version"],
                row["event_key"],
            ),
            "session_key": None,
            "optimizer": row["optimizer"],
            "optimizer_version": row["optimizer_version"],
            "timestamp": row["timestamp"],
            "model": row["model"],
            "original_tokens": row["original_tokens"],
            "optimized_tokens": row["optimized_tokens"],
            "tokens_saved": row["tokens_saved"],
            "compression_percent": row["compression_percent"],
            "cache_read_tokens": row["cache_read_tokens"],
            "compression_savings_usd": row["compression_savings_usd"],
            "cache_savings_usd": row["cache_savings_usd"],
            "observed_input_cost_usd": row["observed_input_cost_usd"],
            "correlation_confidence": row["correlation_confidence"],
        }
        for row in rows
    ]


def _build_records(
    repository: Repository,
    filters: AnalyticsFilter,
) -> dict[str, list[dict[str, Any]]]:
    # Dimension filters select candidate sessions. Date filtering is applied
    # per event below so long-running sessions can contribute only the events
    # that actually fall inside the requested period.
    session_rows = _query_sessions(repository, filters, include_dates=False)
    session_ids = [int(row["id"]) for row in session_rows]

    users_by_key: dict[str, dict[str, Any]] = {}
    machines_by_key: dict[str, dict[str, Any]] = {}
    sessions: list[dict[str, Any]] = []
    session_keys: dict[int, str] = {}
    included_session_ids: set[int] = {
        int(row["id"])
        for row in session_rows
        if _timestamp_in_filter(row["started_at"], filters)
    }

    for row in session_rows:
        if row["user_key"]:
            users_by_key[str(row["user_key"])] = {
                "stable_key": row["user_key"],
                "display_name": row["user_name"],
                "provider_user_id": row["provider_user_id"],
                "provider": row["user_provider"],
                "identity_confidence": row["identity_confidence"],
            }
        if row["machine_key"]:
            machines_by_key[str(row["machine_key"])] = {
                "stable_key": row["machine_key"],
                "display_name": row["machine_name"],
                "os": row["machine_os"],
            }
        session_key = _stable_key(
            "session",
            row["source"],
            row["user_key"],
            row["machine_key"],
            row["external_session_id"],
        )
        session_keys[int(row["id"])] = session_key
        sessions.append(
            {
                "session_key": session_key,
                "external_session_id": row["external_session_id"],
                "source": row["source"],
                "project": row["project"],
                "started_at": row["started_at"],
                "ended_at": row["ended_at"],
                "originator": row["originator"],
                "provider": row["provider"],
                "model": row["model"],
                "cli_version": row["cli_version"],
                "user_key": row["user_key"],
                "machine_key": row["machine_key"],
            }
        )

    scope_key = _stable_key(
        "scope",
        *sorted(users_by_key),
        *sorted(machines_by_key),
    )
    records: dict[str, list[dict[str, Any]]] = {
        "users": [],
        "machines": [],
        "sessions": [],
        "token_usage": [],
        "costs": [],
        "tool_calls": [],
        "agents": [],
        "optimizations": _global_optimization_records(repository, filters),
    }
    if not session_ids:
        return records

    placeholders = _selected_placeholders(session_ids)
    with repository.database.connect() as conn:
        token_date, token_date_params = _event_date_clause(filters, "tu.timestamp")
        token_rows = conn.execute(
            f"""
            SELECT tu.*, m.name AS model
            FROM token_usage tu
            LEFT JOIN models m ON m.id=tu.model_id
            WHERE tu.session_id IN ({placeholders}){token_date}
            ORDER BY tu.timestamp, tu.id
            """,
            [*session_ids, *token_date_params],
        ).fetchall()
        for row in token_rows:
            session_id = int(row["session_id"])
            included_session_ids.add(session_id)
            session_key = session_keys[session_id]
            records["token_usage"].append(
                {
                    "event_key": _event_key(
                        "token", session_key, scope_key, str(row["event_key"])
                    ),
                    "session_key": session_key,
                    "timestamp": row["timestamp"],
                    "model": row["model"],
                    "input_tokens": row["input_tokens"],
                    "cached_input_tokens": row["cached_input_tokens"],
                    "cache_write_input_tokens": row["cache_write_input_tokens"],
                    "output_tokens": row["output_tokens"],
                    "reasoning_output_tokens": row["reasoning_output_tokens"],
                    "total_tokens": row["total_tokens"],
                    "context_window": row["context_window"],
                }
            )

        cost_date, cost_date_params = _event_date_clause(
            filters,
            "COALESCE("
            "c.period_start, c.period_end, "
            "(SELECT sx.started_at FROM sessions sx WHERE sx.id=c.session_id)"
            ")",
        )
        cost_rows = conn.execute(
            f"""
            SELECT c.*, m.name AS model
            FROM costs c
            LEFT JOIN models m ON m.id=c.model_id
            WHERE c.session_id IN ({placeholders}){cost_date}
            ORDER BY c.period_start, c.id
            """,
            [*session_ids, *cost_date_params],
        ).fetchall()
        for row in cost_rows:
            session_id = int(row["session_id"])
            included_session_ids.add(session_id)
            session_key = session_keys[session_id]
            records["costs"].append(
                {
                    "event_key": _event_key(
                        "cost", session_key, scope_key, str(row["event_key"])
                    ),
                    "session_key": session_key,
                    "model": row["model"],
                    "period_start": row["period_start"],
                    "period_end": row["period_end"],
                    "estimated_raw_cost_usd": row["estimated_raw_cost_usd"],
                    "observed_cost_usd": row["observed_cost_usd"],
                    "estimated_cost_after_optimization_usd": row[
                        "estimated_cost_after_optimization_usd"
                    ],
                    "compression_savings_usd": row["compression_savings_usd"],
                    "cache_savings_usd": row["cache_savings_usd"],
                    "total_savings_usd": row["total_savings_usd"],
                    "pricing_source": row["pricing_source"],
                    "pricing_version": row["pricing_version"],
                }
            )

        tool_date, tool_date_params = _event_date_clause(filters, "tc.timestamp")
        tool_rows = conn.execute(
            f"""
            SELECT tc.*, t.name AS tool, t.provider, t.category
            FROM tool_calls tc
            JOIN tools t ON t.id=tc.tool_id
            WHERE tc.session_id IN ({placeholders}){tool_date}
            ORDER BY tc.timestamp, tc.id
            """,
            [*session_ids, *tool_date_params],
        ).fetchall()
        for row in tool_rows:
            session_id = int(row["session_id"])
            included_session_ids.add(session_id)
            session_key = session_keys[session_id]
            records["tool_calls"].append(
                {
                    "event_key": _event_key(
                        "tool", session_key, scope_key, str(row["event_key"])
                    ),
                    "session_key": session_key,
                    "tool": row["tool"],
                    "provider": row["provider"],
                    "category": row["category"],
                    "external_call_id": row["external_call_id"],
                    "timestamp": row["timestamp"],
                    "duration_ms": row["duration_ms"],
                    "status": row["status"],
                    "input_size": row["input_size"],
                    "output_size": row["output_size"],
                }
            )

        agent_date, agent_date_params = _event_date_clause(
            filters,
            "COALESCE(sa.started_at, sa.ended_at, "
            "(SELECT sx.started_at FROM sessions sx WHERE sx.id=sa.session_id))",
        )
        agent_rows = conn.execute(
            f"""
            SELECT sa.*, a.name AS agent, a.type AS agent_type,
                   pa.name AS parent_agent
            FROM session_agents sa
            JOIN agents a ON a.id=sa.agent_id
            LEFT JOIN agents pa ON pa.id=sa.parent_agent_id
            WHERE sa.session_id IN ({placeholders}){agent_date}
            ORDER BY sa.session_id, a.name, sa.id
            """,
            [*session_ids, *agent_date_params],
        ).fetchall()
        for row in agent_rows:
            session_id = int(row["session_id"])
            included_session_ids.add(session_id)
            session_key = session_keys[session_id]
            records["agents"].append(
                {
                    "event_key": _stable_key(
                        "agent",
                        session_key,
                        row["agent"],
                        row["agent_type"],
                        row["parent_agent"],
                        row["evidence_type"],
                    ),
                    "session_key": session_key,
                    "agent": row["agent"],
                    "agent_type": row["agent_type"],
                    "parent_agent": row["parent_agent"],
                    "started_at": row["started_at"],
                    "ended_at": row["ended_at"],
                    "evidence_type": row["evidence_type"],
                }
            )

        optimization_date, optimization_date_params = _event_date_clause(
            filters,
            "op.timestamp",
        )
        optimization_rows = conn.execute(
            f"""
            SELECT op.*, o.name AS optimizer, o.version AS optimizer_version,
                   m.name AS model
            FROM optimizations op
            JOIN optimizers o ON o.id=op.optimizer_id
            LEFT JOIN models m ON m.id=op.model_id
            WHERE op.session_id IN ({placeholders}){optimization_date}
            ORDER BY op.timestamp, op.id
            """,
            [*session_ids, *optimization_date_params],
        ).fetchall()
        for row in optimization_rows:
            session_id = int(row["session_id"])
            included_session_ids.add(session_id)
            session_key = session_keys[session_id]
            records["optimizations"].append(
                {
                    "event_key": _event_key(
                        "optimization", session_key, scope_key, str(row["event_key"])
                    ),
                    "session_key": session_key,
                    "optimizer": row["optimizer"],
                    "optimizer_version": row["optimizer_version"],
                    "timestamp": row["timestamp"],
                    "model": row["model"],
                    "original_tokens": row["original_tokens"],
                    "optimized_tokens": row["optimized_tokens"],
                    "tokens_saved": row["tokens_saved"],
                    "compression_percent": row["compression_percent"],
                    "cache_read_tokens": row["cache_read_tokens"],
                    "compression_savings_usd": row["compression_savings_usd"],
                    "cache_savings_usd": row["cache_savings_usd"],
                    "observed_input_cost_usd": row["observed_input_cost_usd"],
                    "correlation_confidence": row["correlation_confidence"],
                }
            )

    included_session_keys = {
        session_keys[session_id]
        for session_id in included_session_ids
        if session_id in session_keys
    }
    records["sessions"] = [
        row for row in sessions if row["session_key"] in included_session_keys
    ]
    used_user_keys = {
        str(row["user_key"])
        for row in records["sessions"]
        if row["user_key"]
    }
    used_machine_keys = {
        str(row["machine_key"])
        for row in records["sessions"]
        if row["machine_key"]
    }
    records["users"] = [
        users_by_key[key] for key in sorted(used_user_keys)
    ]
    records["machines"] = [
        machines_by_key[key] for key in sorted(used_machine_keys)
    ]
    return records


def build_team_bundle(
    repository: Repository,
    analytics_filter: AnalyticsFilter | None = None,
    organization: str | None = None,
    team: str | None = None,
) -> dict:
    filters = analytics_filter or AnalyticsFilter()
    bundle = {
        "schema": TEAM_BUNDLE_SCHEMA,
        "version": TEAM_BUNDLE_VERSION,
        "bundle_id": "",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "organization": organization,
        "team": team,
        "records": _build_records(repository, filters),
    }
    bundle["bundle_id"] = compute_bundle_id(canonical_bundle_payload(bundle))
    return bundle
