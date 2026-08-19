import sqlite3

from agentscope.domain.models import (
    IdentityConfidence,
    NormalizedMachine,
    NormalizedMessage,
    NormalizedSession,
    NormalizedUser,
)
from agentscope.storage.database import Database
from agentscope.storage.repository import Repository


def test_database_initializes_required_schema(tmp_path):
    db = Database(tmp_path / "agentscope.db")
    db.initialize()
    with db.connect() as conn:
        names = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {
        "sources", "projects", "models", "sessions", "turns", "messages",
        "agents", "session_agents", "skills", "session_skills", "tools",
        "tool_calls", "token_usage", "optimizers", "optimizations", "costs",
        "import_state", "import_errors", "schema_migrations", "users", "machines",
        "team_bundles", "team_event_provenance", "model_pricing",
    }.issubset(names)


def test_v1_database_migrates_additively_and_idempotently(tmp_path):
    path = tmp_path / "v1.db"
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE schema_migrations (
            version INTEGER PRIMARY KEY,
            applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            description TEXT NOT NULL
        );
        INSERT INTO schema_migrations(version, description)
        VALUES(1, 'Initial AgentScope schema');

        CREATE TABLE sources (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            type TEXT NOT NULL,
            version TEXT
        );
        INSERT INTO sources(id, name, type) VALUES(1, 'codex', 'codex');

        CREATE TABLE sessions (
            id INTEGER PRIMARY KEY,
            source_id INTEGER NOT NULL REFERENCES sources(id),
            external_session_id TEXT NOT NULL,
            project_id INTEGER,
            started_at TEXT,
            ended_at TEXT,
            originator TEXT,
            provider TEXT,
            model_id INTEGER,
            cli_version TEXT,
            raw_file_path TEXT,
            metadata_json TEXT NOT NULL DEFAULT '{}',
            UNIQUE(source_id, external_session_id)
        );
        INSERT INTO sessions(id, source_id, external_session_id, started_at)
        VALUES(1, 1, 'legacy-session', '2026-08-18T10:00:00Z');
        """
    )
    conn.commit()
    conn.close()

    db = Database(path)
    db.initialize()
    db.initialize()

    with db.connect() as migrated:
        names = {
            row[0]
            for row in migrated.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        session_columns = {
            row[1] for row in migrated.execute("PRAGMA table_info(sessions)")
        }
        token_columns = {
            row[1] for row in migrated.execute("PRAGMA table_info(token_usage)")
        }
        versions = [
            row[0]
            for row in migrated.execute(
                "SELECT version FROM schema_migrations ORDER BY version"
            )
        ]
        legacy = migrated.execute(
            "SELECT external_session_id, started_at FROM sessions WHERE id=1"
        ).fetchone()

    assert {
        "users", "machines", "team_bundles", "team_event_provenance", "model_pricing"
    }.issubset(names)
    assert {"user_id", "machine_id"}.issubset(session_columns)
    assert "token_source" in token_columns
    assert versions == [1, 2, 3, 4, 5]
    assert legacy[0] == "legacy-session"
    assert legacy[1] == "2026-08-18T10:00:00Z"


def test_foreign_keys_are_enabled(tmp_path):
    db = Database(tmp_path / "agentscope.db")
    db.initialize()
    with db.connect() as conn:
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1


def test_upsert_session_is_idempotent(tmp_path):
    db = Database(tmp_path / "agentscope.db")
    db.initialize()
    repo = Repository(db)
    session = NormalizedSession(external_session_id="s1", source="codex", project_path="C:/demo")
    first = repo.upsert_session(session)
    second = repo.upsert_session(session)
    assert first == second
    with db.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0] == 1


def test_identity_upserts_use_stable_keys_not_display_labels(tmp_path):
    db = Database(tmp_path / "agentscope.db")
    db.initialize()
    repo = Repository(db)

    first_user = repo.upsert_user(
        NormalizedUser(
            stable_key="user-1",
            display_name="Peterson",
            provider="local",
            confidence=IdentityConfidence.INFERRED,
        )
    )
    second_user = repo.upsert_user(
        NormalizedUser(
            stable_key="user-1",
            display_name="Peterson Benhame",
            provider="local",
            confidence=IdentityConfidence.INFERRED,
        )
    )
    another_user = repo.upsert_user(
        NormalizedUser(
            stable_key="user-2",
            display_name="Peterson Benhame",
            confidence=IdentityConfidence.UNKNOWN,
        )
    )

    first_machine = repo.upsert_machine(
        NormalizedMachine(stable_key="machine-1", display_name="Notebook")
    )
    second_machine = repo.upsert_machine(
        NormalizedMachine(stable_key="machine-1", display_name="Notebook novo")
    )

    assert first_user == second_user
    assert another_user != first_user
    assert first_machine == second_machine

    with db.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 2
        assert conn.execute("SELECT COUNT(*) FROM machines").fetchone()[0] == 1
        assert conn.execute(
            "SELECT display_name FROM users WHERE stable_key='user-1'"
        ).fetchone()[0] == "Peterson Benhame"
        assert conn.execute(
            "SELECT display_name FROM machines WHERE stable_key='machine-1'"
        ).fetchone()[0] == "Notebook novo"


def test_session_can_be_associated_with_user_and_machine(tmp_path):
    db = Database(tmp_path / "agentscope.db")
    db.initialize()
    repo = Repository(db)
    session_id = repo.upsert_session(
        NormalizedSession(external_session_id="s1", source="codex")
    )
    user_id = repo.upsert_user(NormalizedUser(stable_key="user-1"))
    machine_id = repo.upsert_machine(NormalizedMachine(stable_key="machine-1"))

    repo.associate_session_identity(session_id, user_id, machine_id)

    with db.connect() as conn:
        row = conn.execute(
            "SELECT user_id, machine_id FROM sessions WHERE id=?",
            (session_id,),
        ).fetchone()
    assert row[0] == user_id
    assert row[1] == machine_id


def test_message_provenance_prevents_duplicate_event(tmp_path):
    db = Database(tmp_path / "agentscope.db")
    db.initialize()
    repo = Repository(db)
    sid = repo.upsert_session(NormalizedSession(external_session_id="s1", source="codex"))
    message = NormalizedMessage(
        role="user", timestamp="2026-08-18T10:00:00Z", content="secret",
        source_file="rollout.jsonl", source_line=10,
    )
    repo.insert_message(sid, None, message)
    repo.insert_message(sid, None, message)
    with db.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0] == 1


def test_unknown_cost_is_stored_as_null_not_zero(tmp_path):
    db = Database(tmp_path / "agentscope.db")
    db.initialize()
    repo = Repository(db)
    sid = repo.upsert_session(NormalizedSession(external_session_id="s1", source="codex"))
    repo.insert_cost(session_id=sid, model_id=None, estimated_raw_cost_usd=None, observed_cost_usd=None)
    with db.connect() as conn:
        row = conn.execute("SELECT estimated_raw_cost_usd, observed_cost_usd FROM costs").fetchone()
    assert row[0] is None
    assert row[1] is None
