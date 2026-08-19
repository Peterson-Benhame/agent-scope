from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from agentscope.storage.repository import Repository
from agentscope.team.validation import validate_team_bundle


@dataclass(frozen=True, slots=True)
class TeamImportSummary:
    bundle_id: str
    sessions_imported: int = 0
    events_imported: int = 0
    events_skipped: int = 0
    errors: int = 0


def _project_id(conn, name: str | None) -> int | None:
    if not name:
        return None
    safe_path = "team://project/" + hashlib.sha256(name.encode("utf-8")).hexdigest()
    conn.execute(
        "INSERT OR IGNORE INTO projects(name, path) VALUES(?, ?)",
        (name, safe_path),
    )
    return int(conn.execute("SELECT id FROM projects WHERE path=?", (safe_path,)).fetchone()[0])


def _model_id(conn, name: str | None, provider: str | None = None) -> int | None:
    if not name:
        return None
    provider_value = provider or ""
    conn.execute(
        "INSERT OR IGNORE INTO models(provider, name) VALUES(?, ?)",
        (provider_value, name),
    )
    return int(
        conn.execute(
            "SELECT id FROM models WHERE provider=? AND name=?",
            (provider_value, name),
        ).fetchone()[0]
    )


def _source_id(conn, name: str) -> int:
    conn.execute(
        "INSERT OR IGNORE INTO sources(name, type) VALUES(?, 'team-import')",
        (name,),
    )
    return int(conn.execute("SELECT id FROM sources WHERE name=?", (name,)).fetchone()[0])


def _user_ids(conn, records: list[dict[str, Any]]) -> dict[str, int]:
    result: dict[str, int] = {}
    for record in records:
        conn.execute(
            """
            INSERT INTO users(
                stable_key, display_name, provider_user_id, provider,
                identity_confidence, metadata_json
            ) VALUES(?, ?, ?, ?, ?, '{}')
            ON CONFLICT(stable_key) DO UPDATE SET
                display_name=excluded.display_name,
                provider_user_id=COALESCE(excluded.provider_user_id, users.provider_user_id),
                provider=COALESCE(excluded.provider, users.provider),
                identity_confidence=excluded.identity_confidence
            """,
            (
                record["stable_key"],
                record.get("display_name"),
                record.get("provider_user_id"),
                record.get("provider"),
                record.get("identity_confidence") or "unknown",
            ),
        )
        result[str(record["stable_key"])] = int(
            conn.execute(
                "SELECT id FROM users WHERE stable_key=?",
                (record["stable_key"],),
            ).fetchone()[0]
        )
    return result


def _machine_ids(conn, records: list[dict[str, Any]]) -> dict[str, int]:
    result: dict[str, int] = {}
    for record in records:
        conn.execute(
            """
            INSERT INTO machines(stable_key, display_name, os, metadata_json)
            VALUES(?, ?, ?, '{}')
            ON CONFLICT(stable_key) DO UPDATE SET
                display_name=excluded.display_name,
                os=COALESCE(excluded.os, machines.os)
            """,
            (record["stable_key"], record.get("display_name"), record.get("os")),
        )
        result[str(record["stable_key"])] = int(
            conn.execute(
                "SELECT id FROM machines WHERE stable_key=?",
                (record["stable_key"],),
            ).fetchone()[0]
        )
    return result


def _session_map(
    conn,
    records: list[dict[str, Any]],
    users: dict[str, int],
    machines: dict[str, int],
) -> tuple[dict[str, int], dict[str, dict[str, Any]], int]:
    ids: dict[str, int] = {}
    metadata: dict[str, dict[str, Any]] = {}
    imported = 0
    for record in records:
        source_id = _source_id(conn, str(record["source"]))
        project_id = _project_id(conn, record.get("project"))
        model_id = _model_id(conn, record.get("model"), record.get("provider"))
        user_key = record.get("user_key")
        machine_key = record.get("machine_key")
        cursor = conn.execute(
            """
            INSERT OR IGNORE INTO sessions(
                source_id, external_session_id, project_id, started_at, ended_at,
                originator, provider, model_id, cli_version, metadata_json,
                user_id, machine_id
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                source_id,
                record["session_key"],
                project_id,
                record.get("started_at"),
                record.get("ended_at"),
                record.get("originator"),
                record.get("provider"),
                model_id,
                record.get("cli_version"),
                json.dumps(
                    {"team_session_key": record["session_key"]},
                    ensure_ascii=False,
                    sort_keys=True,
                ),
                users.get(str(user_key)) if user_key else None,
                machines.get(str(machine_key)) if machine_key else None,
            ),
        )
        imported += 1 if cursor.rowcount == 1 else 0
        session_id = int(
            conn.execute(
                "SELECT id FROM sessions WHERE source_id=? AND external_session_id=?",
                (source_id, record["session_key"]),
            ).fetchone()[0]
        )
        ids[str(record["session_key"])] = session_id
        metadata[str(record["session_key"])] = record
    return ids, metadata, imported


def _provenance(
    conn,
    bundle_id: str,
    event_key: str,
    session_record: dict[str, Any] | None,
    source: str | None = None,
) -> None:
    conn.execute(
        """
        INSERT OR IGNORE INTO team_event_provenance(
            event_key, bundle_id, source, user_key, machine_key
        ) VALUES(?, ?, ?, ?, ?)
        """,
        (
            event_key,
            bundle_id,
            source or (session_record or {}).get("source"),
            (session_record or {}).get("user_key"),
            (session_record or {}).get("machine_key"),
        ),
    )


def _insert_token(conn, session_id: int, record: dict[str, Any], provider: str | None) -> bool:
    model_id = _model_id(conn, record.get("model"), provider)
    cursor = conn.execute(
        """
        INSERT OR IGNORE INTO token_usage(
            session_id, timestamp, model_id, input_tokens, cached_input_tokens,
            cache_write_input_tokens, output_tokens, reasoning_output_tokens,
            total_tokens, context_window, event_key
        ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            session_id,
            record.get("timestamp") or "",
            model_id,
            record.get("input_tokens"),
            record.get("cached_input_tokens"),
            record.get("cache_write_input_tokens"),
            record.get("output_tokens"),
            record.get("reasoning_output_tokens"),
            record.get("total_tokens"),
            record.get("context_window"),
            record["event_key"],
        ),
    )
    return cursor.rowcount == 1


def _insert_cost(conn, session_id: int, record: dict[str, Any], provider: str | None) -> bool:
    model_id = _model_id(conn, record.get("model"), provider)
    cursor = conn.execute(
        """
        INSERT OR IGNORE INTO costs(
            session_id, model_id, period_start, period_end,
            estimated_raw_cost_usd, observed_cost_usd,
            estimated_cost_after_optimization_usd, compression_savings_usd,
            cache_savings_usd, total_savings_usd,
            pricing_source, pricing_version, event_key
        ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            session_id,
            model_id,
            record.get("period_start"),
            record.get("period_end"),
            record.get("estimated_raw_cost_usd"),
            record.get("observed_cost_usd"),
            record.get("estimated_cost_after_optimization_usd"),
            record.get("compression_savings_usd"),
            record.get("cache_savings_usd"),
            record.get("total_savings_usd"),
            record.get("pricing_source"),
            record.get("pricing_version"),
            record["event_key"],
        ),
    )
    return cursor.rowcount == 1


def _insert_tool(conn, session_id: int, record: dict[str, Any]) -> bool:
    conn.execute(
        "INSERT OR IGNORE INTO tools(name, provider, category) VALUES(?, ?, ?)",
        (record["tool"], record.get("provider") or "", record.get("category") or ""),
    )
    tool_id = int(
        conn.execute(
            "SELECT id FROM tools WHERE name=? AND provider=? AND category=?",
            (record["tool"], record.get("provider") or "", record.get("category") or ""),
        ).fetchone()[0]
    )
    cursor = conn.execute(
        """
        INSERT OR IGNORE INTO tool_calls(
            session_id, tool_id, external_call_id, timestamp, duration_ms,
            status, input_size, output_size, event_key
        ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            session_id,
            tool_id,
            record.get("external_call_id"),
            record.get("timestamp") or "",
            record.get("duration_ms"),
            record.get("status"),
            record.get("input_size"),
            record.get("output_size"),
            record["event_key"],
        ),
    )
    return cursor.rowcount == 1


def _insert_agent(conn, session_id: int, record: dict[str, Any]) -> bool:
    conn.execute(
        "INSERT OR IGNORE INTO agents(name, type) VALUES(?, ?)",
        (record["agent"], record["agent_type"]),
    )
    agent_id = int(
        conn.execute(
            "SELECT id FROM agents WHERE name=? AND type=?",
            (record["agent"], record["agent_type"]),
        ).fetchone()[0]
    )
    parent_id = None
    if record.get("parent_agent"):
        conn.execute(
            "INSERT OR IGNORE INTO agents(name, type) VALUES(?, 'parent')",
            (record["parent_agent"],),
        )
        parent_id = int(
            conn.execute(
                "SELECT id FROM agents WHERE name=? AND type='parent'",
                (record["parent_agent"],),
            ).fetchone()[0]
        )
    existing = conn.execute(
        """
        SELECT 1 FROM session_agents
        WHERE session_id=? AND agent_id=?
          AND COALESCE(parent_agent_id, -1)=COALESCE(?, -1)
          AND evidence_type=?
        """,
        (session_id, agent_id, parent_id, record.get("evidence_type") or "team_bundle"),
    ).fetchone()
    if existing:
        return False
    conn.execute(
        """
        INSERT INTO session_agents(
            session_id, agent_id, parent_agent_id, started_at, ended_at, evidence_type
        ) VALUES(?, ?, ?, ?, ?, ?)
        """,
        (
            session_id,
            agent_id,
            parent_id,
            record.get("started_at"),
            record.get("ended_at"),
            record.get("evidence_type") or "team_bundle",
        ),
    )
    return True


def _insert_optimization(
    conn,
    session_id: int | None,
    record: dict[str, Any],
    provider: str | None,
) -> bool:
    conn.execute(
        "INSERT OR IGNORE INTO optimizers(name, version) VALUES(?, ?)",
        (record["optimizer"], record.get("optimizer_version") or ""),
    )
    optimizer_id = int(
        conn.execute(
            "SELECT id FROM optimizers WHERE name=? AND version=?",
            (record["optimizer"], record.get("optimizer_version") or ""),
        ).fetchone()[0]
    )
    model_id = _model_id(conn, record.get("model"), provider)
    cursor = conn.execute(
        """
        INSERT OR IGNORE INTO optimizations(
            optimizer_id, session_id, timestamp, model_id,
            original_tokens, optimized_tokens, tokens_saved,
            compression_percent, cache_read_tokens,
            compression_savings_usd, cache_savings_usd,
            observed_input_cost_usd, correlation_confidence, event_key
        ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            optimizer_id,
            session_id,
            record.get("timestamp") or "",
            model_id,
            record.get("original_tokens"),
            record.get("optimized_tokens"),
            record.get("tokens_saved"),
            record.get("compression_percent"),
            record.get("cache_read_tokens"),
            record.get("compression_savings_usd"),
            record.get("cache_savings_usd"),
            record.get("observed_input_cost_usd"),
            record.get("correlation_confidence") or "unknown",
            record["event_key"],
        ),
    )
    return cursor.rowcount == 1


def import_team_bundle(repository: Repository, bundle: dict) -> TeamImportSummary:
    validate_team_bundle(bundle)
    bundle_id = str(bundle["bundle_id"])
    records = bundle["records"]
    total_events = sum(
        len(records[group])
        for group in ("token_usage", "costs", "tool_calls", "agents", "optimizations")
    )

    with repository.database.connect() as conn:
        if conn.execute(
            "SELECT 1 FROM team_bundles WHERE bundle_id=?",
            (bundle_id,),
        ).fetchone():
            return TeamImportSummary(
                bundle_id=bundle_id,
                events_skipped=total_events,
            )

        conn.execute(
            """
            INSERT INTO team_bundles(
                bundle_id, schema_version, organization, team, metadata_json
            ) VALUES(?, ?, ?, ?, ?)
            """,
            (
                bundle_id,
                int(bundle["version"]),
                bundle.get("organization"),
                bundle.get("team"),
                json.dumps(
                    {"generated_at": bundle.get("generated_at")},
                    ensure_ascii=False,
                    sort_keys=True,
                ),
            ),
        )
        users = _user_ids(conn, records["users"])
        machines = _machine_ids(conn, records["machines"])
        sessions, session_metadata, sessions_imported = _session_map(
            conn,
            records["sessions"],
            users,
            machines,
        )

        imported = 0
        skipped = 0
        for group, writer in (
            ("token_usage", _insert_token),
            ("costs", _insert_cost),
        ):
            for record in records[group]:
                session_record = session_metadata[str(record["session_key"])]
                created = writer(
                    conn,
                    sessions[str(record["session_key"])],
                    record,
                    session_record.get("provider"),
                )
                imported += int(created)
                skipped += int(not created)
                _provenance(conn, bundle_id, record["event_key"], session_record)

        for record in records["tool_calls"]:
            session_record = session_metadata[str(record["session_key"])]
            created = _insert_tool(
                conn,
                sessions[str(record["session_key"])],
                record,
            )
            imported += int(created)
            skipped += int(not created)
            _provenance(conn, bundle_id, record["event_key"], session_record)

        for record in records["agents"]:
            session_record = session_metadata[str(record["session_key"])]
            created = _insert_agent(
                conn,
                sessions[str(record["session_key"])],
                record,
            )
            imported += int(created)
            skipped += int(not created)
            _provenance(conn, bundle_id, record["event_key"], session_record)

        for record in records["optimizations"]:
            session_key = record.get("session_key")
            session_record = session_metadata.get(str(session_key)) if session_key else None
            created = _insert_optimization(
                conn,
                sessions.get(str(session_key)) if session_key else None,
                record,
                (session_record or {}).get("provider"),
            )
            imported += int(created)
            skipped += int(not created)
            _provenance(
                conn,
                bundle_id,
                record["event_key"],
                session_record,
                source=record.get("optimizer"),
            )

    return TeamImportSummary(
        bundle_id=bundle_id,
        sessions_imported=sessions_imported,
        events_imported=imported,
        events_skipped=skipped,
        errors=0,
    )
