import shutil
from pathlib import Path

from agentscope.sources.base import CollectRequest, DiscoveryContext
from agentscope.sources.kimi import KimiAdapter
from agentscope.storage.database import Database
from agentscope.storage.repository import Repository


FIXTURE = Path("tests/fixtures/kimi")


def arrange_home(tmp_path):
    root = tmp_path / ".kimi-code"
    shutil.copytree(FIXTURE, root)
    state = root / "sessions" / "wd-demo" / "kimi-session-1" / "state.json"
    return root, state


def test_discovers_verified_kimi_session_layout(tmp_path):
    root, state = arrange_home(tmp_path)

    discovery = KimiAdapter().discover(
        DiscoveryContext(user_home=tmp_path, overrides={"kimi": root})
    )

    assert discovery.detected is True
    assert discovery.format_version == "session-v1"
    assert discovery.artifacts == (state,)


def test_collects_kimi_context_and_cache_token_usage_idempotently(tmp_path):
    root, _ = arrange_home(tmp_path)
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
            SELECT s.external_session_id, p.path
            FROM sessions s LEFT JOIN projects p ON p.id=s.project_id
            """
        ).fetchone()
        assert session["external_session_id"] == "kimi-session-1"
        assert session["path"] == r"C:\work\kimi-demo"
        usage = conn.execute(
            """
            SELECT input_tokens, cached_input_tokens, cache_write_input_tokens,
                   output_tokens, total_tokens, context_window
            FROM token_usage
            """
        ).fetchone()
        assert usage["input_tokens"] == 7426
        assert usage["cached_input_tokens"] == 5120
        assert usage["cache_write_input_tokens"] == 0
        assert usage["output_tokens"] == 420
        assert usage["total_tokens"] == 7846
        assert usage["context_window"] == 262144


def test_unknown_kimi_state_structure_is_not_guessed(tmp_path):
    root = tmp_path / ".kimi-code"
    session = root / "sessions" / "wd" / "future"
    session.mkdir(parents=True)
    (session / "state.json").write_text('{"futureSchema":99}\n', encoding="utf-8")

    discovery = KimiAdapter().discover(
        DiscoveryContext(user_home=tmp_path, overrides={"kimi": root})
    )

    assert discovery.detected is False
    assert discovery.artifacts == ()
    assert "unsupported" in (discovery.diagnostic or "").lower()


def test_kimi_capabilities_only_claim_verified_metrics():
    capabilities = KimiAdapter().capabilities()

    assert capabilities.sessions is True
    assert capabilities.tokens is True
    assert capabilities.cache is True
    assert capabilities.messages is False
    assert capabilities.tools is False
    assert capabilities.costs is False
    assert capabilities.user_identity is False
