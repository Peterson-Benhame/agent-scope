import shutil
from pathlib import Path

from agentscope.sources.base import CollectRequest, DiscoveryContext
from agentscope.sources.gemini import GeminiAdapter
from agentscope.storage.database import Database
from agentscope.storage.repository import Repository


FIXTURE = Path("tests/fixtures/gemini")


def arrange_home(tmp_path):
    root = tmp_path / ".gemini"
    shutil.copytree(FIXTURE, root)
    session = root / "tmp" / "project-hash" / "chats" / "session-2026-08-18-gemini-session-1.jsonl"
    return root, session


def test_discovers_verified_gemini_session_jsonl(tmp_path):
    root, session = arrange_home(tmp_path)

    discovery = GeminiAdapter().discover(
        DiscoveryContext(user_home=tmp_path, overrides={"gemini": root})
    )

    assert discovery.detected is True
    assert discovery.format_version == "session-jsonl-v1"
    assert discovery.artifacts == (session,)


def test_collects_gemini_messages_and_usage_metadata_idempotently(tmp_path):
    root, _ = arrange_home(tmp_path)
    adapter = GeminiAdapter()
    discovery = adapter.discover(
        DiscoveryContext(user_home=tmp_path, overrides={"gemini": root})
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
            SELECT s.external_session_id, s.started_at, s.ended_at, m.name
            FROM sessions s LEFT JOIN models m ON m.id=s.model_id
            """
        ).fetchone()
        assert session["external_session_id"] == "gemini-session-1"
        assert session["started_at"] == "2026-08-18T13:00:00Z"
        assert session["ended_at"] == "2026-08-18T13:00:03Z"
        assert session["name"] == "gemini-2.5-pro"
        assert conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0] == 2
        usage = conn.execute(
            """
            SELECT input_tokens, cached_input_tokens, output_tokens,
                   reasoning_output_tokens, total_tokens
            FROM token_usage
            """
        ).fetchone()
        assert usage["input_tokens"] == 1000
        assert usage["cached_input_tokens"] == 600
        assert usage["output_tokens"] == 200
        assert usage["reasoning_output_tokens"] == 50
        assert usage["total_tokens"] == 1250


def test_gemini_rejects_unknown_session_structure(tmp_path):
    root = tmp_path / ".gemini"
    chats = root / "tmp" / "future" / "chats"
    chats.mkdir(parents=True)
    (chats / "session-future.jsonl").write_text(
        '{"futureSchema":99}\n', encoding="utf-8"
    )

    discovery = GeminiAdapter().discover(
        DiscoveryContext(user_home=tmp_path, overrides={"gemini": root})
    )

    assert discovery.detected is False
    assert discovery.artifacts == ()
    assert "unsupported" in (discovery.diagnostic or "").lower()


def test_gemini_capabilities_only_claim_verified_metrics():
    capabilities = GeminiAdapter().capabilities()

    assert capabilities.sessions is True
    assert capabilities.messages is True
    assert capabilities.tokens is True
    assert capabilities.cache is True
    assert capabilities.tools is False
    assert capabilities.costs is False
    assert capabilities.agents is False
    assert capabilities.skills is False
    assert capabilities.user_identity is False
