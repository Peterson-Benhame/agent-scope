import shutil
from pathlib import Path

from agentscope.sources.base import CollectRequest, DiscoveryContext
from agentscope.sources.kimi import KimiAdapter
from agentscope.storage.database import Database
from agentscope.storage.repository import Repository


FIXTURE_ROOT = Path("tests/fixtures/kimi")


def arrange_home(tmp_path):
    root = tmp_path / ".kimi-code"
    shutil.copytree(FIXTURE_ROOT, root)
    return root


def test_discovers_verified_kimi_index_state_layout(tmp_path):
    root = arrange_home(tmp_path)

    discovery = KimiAdapter().discover(
        DiscoveryContext(user_home=tmp_path, overrides={"kimi": root})
    )

    assert discovery.detected is True
    assert discovery.format_version == "index-state-v1"
    assert discovery.artifacts == (root / "session_index.jsonl",)


def test_collects_kimi_session_metadata_without_guessing_wire_records(tmp_path):
    root = arrange_home(tmp_path)
    adapter = KimiAdapter()
    discovery = adapter.discover(
        DiscoveryContext(user_home=tmp_path, overrides={"kimi": root})
    )
    db = Database(tmp_path / "agentscope.db")
    db.initialize()
    repo = Repository(db)

    first = adapter.collect(CollectRequest(repository=repo, discovery=discovery))
    second = adapter.collect(CollectRequest(repository=repo, discovery=discovery))

    assert first.sessions_imported == 1
    assert first.errors == 0
    assert second.files_skipped == 1
    with db.connect() as conn:
        session = conn.execute(
            """
            SELECT s.external_session_id, s.started_at, s.ended_at, p.path, m.name
            FROM sessions s
            LEFT JOIN projects p ON p.id=s.project_id
            LEFT JOIN models m ON m.id=s.model_id
            """
        ).fetchone()
        assert session["external_session_id"] == "kimi-session-1"
        assert session["started_at"] == "2026-08-18T12:00:00Z"
        assert session["ended_at"] == "2026-08-18T12:05:00Z"
        assert session["path"] == r"C:\work\kimi-demo"
        assert session["name"] is None
        assert conn.execute("SELECT COUNT(*) FROM token_usage").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM tool_calls").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM skills").fetchone()[0] == 0


def test_kimi_rejects_index_entries_without_verified_state(tmp_path):
    root = tmp_path / ".kimi-code"
    root.mkdir()
    (root / "session_index.jsonl").write_text(
        '{"sessionId":"future","sessionDir":"missing","workDir":"C:\\\\work"}\n',
        encoding="utf-8",
    )

    discovery = KimiAdapter().discover(
        DiscoveryContext(user_home=tmp_path, overrides={"kimi": root})
    )

    assert discovery.detected is False
    assert discovery.artifacts == ()
    assert "state" in (discovery.diagnostic or "").lower()


def test_kimi_capabilities_only_claim_verified_session_metadata():
    capabilities = KimiAdapter().capabilities()

    assert capabilities.sessions is True
    assert capabilities.messages is False
    assert capabilities.tokens is False
    assert capabilities.cache is False
    assert capabilities.costs is False
    assert capabilities.tools is False
    assert capabilities.agents is False
    assert capabilities.skills is False
    assert capabilities.user_identity is False
