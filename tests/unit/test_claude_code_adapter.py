from pathlib import Path

from agentscope.sources.base import CollectRequest, DiscoveryContext
from agentscope.sources.claude_code import ClaudeCodeAdapter
from agentscope.storage.database import Database
from agentscope.storage.repository import Repository


FIXTURE = Path("tests/fixtures/claude_code/session.jsonl")


def test_discovers_verified_claude_jsonl_layout(tmp_path):
    root = tmp_path / ".claude"
    project = root / "projects" / "-work-claude-demo"
    project.mkdir(parents=True)
    target = project / "claude-session-1.jsonl"
    target.write_text(FIXTURE.read_text(encoding="utf-8"), encoding="utf-8")

    discovery = ClaudeCodeAdapter().discover(
        DiscoveryContext(user_home=tmp_path, overrides={"claude_code": root})
    )

    assert discovery.detected is True
    assert discovery.format_version == "jsonl-v1"
    assert discovery.artifacts == (target,)


def test_collects_explicit_claude_session_model_tokens_and_tools(tmp_path):
    root = tmp_path / ".claude"
    project = root / "projects" / "-work-claude-demo"
    project.mkdir(parents=True)
    target = project / "claude-session-1.jsonl"
    target.write_text(FIXTURE.read_text(encoding="utf-8"), encoding="utf-8")

    adapter = ClaudeCodeAdapter()
    discovery = adapter.discover(
        DiscoveryContext(user_home=tmp_path, overrides={"claude_code": root})
    )
    db = Database(tmp_path / "agentscope.db")
    db.initialize()
    repo = Repository(db)

    summary = adapter.collect(CollectRequest(repository=repo, discovery=discovery))

    assert summary.sessions_imported == 1
    assert summary.errors == 0
    with db.connect() as conn:
        session = conn.execute(
            """
            SELECT s.external_session_id, p.path, m.name
            FROM sessions s
            LEFT JOIN projects p ON p.id=s.project_id
            LEFT JOIN models m ON m.id=s.model_id
            """
        ).fetchone()
        assert session["external_session_id"] == "claude-session-1"
        assert session["path"] == r"C:\work\claude-demo"
        assert session["name"] == "claude-sonnet-4-6"
        usage = conn.execute(
            """
            SELECT input_tokens, cached_input_tokens, cache_write_input_tokens,
                   output_tokens, total_tokens
            FROM token_usage
            """
        ).fetchone()
        assert usage["input_tokens"] == 1000
        assert usage["cached_input_tokens"] == 700
        assert usage["cache_write_input_tokens"] == 100
        assert usage["output_tokens"] == 200
        assert usage["total_tokens"] == 1200
        tool = conn.execute(
            "SELECT t.name FROM tool_calls tc JOIN tools t ON t.id=tc.tool_id"
        ).fetchone()
        assert tool["name"] == "Read"


def test_unknown_claude_structure_is_reported_not_guessed(tmp_path):
    root = tmp_path / ".claude"
    project = root / "projects" / "-work-unknown"
    project.mkdir(parents=True)
    target = project / "unknown.jsonl"
    target.write_text('{"type":"new_future_record","formatVersion":99}\n', encoding="utf-8")

    discovery = ClaudeCodeAdapter().discover(
        DiscoveryContext(user_home=tmp_path, overrides={"claude_code": root})
    )

    assert discovery.detected is False
    assert discovery.artifacts == ()
    assert "unsupported" in (discovery.diagnostic or "").lower()


def test_claude_capabilities_do_not_claim_unavailable_costs_or_identity():
    capabilities = ClaudeCodeAdapter().capabilities()

    assert capabilities.sessions is True
    assert capabilities.messages is True
    assert capabilities.tokens is True
    assert capabilities.cache is True
    assert capabilities.tools is True
    assert capabilities.costs is False
    assert capabilities.user_identity is False
