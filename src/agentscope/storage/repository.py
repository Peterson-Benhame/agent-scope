from __future__ import annotations

import hashlib
import json

from agentscope.domain.models import (
    NormalizedMachine,
    NormalizedMessage,
    NormalizedSession,
    NormalizedUser,
)
from agentscope.storage.database import Database


class Repository:
    def __init__(self, database: Database):
        self.database = database

    @staticmethod
    def _event_key(*parts: object) -> str:
        raw = "|".join("" if x is None else str(x) for x in parts)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    @staticmethod
    def _project_name(path: str) -> str:
        normalized = path.replace("\\", "/").rstrip("/")
        return normalized.rsplit("/", 1)[-1] or normalized

    def _upsert_source(self, conn, name: str) -> int:
        conn.execute(
            "INSERT INTO sources(name, type) VALUES(?, ?) "
            "ON CONFLICT(name) DO NOTHING",
            (name, name),
        )
        return int(
            conn.execute("SELECT id FROM sources WHERE name=?", (name,)).fetchone()[0]
        )

    def _upsert_project(self, conn, path: str | None) -> int | None:
        if not path:
            return None
        conn.execute(
            "INSERT INTO projects(name, path) VALUES(?, ?) "
            "ON CONFLICT(path) DO UPDATE SET name=excluded.name",
            (self._project_name(path), path),
        )
        return int(
            conn.execute("SELECT id FROM projects WHERE path=?", (path,)).fetchone()[0]
        )

    def upsert_model(
        self,
        conn,
        name: str | None,
        provider: str | None = None,
    ) -> int | None:
        if not name:
            return None
        provider_value = provider or ""
        conn.execute(
            "INSERT INTO models(provider, name) VALUES(?, ?) "
            "ON CONFLICT(provider, name) DO NOTHING",
            (provider_value, name),
        )
        return int(
            conn.execute(
                "SELECT id FROM models WHERE provider=? AND name=?",
                (provider_value, name),
            ).fetchone()[0]
        )

    def upsert_user(self, user: NormalizedUser) -> int:
        with self.database.connect() as conn:
            conn.execute(
                """
                INSERT INTO users(
                    stable_key, display_name, provider_user_id, provider,
                    identity_confidence, metadata_json
                ) VALUES(?, ?, ?, ?, ?, ?)
                ON CONFLICT(stable_key) DO UPDATE SET
                    display_name=COALESCE(excluded.display_name, users.display_name),
                    provider_user_id=COALESCE(excluded.provider_user_id, users.provider_user_id),
                    provider=COALESCE(excluded.provider, users.provider),
                    identity_confidence=excluded.identity_confidence,
                    metadata_json=excluded.metadata_json
                """,
                (
                    user.stable_key,
                    user.display_name,
                    user.provider_user_id,
                    user.provider,
                    user.confidence.value,
                    json.dumps(user.metadata, ensure_ascii=False),
                ),
            )
            return int(
                conn.execute(
                    "SELECT id FROM users WHERE stable_key=?",
                    (user.stable_key,),
                ).fetchone()[0]
            )

    def upsert_machine(self, machine: NormalizedMachine) -> int:
        with self.database.connect() as conn:
            conn.execute(
                """
                INSERT INTO machines(stable_key, display_name, os, metadata_json)
                VALUES(?, ?, ?, ?)
                ON CONFLICT(stable_key) DO UPDATE SET
                    display_name=COALESCE(excluded.display_name, machines.display_name),
                    os=COALESCE(excluded.os, machines.os),
                    metadata_json=excluded.metadata_json
                """,
                (
                    machine.stable_key,
                    machine.display_name,
                    machine.os,
                    json.dumps(machine.metadata, ensure_ascii=False),
                ),
            )
            return int(
                conn.execute(
                    "SELECT id FROM machines WHERE stable_key=?",
                    (machine.stable_key,),
                ).fetchone()[0]
            )

    def associate_session_identity(
        self,
        session_id: int,
        user_id: int | None,
        machine_id: int | None,
    ) -> None:
        with self.database.connect() as conn:
            conn.execute(
                """
                UPDATE sessions
                SET user_id=COALESCE(?, user_id),
                    machine_id=COALESCE(?, machine_id)
                WHERE id=?
                """,
                (user_id, machine_id, session_id),
            )

    def upsert_session(self, session: NormalizedSession) -> int:
        with self.database.connect() as conn:
            source_id = self._upsert_source(conn, session.source)
            project_id = self._upsert_project(conn, session.project_path)
            model_id = self.upsert_model(conn, session.model, session.provider)
            conn.execute(
                """
                INSERT INTO sessions(
                    source_id, external_session_id, project_id, started_at, ended_at,
                    originator, provider, model_id, cli_version, raw_file_path, metadata_json
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(source_id, external_session_id) DO UPDATE SET
                    project_id=COALESCE(excluded.project_id, sessions.project_id),
                    started_at=COALESCE(excluded.started_at, sessions.started_at),
                    ended_at=COALESCE(excluded.ended_at, sessions.ended_at),
                    originator=COALESCE(excluded.originator, sessions.originator),
                    provider=COALESCE(excluded.provider, sessions.provider),
                    model_id=COALESCE(excluded.model_id, sessions.model_id),
                    cli_version=COALESCE(excluded.cli_version, sessions.cli_version),
                    raw_file_path=COALESCE(excluded.raw_file_path, sessions.raw_file_path),
                    metadata_json=excluded.metadata_json
                """,
                (
                    source_id,
                    session.external_session_id,
                    project_id,
                    session.started_at,
                    session.ended_at,
                    session.originator,
                    session.provider,
                    model_id,
                    session.cli_version,
                    session.raw_file_path,
                    json.dumps(session.metadata, ensure_ascii=False),
                ),
            )
            row = conn.execute(
                "SELECT id FROM sessions WHERE source_id=? AND external_session_id=?",
                (source_id, session.external_session_id),
            ).fetchone()
            return int(row[0])

    def insert_message(
        self,
        session_id: int,
        turn_id: int | None,
        message: NormalizedMessage,
    ) -> int:
        key = self._event_key(
            "message",
            session_id,
            message.source_file,
            message.source_line,
            message.role,
            message.timestamp,
        )
        with self.database.connect() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO messages(
                    session_id, turn_id, role, phase, timestamp, content, content_type,
                    source_file, source_line, metadata_json, event_key
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    turn_id,
                    message.role,
                    message.phase,
                    message.timestamp,
                    message.content,
                    message.content_type,
                    message.source_file,
                    message.source_line,
                    json.dumps(message.metadata, ensure_ascii=False),
                    key,
                ),
            )
            row = conn.execute(
                "SELECT id FROM messages WHERE event_key=?",
                (key,),
            ).fetchone()
            return int(row[0])

    def insert_cost(
        self,
        session_id: int | None,
        model_id: int | None,
        estimated_raw_cost_usd: float | None,
        observed_cost_usd: float | None,
        **values,
    ) -> int:
        snapshot_key = values.get("snapshot_key")
        event_key = (
            self._event_key("cost_snapshot", snapshot_key)
            if snapshot_key
            else self._event_key(
                "cost",
                session_id,
                model_id,
                values.get("period_start"),
                values.get("period_end"),
                estimated_raw_cost_usd,
                observed_cost_usd,
                values.get("compression_savings_usd"),
                values.get("cache_savings_usd"),
                values.get("pricing_source"),
                values.get("pricing_version"),
            )
        )
        with self.database.connect() as conn:
            conn.execute(
                """
                INSERT INTO costs(
                    session_id, model_id, period_start, period_end,
                    estimated_raw_cost_usd, observed_cost_usd,
                    estimated_cost_after_optimization_usd,
                    compression_savings_usd, cache_savings_usd, total_savings_usd,
                    pricing_source, pricing_version, event_key
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(event_key) DO UPDATE SET
                    session_id=excluded.session_id,
                    model_id=excluded.model_id,
                    period_start=excluded.period_start,
                    period_end=excluded.period_end,
                    estimated_raw_cost_usd=excluded.estimated_raw_cost_usd,
                    observed_cost_usd=excluded.observed_cost_usd,
                    estimated_cost_after_optimization_usd=excluded.estimated_cost_after_optimization_usd,
                    compression_savings_usd=excluded.compression_savings_usd,
                    cache_savings_usd=excluded.cache_savings_usd,
                    total_savings_usd=excluded.total_savings_usd,
                    pricing_source=excluded.pricing_source,
                    pricing_version=excluded.pricing_version
                """,
                (
                    session_id,
                    model_id,
                    values.get("period_start"),
                    values.get("period_end"),
                    estimated_raw_cost_usd,
                    observed_cost_usd,
                    values.get("estimated_cost_after_optimization_usd"),
                    values.get("compression_savings_usd"),
                    values.get("cache_savings_usd"),
                    values.get("total_savings_usd"),
                    values.get("pricing_source"),
                    values.get("pricing_version"),
                    event_key,
                ),
            )
            row = conn.execute(
                "SELECT id FROM costs WHERE event_key=?",
                (event_key,),
            ).fetchone()
            return int(row[0])

    def upsert_turn(self, session_id: int, turn) -> int:
        with self.database.connect() as conn:
            model_id = self.upsert_model(conn, turn.model)
            conn.execute(
                """
                INSERT INTO turns(
                    session_id, external_turn_id, started_at, ended_at, model_id, metadata_json
                ) VALUES(?, ?, ?, ?, ?, ?)
                ON CONFLICT(session_id, external_turn_id) DO UPDATE SET
                    started_at=COALESCE(excluded.started_at, turns.started_at),
                    ended_at=COALESCE(excluded.ended_at, turns.ended_at),
                    model_id=COALESCE(excluded.model_id, turns.model_id),
                    metadata_json=excluded.metadata_json
                """,
                (
                    session_id,
                    turn.external_turn_id,
                    turn.started_at,
                    turn.ended_at,
                    model_id,
                    json.dumps(turn.metadata, ensure_ascii=False),
                ),
            )
            return int(
                conn.execute(
                    "SELECT id FROM turns WHERE session_id=? AND external_turn_id=?",
                    (session_id, turn.external_turn_id),
                ).fetchone()[0]
            )

    def insert_tool_call(self, session_id: int, turn_id: int | None, call) -> int:
        key = self._event_key(
            "tool",
            session_id,
            call.source_file,
            call.source_line,
            call.external_call_id,
            call.name,
        )
        with self.database.connect() as conn:
            provider = call.provider or ""
            category = call.category or "other"
            conn.execute(
                "INSERT INTO tools(name, provider, category) VALUES(?, ?, ?) "
                "ON CONFLICT(name, provider, category) DO NOTHING",
                (call.name, provider, category),
            )
            tool_id = int(
                conn.execute(
                    "SELECT id FROM tools WHERE name=? AND provider=? AND category=?",
                    (call.name, provider, category),
                ).fetchone()[0]
            )
            conn.execute(
                """
                INSERT OR IGNORE INTO tool_calls(
                    session_id, turn_id, tool_id, external_call_id, timestamp, duration_ms, status,
                    input_size, output_size, source_file, source_line, metadata_json, event_key
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    turn_id,
                    tool_id,
                    call.external_call_id,
                    call.timestamp,
                    call.duration_ms,
                    call.status,
                    call.input_size,
                    call.output_size,
                    call.source_file,
                    call.source_line,
                    json.dumps(call.metadata, ensure_ascii=False),
                    key,
                ),
            )
            return int(
                conn.execute(
                    "SELECT id FROM tool_calls WHERE event_key=?",
                    (key,),
                ).fetchone()[0]
            )

    def insert_token_usage(self, session_id: int, turn_id: int | None, usage) -> int:
        key = self._event_key(
            "tokens",
            session_id,
            usage.source_file,
            usage.source_line,
            usage.timestamp,
        )
        with self.database.connect() as conn:
            model_id = self.upsert_model(conn, usage.model)
            conn.execute(
                """
                INSERT OR IGNORE INTO token_usage(
                    session_id, turn_id, timestamp, model_id, input_tokens, cached_input_tokens,
                    cache_write_input_tokens, output_tokens, reasoning_output_tokens, total_tokens,
                    context_window, source_file, source_line, event_key
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    turn_id,
                    usage.timestamp,
                    model_id,
                    usage.input_tokens,
                    usage.cached_input_tokens,
                    usage.cache_write_input_tokens,
                    usage.output_tokens,
                    usage.reasoning_output_tokens,
                    usage.total_tokens,
                    usage.context_window,
                    usage.source_file,
                    usage.source_line,
                    key,
                ),
            )
            return int(
                conn.execute(
                    "SELECT id FROM token_usage WHERE event_key=?",
                    (key,),
                ).fetchone()[0]
            )

    def upsert_agent_evidence(self, session_id: int, evidence) -> int:
        with self.database.connect() as conn:
            conn.execute(
                "INSERT INTO agents(name, type) VALUES(?, ?) "
                "ON CONFLICT(name, type) DO NOTHING",
                (evidence.name, evidence.agent_type),
            )
            agent_id = int(
                conn.execute(
                    "SELECT id FROM agents WHERE name=? AND type=?",
                    (evidence.name, evidence.agent_type),
                ).fetchone()[0]
            )
            parent_id = None
            if evidence.parent_name:
                conn.execute(
                    "INSERT INTO agents(name, type) VALUES(?, 'root') "
                    "ON CONFLICT(name, type) DO NOTHING",
                    (evidence.parent_name,),
                )
                parent_id = int(
                    conn.execute(
                        "SELECT id FROM agents WHERE name=? AND type='root'",
                        (evidence.parent_name,),
                    ).fetchone()[0]
                )
            conn.execute(
                """
                INSERT OR IGNORE INTO session_agents(
                    session_id, agent_id, parent_agent_id, started_at, evidence_type
                ) VALUES(?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    agent_id,
                    parent_id,
                    evidence.timestamp,
                    evidence.evidence_type,
                ),
            )
            return agent_id

    def upsert_skill_evidence(self, session_id: int, evidence) -> int:
        with self.database.connect() as conn:
            source = evidence.source or ""
            version = evidence.version or ""
            conn.execute(
                "INSERT INTO skills(name, source, version) VALUES(?, ?, ?) "
                "ON CONFLICT(name, source, version) DO NOTHING",
                (evidence.name, source, version),
            )
            skill_id = int(
                conn.execute(
                    "SELECT id FROM skills WHERE name=? AND source=? AND version=?",
                    (evidence.name, source, version),
                ).fetchone()[0]
            )
            conn.execute(
                """
                INSERT OR IGNORE INTO session_skills(
                    session_id, skill_id, usage_type, first_seen_at, evidence_type
                ) VALUES(?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    skill_id,
                    evidence.usage_type.value,
                    evidence.timestamp,
                    evidence.evidence_type,
                ),
            )
            return skill_id

    def insert_optimization(self, optimization, session_id: int | None = None) -> int:
        key = self._event_key(
            "optimization",
            optimization.source_file,
            optimization.source_line,
            optimization.timestamp,
            optimization.model,
            optimization.original_tokens,
            optimization.optimized_tokens,
            optimization.tokens_saved,
        )
        with self.database.connect() as conn:
            conn.execute(
                "INSERT INTO optimizers(name, version) VALUES(?, '') "
                "ON CONFLICT(name, version) DO NOTHING",
                (optimization.optimizer,),
            )
            optimizer_id = int(
                conn.execute(
                    "SELECT id FROM optimizers WHERE name=? AND version=''",
                    (optimization.optimizer,),
                ).fetchone()[0]
            )
            model_id = self.upsert_model(conn, optimization.model)
            conn.execute(
                """
                INSERT OR IGNORE INTO optimizations(
                    optimizer_id, session_id, timestamp, model_id, original_tokens, optimized_tokens,
                    tokens_saved, compression_percent, cache_read_tokens, compression_savings_usd,
                    cache_savings_usd, observed_input_cost_usd, correlation_confidence,
                    source_file, source_line, metadata_json, event_key
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    optimizer_id,
                    session_id,
                    optimization.timestamp,
                    model_id,
                    optimization.original_tokens,
                    optimization.optimized_tokens,
                    optimization.tokens_saved,
                    optimization.compression_percent,
                    optimization.cache_read_tokens,
                    optimization.compression_savings_usd,
                    optimization.cache_savings_usd,
                    optimization.observed_input_cost_usd,
                    optimization.confidence.value,
                    optimization.source_file,
                    optimization.source_line,
                    json.dumps(optimization.metadata, ensure_ascii=False),
                    key,
                ),
            )
            return int(
                conn.execute(
                    "SELECT id FROM optimizations WHERE event_key=?",
                    (key,),
                ).fetchone()[0]
            )

    def get_import_state(self, source: str, path: str):
        with self.database.connect() as conn:
            row = conn.execute(
                "SELECT * FROM import_state WHERE source=? AND path=?",
                (source, path),
            ).fetchone()
            return dict(row) if row else None

    def save_import_state(
        self,
        source: str,
        path: str,
        *,
        size: int,
        modified_at: float | None,
        content_hash: str | None,
        last_offset: int,
        status: str = "complete",
    ) -> None:
        with self.database.connect() as conn:
            conn.execute(
                """
                INSERT INTO import_state(
                    source, path, size, modified_at, content_hash, last_offset, status
                ) VALUES(?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(source, path) DO UPDATE SET
                    size=excluded.size,
                    modified_at=excluded.modified_at,
                    content_hash=excluded.content_hash,
                    last_offset=excluded.last_offset,
                    last_imported_at=CURRENT_TIMESTAMP,
                    status=excluded.status
                """,
                (
                    source,
                    path,
                    size,
                    modified_at,
                    content_hash,
                    last_offset,
                    status,
                ),
            )

    def record_import_error(
        self,
        source: str,
        file: str,
        line: int | None,
        error_type: str,
        error_message: str,
    ) -> None:
        with self.database.connect() as conn:
            conn.execute(
                """
                INSERT INTO import_errors(source, file, line, error_type, error_message)
                VALUES(?, ?, ?, ?, ?)
                """,
                (source, file, line, error_type, error_message),
            )

    def session_id_by_external(self, external_session_id: str) -> int | None:
        with self.database.connect() as conn:
            row = conn.execute(
                "SELECT id FROM sessions WHERE external_session_id=? ORDER BY id LIMIT 1",
                (external_session_id,),
            ).fetchone()
            return int(row[0]) if row else None

    def session_candidates(self):
        from agentscope.correlation import SessionCandidate

        with self.database.connect() as conn:
            rows = conn.execute(
                """
                SELECT s.external_session_id, s.started_at, s.ended_at,
                       m.name AS model, p.path AS project_path
                FROM sessions s
                LEFT JOIN models m ON m.id=s.model_id
                LEFT JOIN projects p ON p.id=s.project_id
                """
            ).fetchall()
        return [
            SessionCandidate(
                external_session_id=row["external_session_id"],
                started_at=row["started_at"],
                ended_at=row["ended_at"],
                model=row["model"],
                project_path=row["project_path"],
            )
            for row in rows
        ]
