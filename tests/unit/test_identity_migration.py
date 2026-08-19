import sqlite3

from agentscope.storage.database import Database, SCHEMA_V1


def test_v1_database_migrates_to_identity_schema_without_losing_data(tmp_path):
    path = tmp_path / "agentscope-v1.db"
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA_V1)
    conn.execute("INSERT INTO sources(name, type) VALUES('codex', 'agent-runtime')")
    source_id = conn.execute("SELECT id FROM sources WHERE name='codex'").fetchone()[0]
    conn.execute(
        """
        INSERT INTO sessions(source_id, external_session_id, started_at)
        VALUES(?, 'legacy-session', '2026-08-18T10:00:00Z')
        """,
        (source_id,),
    )
    session_id = conn.execute(
        "SELECT id FROM sessions WHERE external_session_id='legacy-session'"
    ).fetchone()[0]
    conn.execute(
        """
        INSERT INTO token_usage(session_id, timestamp, input_tokens, event_key)
        VALUES(?, '2026-08-18T10:01:00Z', 123, 'legacy-token')
        """,
        (session_id,),
    )
    conn.commit()
    conn.close()

    db = Database(path)
    db.initialize()
    db.initialize()

    with db.connect() as migrated:
        assert migrated.execute("SELECT COUNT(*) FROM sessions").fetchone()[0] == 1
        assert migrated.execute("SELECT SUM(input_tokens) FROM token_usage").fetchone()[0] == 123
        assert migrated.execute(
            "SELECT COUNT(*) FROM schema_migrations WHERE version=2"
        ).fetchone()[0] == 1
        assert migrated.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='users'"
        ).fetchone()[0] == "users"
        assert migrated.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='machines'"
        ).fetchone()[0] == "machines"
        columns = {
            row[1] for row in migrated.execute("PRAGMA table_info(sessions)").fetchall()
        }
        assert {"user_id", "machine_id"}.issubset(columns)
