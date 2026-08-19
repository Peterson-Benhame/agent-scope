import shutil
from pathlib import Path

from agentscope.sources.base import CollectRequest, DiscoveryContext
from agentscope.sources.codex import CodexAdapter
from agentscope.storage.database import Database
from agentscope.storage.repository import Repository


FIXTURE = Path("tests/fixtures/codex/rollout.jsonl")


def make_repo(tmp_path):
    db = Database(tmp_path / "agentscope.db")
    db.initialize()
    return db, Repository(db)


def make_codex_home(tmp_path):
    home = tmp_path / ".codex"
    target = home / "sessions" / "2026" / "08" / "18"
    target.mkdir(parents=True)
    rollout = target / "rollout.jsonl"
    shutil.copy(FIXTURE, rollout)
    return home, rollout


def test_codex_adapter_discovers_rollout_files_from_override(tmp_path):
    home, rollout = make_codex_home(tmp_path)
    adapter = CodexAdapter()

    discovery = adapter.discover(
        DiscoveryContext(user_home=tmp_path, overrides={"codex": home})
    )

    assert discovery.source == "codex"
    assert discovery.detected is True
    assert discovery.roots == (home,)
    assert discovery.artifacts == (rollout,)
    assert discovery.format_version == "rollout-jsonl"


def test_codex_adapter_declares_only_supported_capabilities():
    capabilities = CodexAdapter().capabilities()

    assert capabilities.sessions is True
    assert capabilities.messages is True
    assert capabilities.tokens is True
    assert capabilities.tools is True
    assert capabilities.agents is True
    assert capabilities.skills is True
    assert capabilities.cache is True
    assert capabilities.costs is False
    assert capabilities.optimizations is False
    assert capabilities.user_identity is False


def test_codex_adapter_collect_is_idempotent(tmp_path):
    db, repo = make_repo(tmp_path)
    home, _ = make_codex_home(tmp_path)
    adapter = CodexAdapter()
    discovery = adapter.discover(
        DiscoveryContext(user_home=tmp_path, overrides={"codex": home})
    )

    first = adapter.collect(CollectRequest(repository=repo, discovery=discovery))
    second = adapter.collect(CollectRequest(repository=repo, discovery=discovery))

    assert first.files_seen == 1
    assert first.files_imported == 1
    assert first.sessions_imported == 1
    assert second.files_seen == 1
    assert second.files_skipped == 1
    with db.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0] == 3
        assert conn.execute("SELECT COUNT(*) FROM token_usage").fetchone()[0] == 1
