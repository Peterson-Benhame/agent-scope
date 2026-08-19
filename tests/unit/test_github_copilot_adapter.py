from pathlib import Path

from agentscope.sources.base import CollectRequest, DiscoveryContext
from agentscope.sources.github_copilot import GitHubCopilotAdapter
from agentscope.storage.database import Database
from agentscope.storage.repository import Repository


FIXTURE = Path("tests/fixtures/github_copilot/events.jsonl")


def arrange_home(tmp_path, *, version: int = 1):
    root = tmp_path / ".copilot"
    state = root / "session-state" / "copilot-session-1"
    state.mkdir(parents=True)
    target = state / "events.jsonl"
    text = FIXTURE.read_text(encoding="utf-8")
    if version != 1:
        text = text.replace('"version":1', f'"version":{version}', 1)
    target.write_text(text, encoding="utf-8")
    return root, target


def test_discovers_verified_copilot_events_v1(tmp_path):
    root, target = arrange_home(tmp_path)

    discovery = GitHubCopilotAdapter().discover(
        DiscoveryContext(user_home=tmp_path, overrides={"github_copilot": root})
    )

    assert discovery.detected is True
    assert discovery.format_version == "events-v1"
    assert discovery.artifacts == (target,)


def test_collects_copilot_session_tokens_cache_and_tool_without_usd_cost(tmp_path):
    root, target = arrange_home(tmp_path)
    before = target.stat().st_mtime_ns
    adapter = GitHubCopilotAdapter()
    discovery = adapter.discover(
        DiscoveryContext(user_home=tmp_path, overrides={"github_copilot": root})
    )
    db = Database(tmp_path / "agentscope.db")
    db.initialize()
    repo = Repository(db)

    first = adapter.collect(CollectRequest(repository=repo, discovery=discovery))
    second = adapter.collect(CollectRequest(repository=repo, discovery=discovery))

    assert first.sessions_imported == 1
    assert second.files_skipped == 1
    assert target.stat().st_mtime_ns == before
    with db.connect() as conn:
        session = conn.execute(
            """
            SELECT s.external_session_id, p.path, m.name
            FROM sessions s
            LEFT JOIN projects p ON p.id=s.project_id
            LEFT JOIN models m ON m.id=s.model_id
            """
        ).fetchone()
        assert session["external_session_id"] == "copilot-session-1"
        assert session["path"] == r"C:\work\copilot-demo"
        assert session["name"] == "gpt-5.4"
        usage = conn.execute(
            """
            SELECT input_tokens, cached_input_tokens, cache_write_input_tokens,
                   output_tokens, reasoning_output_tokens, total_tokens
            FROM token_usage
            """
        ).fetchone()
        assert usage["input_tokens"] == 2000
        assert usage["cached_input_tokens"] == 1200
        assert usage["cache_write_input_tokens"] == 100
        assert usage["output_tokens"] == 300
        assert usage["reasoning_output_tokens"] == 50
        assert usage["total_tokens"] == 2300
        tool = conn.execute(
            "SELECT t.name FROM tool_calls tc JOIN tools t ON t.id=tc.tool_id"
        ).fetchone()
        assert tool["name"] == "shell"
        assert conn.execute("SELECT COUNT(*) FROM costs").fetchone()[0] == 0


def test_copilot_rejects_unknown_event_schema_version(tmp_path):
    root, _ = arrange_home(tmp_path, version=9)

    discovery = GitHubCopilotAdapter().discover(
        DiscoveryContext(user_home=tmp_path, overrides={"github_copilot": root})
    )

    assert discovery.detected is False
    assert discovery.artifacts == ()
    assert discovery.diagnostic == "github_copilot unsupported format version: 9"


def test_copilot_capabilities_do_not_claim_usd_cost_or_user_identity():
    capabilities = GitHubCopilotAdapter().capabilities()

    assert capabilities.sessions is True
    assert capabilities.messages is True
    assert capabilities.tokens is True
    assert capabilities.cache is True
    assert capabilities.tools is True
    assert capabilities.costs is False
    assert capabilities.user_identity is False
