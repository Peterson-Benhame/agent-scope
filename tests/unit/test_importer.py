import json
import shutil
from pathlib import Path

from agentscope.importer import collect_sources
from agentscope.storage.database import Database
from agentscope.storage.repository import Repository


CODEX_FIXTURE = Path("tests/fixtures/codex/rollout.jsonl")
HEADROOM_FIXTURE = Path("tests/fixtures/headroom")


def make_repo(tmp_path):
    db = Database(tmp_path / "agentscope.db")
    db.initialize()
    return db, Repository(db)


def make_codex_home(tmp_path):
    home = tmp_path / ".codex"
    target = home / "sessions" / "2026" / "08" / "18"
    target.mkdir(parents=True)
    shutil.copy(CODEX_FIXTURE, target / "rollout.jsonl")
    return home, target / "rollout.jsonl"


def test_double_import_is_logically_idempotent(tmp_path):
    db, repo = make_repo(tmp_path)
    codex_home, _ = make_codex_home(tmp_path)
    first = collect_sources(repo, codex_home=codex_home)
    second = collect_sources(repo, codex_home=codex_home)
    assert first.sessions_imported == 1
    assert second.files_skipped == 1
    with db.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0] == 3
        assert conn.execute("SELECT COUNT(*) FROM token_usage").fetchone()[0] == 1


def test_append_import_adds_only_new_logical_event(tmp_path):
    db, repo = make_repo(tmp_path)
    codex_home, rollout = make_codex_home(tmp_path)
    collect_sources(repo, codex_home=codex_home)
    before = rollout.stat().st_size
    new_line = {
        "timestamp": "2026-08-18T22:46:00.000Z",
        "type": "response_item",
        "payload": {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "new reply"}]},
    }
    with rollout.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(new_line) + "\n")
    summary = collect_sources(repo, codex_home=codex_home)
    state = repo.get_import_state("codex", str(rollout))
    assert summary.sessions_imported == 1
    assert state["last_offset"] > before
    with db.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0] == 4
        assert conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0] == 1


def test_import_preserves_source_provenance(tmp_path):
    db, repo = make_repo(tmp_path)
    codex_home, rollout = make_codex_home(tmp_path)
    collect_sources(repo, codex_home=codex_home)
    with db.connect() as conn:
        row = conn.execute("SELECT source_file, source_line FROM messages WHERE role='user'").fetchone()
    assert row["source_file"] == str(rollout)
    assert row["source_line"] > 0


def test_headroom_import_is_idempotent_and_optimizer_is_not_agent(tmp_path):
    db, repo = make_repo(tmp_path)
    headroom_home = tmp_path / ".headroom"
    shutil.copytree(HEADROOM_FIXTURE, headroom_home)
    collect_sources(repo, headroom_home=headroom_home)
    collect_sources(repo, headroom_home=headroom_home)
    with db.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM optimizers WHERE name='headroom'").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM optimizations").fetchone()[0] == 2
        assert conn.execute("SELECT COUNT(*) FROM agents WHERE name='headroom'").fetchone()[0] == 0
