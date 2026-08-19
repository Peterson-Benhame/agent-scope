import shutil
from pathlib import Path

from agentscope.analytics.service import AnalyticsService
from agentscope.importer import collect_sources
from agentscope.storage.database import Database
from agentscope.storage.repository import Repository


CODEX_FIXTURE = Path("tests/fixtures/codex/rollout.jsonl")
HEADROOM_FIXTURE = Path("tests/fixtures/headroom")


def populated(tmp_path):
    codex_home = tmp_path / ".codex"
    session_dir = codex_home / "sessions" / "2026" / "08" / "18"
    session_dir.mkdir(parents=True)
    shutil.copy(CODEX_FIXTURE, session_dir / "rollout.jsonl")
    headroom_home = tmp_path / ".headroom"
    shutil.copytree(HEADROOM_FIXTURE, headroom_home)
    db = Database(tmp_path / "agentscope.db")
    db.initialize()
    repo = Repository(db)
    collect_sources(repo, codex_home=codex_home, headroom_home=headroom_home)
    return db, repo, AnalyticsService(repo)


def test_summary_combines_usage_cache_and_optimizer_savings(tmp_path):
    _, _, analytics = populated(tmp_path)
    summary = analytics.summary()
    assert summary.sessions == 1
    assert summary.messages == 3
    assert summary.tool_calls == 2
    assert summary.input_tokens == 18019
    assert summary.cached_input_tokens == 17152
    assert summary.output_tokens == 223
    assert summary.reasoning_output_tokens == 39
    assert round(summary.cache_ratio, 4) == round(17152 / 18019, 4)
    assert summary.tokens_saved == 1500
    assert round(summary.compression_savings_usd, 6) == 0.003
    assert round(summary.cache_savings_usd, 6) == 0.02
    assert round(summary.total_savings_usd, 6) == 0.023
    assert round(summary.observed_cost_usd or 0, 6) == 0.08
    assert summary.estimated_raw_cost_usd is None


def test_groups_usage_by_project_and_model(tmp_path):
    _, _, analytics = populated(tmp_path)
    projects = analytics.by_project()
    models = analytics.by_model()
    assert projects[0]["project"] == "demo"
    assert projects[0]["sessions"] == 1
    assert projects[0]["input_tokens"] == 18019
    terra = next(x for x in models if x["model"] == "gpt-5.6-terra")
    assert terra["input_tokens"] == 18019


def test_agent_skill_and_tool_analytics_preserve_distinctions(tmp_path):
    _, _, analytics = populated(tmp_path)
    agents = {x["agent"]: x for x in analytics.by_agent()}
    assert agents["root"]["sessions"] == 1
    assert agents["reviewer"]["sessions"] == 1
    assert "headroom" not in agents
    skills = {(x["skill"], x["usage_type"]): x["sessions"] for x in analytics.by_skill()}
    assert skills[("superpowers:brainstorming", "available")] == 1
    assert skills[("superpowers:brainstorming", "loaded")] == 1
    assert skills[("superpowers:brainstorming", "invoked")] == 1
    tools = {x["tool"]: x for x in analytics.by_tool()}
    assert tools["exec"]["calls"] == 1
    assert tools["spawn_agent"]["calls"] == 1


def test_unknown_cost_remains_null(tmp_path):
    db = Database(tmp_path / "agentscope.db")
    db.initialize()
    repo = Repository(db)
    analytics = AnalyticsService(repo)
    summary = analytics.summary()
    assert summary.observed_cost_usd is None
    assert summary.estimated_raw_cost_usd is None


def test_headroom_lifetime_cost_snapshot_is_replaced_not_accumulated(tmp_path):
    codex_home = tmp_path / ".codex"
    sdir = codex_home / "sessions" / "2026" / "08" / "18"
    sdir.mkdir(parents=True)
    shutil.copy(CODEX_FIXTURE, sdir / "rollout.jsonl")
    headroom_home = tmp_path / ".headroom"
    shutil.copytree(HEADROOM_FIXTURE, headroom_home)
    db = Database(tmp_path / "agentscope.db")
    db.initialize()
    repo = Repository(db)
    collect_sources(repo, codex_home=codex_home, headroom_home=headroom_home)
    payload_path = headroom_home / "proxy_savings.json"
    payload = __import__("json").loads(payload_path.read_text(encoding="utf-8"))
    payload["lifetime"]["total_input_cost_usd"] = 0.10
    payload["lifetime"]["compression_savings_usd"] = 0.004
    payload["lifetime"]["cache_savings_usd"] = 0.03
    payload_path.write_text(__import__("json").dumps(payload), encoding="utf-8")
    collect_sources(repo, codex_home=codex_home, headroom_home=headroom_home)
    summary = AnalyticsService(repo).summary()
    assert round(summary.observed_cost_usd or 0, 6) == 0.10
    assert round(summary.compression_savings_usd, 6) == 0.004
    assert round(summary.cache_savings_usd, 6) == 0.03
    assert round(summary.total_savings_usd, 6) == 0.034
    with db.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM costs WHERE pricing_source='headroom:lifetime'").fetchone()[0] == 1
