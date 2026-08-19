from pathlib import Path

from agentscope.sources.base import CollectRequest, DiscoveryContext
from agentscope.sources.gemini import GeminiAdapter
from agentscope.storage.database import Database
from agentscope.storage.repository import Repository


FIXTURE = Path("tests/fixtures/gemini/session.jsonl")


def arrange_home(tmp_path):
    root = tmp_path / ".gemini"
    chats = root / "tmp" / "project-hash-1" / "chats"
    chats.mkdir(parents=True)
    target = chats / "session-2026-08-18.jsonl"
    target.write_text(FIXTURE.read_text(encoding="utf-8"), encoding="utf-8")
    return root, target


def test_discovers_verified_gemini_jsonl_layout(tmp_path):
    root, target = arrange_home(tmp_path)

    discovery = GeminiAdapter().discover(
        DiscoveryContext(user_home=tmp_path, overrides={"gemini": root})
    )

    assert discovery.detected is True
    assert discovery.format_version == "jsonl-v1"
    assert discovery.artifacts == (target,)


def test_collects_gemini_session_model_tokens_and_tools(tmp_path):
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
        assert session["ended_at"] == "2026-08-18T13:05:00Z"
        assert session["name"] == "gemini-2.5-pro"
        usage = conn.execute(
            """
            SELECT input_tokens, cached_input_tokens, output_tokens,
                   reasoning_output_tokens, total_tokens
            FROM token_usage
            """
        ).fetchone()
        assert usage["input_tokens"] == 1500
        assert usage["cached_input_tokens"] == 900
        assert usage["output_tokens"] == 250
        assert usage["reasoning_output_tokens"] == 40
        assert usage["total_tokens"] == 1750
        tool = conn.execute(
            "SELECT t.name FROM tool_calls tc JOIN tools t ON t.id=tc.tool_id"
        ).fetchone()
        assert tool["name"] == "read_file"
        assert conn.execute("SELECT COUNT(*) FROM costs").fetchone()[0] == 0


def test_gemini_rejects_unknown_session_structure(tmp_path):
    root = tmp_path / ".gemini"
    chats = root / "tmp" / "future" / "chats"
    chats.mkdir(parents=True)
    (chats / "session-future.jsonl").write_text(
        '{"futureSchema":99}\n',
        encoding="utf-8",
    )

    discovery = GeminiAdapter().discover(
        DiscoveryContext(user_home=tmp_path, overrides={"gemini": root})
    )

    assert discovery.detected is False
    assert discovery.artifacts == ()
    assert "unsupported" in (discovery.diagnostic or "").lower()


def test_gemini_capabilities_match_verified_record_fields():
    capabilities = GeminiAdapter().capabilities()

    assert capabilities.sessions is True
    assert capabilities.messages is True
    assert capabilities.tokens is True
    assert capabilities.cache is True
    assert capabilities.tools is True
    assert capabilities.costs is False
    assert capabilities.user_identity is False
