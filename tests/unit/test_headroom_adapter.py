import shutil
from pathlib import Path

from agentscope.sources.base import CollectRequest, DiscoveryContext
from agentscope.sources.headroom import HeadroomAdapter
from agentscope.storage.database import Database
from agentscope.storage.repository import Repository


FIXTURE = Path("tests/fixtures/headroom")


def make_repo(tmp_path):
    db = Database(tmp_path / "agentscope.db")
    db.initialize()
    return db, Repository(db)


def make_headroom_home(tmp_path):
    home = tmp_path / ".headroom"
    shutil.copytree(FIXTURE, home)
    return home


def test_headroom_adapter_discovers_only_supported_state_files(tmp_path):
    home = make_headroom_home(tmp_path)
    (home / "unrelated.json").write_text("{}", encoding="utf-8")
    adapter = HeadroomAdapter()

    discovery = adapter.discover(
        DiscoveryContext(user_home=tmp_path, overrides={"headroom": home})
    )

    names = {path.name for path in discovery.artifacts}
    assert discovery.source == "headroom"
    assert discovery.detected is True
    assert "proxy_savings.json" in names
    assert "session_stats.jsonl" in names
    assert "unrelated.json" not in names


def test_headroom_adapter_capabilities_do_not_claim_agents():
    capabilities = HeadroomAdapter().capabilities()

    assert capabilities.optimizations is True
    assert capabilities.cache is True
    assert capabilities.costs is True
    assert capabilities.agents is False
    assert capabilities.sessions is False


def test_headroom_adapter_collect_is_idempotent_and_replaces_snapshot(tmp_path):
    db, repo = make_repo(tmp_path)
    home = make_headroom_home(tmp_path)
    adapter = HeadroomAdapter()
    discovery = adapter.discover(
        DiscoveryContext(user_home=tmp_path, overrides={"headroom": home})
    )

    first = adapter.collect(CollectRequest(repository=repo, discovery=discovery))
    second = adapter.collect(CollectRequest(repository=repo, discovery=discovery))

    assert first.files_seen == len(discovery.artifacts)
    assert first.optimizations_imported == 2
    assert second.files_skipped == len(discovery.artifacts)
    with db.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM optimizations").fetchone()[0] == 2
        assert conn.execute(
            "SELECT COUNT(*) FROM costs WHERE pricing_source='headroom:lifetime'"
        ).fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM agents WHERE name='headroom'").fetchone()[0] == 0
