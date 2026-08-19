from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


SCHEMA_V1 = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    description TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sources (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    type TEXT NOT NULL,
    version TEXT
);

CREATE TABLE IF NOT EXISTS projects (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    path TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS models (
    id INTEGER PRIMARY KEY,
    provider TEXT NOT NULL DEFAULT '',
    name TEXT NOT NULL,
    UNIQUE(provider, name)
);

CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY,
    source_id INTEGER NOT NULL REFERENCES sources(id),
    external_session_id TEXT NOT NULL,
    project_id INTEGER REFERENCES projects(id),
    started_at TEXT,
    ended_at TEXT,
    originator TEXT,
    provider TEXT,
    model_id INTEGER REFERENCES models(id),
    cli_version TEXT,
    raw_file_path TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    UNIQUE(source_id, external_session_id)
);

CREATE INDEX IF NOT EXISTS idx_sessions_started_at ON sessions(started_at);
CREATE INDEX IF NOT EXISTS idx_sessions_project_id ON sessions(project_id);

CREATE TABLE IF NOT EXISTS turns (
    id INTEGER PRIMARY KEY,
    session_id INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    external_turn_id TEXT NOT NULL,
    started_at TEXT,
    ended_at TEXT,
    model_id INTEGER REFERENCES models(id),
    metadata_json TEXT NOT NULL DEFAULT '{}',
    UNIQUE(session_id, external_turn_id)
);
CREATE INDEX IF NOT EXISTS idx_turns_session_id ON turns(session_id);

CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY,
    session_id INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    turn_id INTEGER REFERENCES turns(id) ON DELETE SET NULL,
    role TEXT NOT NULL,
    phase TEXT,
    timestamp TEXT NOT NULL,
    content TEXT,
    content_type TEXT NOT NULL DEFAULT 'text',
    source_file TEXT,
    source_line INTEGER,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    event_key TEXT NOT NULL UNIQUE
);
CREATE INDEX IF NOT EXISTS idx_messages_session_id ON messages(session_id);
CREATE INDEX IF NOT EXISTS idx_messages_turn_id ON messages(turn_id);

CREATE TABLE IF NOT EXISTS agents (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    type TEXT NOT NULL,
    UNIQUE(name, type)
);

CREATE TABLE IF NOT EXISTS session_agents (
    id INTEGER PRIMARY KEY,
    session_id INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    agent_id INTEGER NOT NULL REFERENCES agents(id),
    parent_agent_id INTEGER REFERENCES agents(id),
    started_at TEXT,
    ended_at TEXT,
    evidence_type TEXT NOT NULL,
    UNIQUE(session_id, agent_id, parent_agent_id, evidence_type)
);

CREATE TABLE IF NOT EXISTS skills (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT '',
    version TEXT NOT NULL DEFAULT '',
    UNIQUE(name, source, version)
);

CREATE TABLE IF NOT EXISTS session_skills (
    id INTEGER PRIMARY KEY,
    session_id INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    skill_id INTEGER NOT NULL REFERENCES skills(id),
    usage_type TEXT NOT NULL,
    first_seen_at TEXT,
    evidence_type TEXT NOT NULL,
    UNIQUE(session_id, skill_id, usage_type, evidence_type)
);

CREATE TABLE IF NOT EXISTS tools (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    provider TEXT NOT NULL DEFAULT '',
    category TEXT NOT NULL DEFAULT '',
    UNIQUE(name, provider, category)
);

CREATE TABLE IF NOT EXISTS tool_calls (
    id INTEGER PRIMARY KEY,
    session_id INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    turn_id INTEGER REFERENCES turns(id) ON DELETE SET NULL,
    tool_id INTEGER NOT NULL REFERENCES tools(id),
    external_call_id TEXT,
    timestamp TEXT NOT NULL,
    duration_ms REAL,
    status TEXT,
    input_size INTEGER,
    output_size INTEGER,
    source_file TEXT,
    source_line INTEGER,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    event_key TEXT NOT NULL UNIQUE
);
CREATE INDEX IF NOT EXISTS idx_tool_calls_session_id ON tool_calls(session_id);

CREATE TABLE IF NOT EXISTS token_usage (
    id INTEGER PRIMARY KEY,
    session_id INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    turn_id INTEGER REFERENCES turns(id) ON DELETE SET NULL,
    timestamp TEXT NOT NULL,
    model_id INTEGER REFERENCES models(id),
    input_tokens INTEGER,
    cached_input_tokens INTEGER,
    cache_write_input_tokens INTEGER,
    output_tokens INTEGER,
    reasoning_output_tokens INTEGER,
    total_tokens INTEGER,
    context_window INTEGER,
    source_file TEXT,
    source_line INTEGER,
    event_key TEXT NOT NULL UNIQUE
);
CREATE INDEX IF NOT EXISTS idx_token_usage_session_id ON token_usage(session_id);
CREATE INDEX IF NOT EXISTS idx_token_usage_timestamp ON token_usage(timestamp);

CREATE TABLE IF NOT EXISTS optimizers (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    version TEXT NOT NULL DEFAULT '',
    UNIQUE(name, version)
);

CREATE TABLE IF NOT EXISTS optimizations (
    id INTEGER PRIMARY KEY,
    optimizer_id INTEGER NOT NULL REFERENCES optimizers(id),
    session_id INTEGER REFERENCES sessions(id) ON DELETE SET NULL,
    timestamp TEXT NOT NULL,
    model_id INTEGER REFERENCES models(id),
    original_tokens INTEGER,
    optimized_tokens INTEGER,
    tokens_saved INTEGER,
    compression_percent REAL,
    cache_read_tokens INTEGER,
    compression_savings_usd REAL,
    cache_savings_usd REAL,
    observed_input_cost_usd REAL,
    correlation_confidence TEXT NOT NULL DEFAULT 'unknown',
    source_file TEXT,
    source_line INTEGER,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    event_key TEXT NOT NULL UNIQUE
);
CREATE INDEX IF NOT EXISTS idx_optimizations_session_id ON optimizations(session_id);
CREATE INDEX IF NOT EXISTS idx_optimizations_timestamp ON optimizations(timestamp);

CREATE TABLE IF NOT EXISTS costs (
    id INTEGER PRIMARY KEY,
    session_id INTEGER REFERENCES sessions(id) ON DELETE CASCADE,
    model_id INTEGER REFERENCES models(id),
    period_start TEXT,
    period_end TEXT,
    estimated_raw_cost_usd REAL,
    observed_cost_usd REAL,
    estimated_cost_after_optimization_usd REAL,
    compression_savings_usd REAL,
    cache_savings_usd REAL,
    total_savings_usd REAL,
    pricing_source TEXT,
    pricing_version TEXT,
    event_key TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS import_state (
    id INTEGER PRIMARY KEY,
    source TEXT NOT NULL,
    path TEXT NOT NULL,
    size INTEGER NOT NULL DEFAULT 0,
    modified_at REAL,
    content_hash TEXT,
    last_offset INTEGER NOT NULL DEFAULT 0,
    last_imported_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    status TEXT NOT NULL DEFAULT 'complete',
    UNIQUE(source, path)
);

CREATE TABLE IF NOT EXISTS import_errors (
    id INTEGER PRIMARY KEY,
    source TEXT NOT NULL,
    file TEXT NOT NULL,
    line INTEGER,
    error_type TEXT NOT NULL,
    error_message TEXT NOT NULL,
    timestamp TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


SCHEMA_V2 = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    stable_key TEXT NOT NULL UNIQUE,
    display_name TEXT,
    provider_user_id TEXT,
    provider TEXT,
    identity_confidence TEXT NOT NULL DEFAULT 'unknown',
    metadata_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS machines (
    id INTEGER PRIMARY KEY,
    stable_key TEXT NOT NULL UNIQUE,
    display_name TEXT,
    os TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);
"""


SCHEMA_V3 = """
CREATE TABLE IF NOT EXISTS team_bundles (
    bundle_id TEXT PRIMARY KEY,
    schema_version INTEGER NOT NULL,
    imported_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    organization TEXT,
    team TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS team_event_provenance (
    event_key TEXT NOT NULL,
    bundle_id TEXT NOT NULL REFERENCES team_bundles(bundle_id) ON DELETE CASCADE,
    source TEXT,
    user_key TEXT,
    machine_key TEXT,
    PRIMARY KEY(event_key, bundle_id)
);
CREATE INDEX IF NOT EXISTS idx_team_event_provenance_event_key
    ON team_event_provenance(event_key);
"""


SCHEMA_V4 = """
CREATE TABLE IF NOT EXISTS model_pricing (
    id INTEGER PRIMARY KEY,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    pricing_scope TEXT NOT NULL,
    service_tier TEXT NOT NULL,
    context_type TEXT NOT NULL,
    input_per_1m_usd REAL,
    cached_input_per_1m_usd REAL,
    cache_write_per_1m_usd REAL,
    output_per_1m_usd REAL,
    valid_from TEXT NOT NULL,
    valid_to TEXT,
    valid_from_basis TEXT NOT NULL,
    source_url TEXT NOT NULL,
    source_version TEXT NOT NULL,
    source_hash TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    record_key TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_model_pricing_lookup
    ON model_pricing(provider, model, pricing_scope, service_tier, context_type, valid_from);
"""


class Database:
    def __init__(self, path: Path | str):
        self.path = Path(path)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    @staticmethod
    def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
        return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})")}

    def _migrate_v2(self, conn: sqlite3.Connection) -> None:
        conn.executescript(SCHEMA_V2)
        columns = self._columns(conn, "sessions")
        if "user_id" not in columns:
            conn.execute(
                "ALTER TABLE sessions ADD COLUMN user_id INTEGER REFERENCES users(id)"
            )
        if "machine_id" not in columns:
            conn.execute(
                "ALTER TABLE sessions ADD COLUMN machine_id INTEGER REFERENCES machines(id)"
            )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions(user_id)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_sessions_machine_id ON sessions(machine_id)"
        )
        conn.execute(
            "INSERT OR IGNORE INTO schema_migrations(version, description) VALUES(2, ?)",
            ("Add user and machine identity",),
        )

    def _migrate_v3(self, conn: sqlite3.Connection) -> None:
        conn.executescript(SCHEMA_V3)
        conn.execute(
            "INSERT OR IGNORE INTO schema_migrations(version, description) VALUES(3, ?)",
            ("Add team bundle provenance",),
        )

    def _migrate_v4(self, conn: sqlite3.Connection) -> None:
        conn.executescript(SCHEMA_V4)
        conn.execute(
            "INSERT OR IGNORE INTO schema_migrations(version, description) VALUES(4, ?)",
            ("Add versioned model pricing catalog",),
        )

    def _migrate_v5(self, conn: sqlite3.Connection) -> None:
        columns = self._columns(conn, "token_usage")
        if "token_source" not in columns:
            conn.execute(
                "ALTER TABLE token_usage ADD COLUMN token_source TEXT NOT NULL "
                "DEFAULT 'source_reported'"
            )
        conn.execute(
            "INSERT OR IGNORE INTO schema_migrations(version, description) VALUES(5, ?)",
            ("Add token usage provenance",),
        )

    def initialize(self) -> None:
        with self.connect() as conn:
            conn.executescript(SCHEMA_V1)
            conn.execute(
                "INSERT OR IGNORE INTO schema_migrations(version, description) VALUES(1, ?)",
                ("Initial AgentScope schema",),
            )
            self._migrate_v2(conn)
            self._migrate_v3(conn)
            self._migrate_v4(conn)
            self._migrate_v5(conn)