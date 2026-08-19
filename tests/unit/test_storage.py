from agentscope.domain.models import NormalizedMessage, NormalizedSession
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
        "import_state", "import_errors", "schema_migrations"
    }.issubset(names)


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
