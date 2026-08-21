import shutil
from pathlib import Path

from agentscope.config import AgentScopeConfig
from agentscope.identity_backfill import backfill_local_identity
from agentscope.importer import collect_registered_sources
from agentscope.storage.database import Database
from agentscope.storage.repository import Repository


CODEX_FIXTURE = Path("tests/fixtures/codex/rollout.jsonl")


def _repo(tmp_path):
    db = Database(tmp_path / "agentscope.db")
    db.initialize()
    return db, Repository(db)


def _codex_home(tmp_path):
    home = tmp_path / ".codex"
    target = home / "sessions" / "2026" / "08" / "18"
    target.mkdir(parents=True)
    shutil.copy(CODEX_FIXTURE, target / "rollout.jsonl")
    return home


def _config(tmp_path, codex_home):
    return AgentScopeConfig.from_env(
        codex_home=codex_home,
        database_path=tmp_path / "agentscope.db",
        enabled_sources={"codex"},
        user_display_name="Dev A",
        machine_display_name="Notebook A",
    )


def test_backfill_attaches_identity_to_historical_session(tmp_path):
    db, repo = _repo(tmp_path)
    codex_home = _codex_home(tmp_path)
    config = _config(tmp_path, codex_home)

    collected = collect_registered_sources(repo, config)
    assert collected.sessions_imported == 1
    with db.connect() as conn:
        conn.execute("UPDATE sessions SET user_id=NULL, machine_id=NULL")

    summary = backfill_local_identity(
        repo,
        config,
        sources=frozenset({"codex"}),
    )

    assert summary.sessions_scanned == 1
    assert summary.sessions_updated == 1
    assert summary.sessions_without_user == 0
    assert summary.sessions_without_machine == 0
    assert summary.errors == 0

    with db.connect() as conn:
        row = conn.execute(
            """
            SELECT COALESCE(u.display_name, u.stable_key) AS user_name,
                   COALESCE(m.display_name, m.stable_key) AS machine_name
            FROM sessions s
            LEFT JOIN users u ON u.id=s.user_id
            LEFT JOIN machines m ON m.id=s.machine_id
            """
        ).fetchone()

    assert row["user_name"] == "Dev A"
    assert row["machine_name"] == "Notebook A"


def test_backfill_is_idempotent(tmp_path):
    db, repo = _repo(tmp_path)
    codex_home = _codex_home(tmp_path)
    config = _config(tmp_path, codex_home)

    collect_registered_sources(repo, config)
    with db.connect() as conn:
        conn.execute("UPDATE sessions SET user_id=NULL, machine_id=NULL")

    first = backfill_local_identity(repo, config, sources=frozenset({"codex"}))
    second = backfill_local_identity(repo, config, sources=frozenset({"codex"}))

    assert first.sessions_updated == 1
    assert second.sessions_updated == 0
    with db.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM machines").fetchone()[0] == 1
