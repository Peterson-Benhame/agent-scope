import shutil
from pathlib import Path

from agentscope.analytics.service import AnalyticsService
from agentscope.importer import collect_sources
from agentscope.reporting.export import export_datasets
from agentscope.reporting.html_report import generate_html_report
from agentscope.storage.database import Database
from agentscope.storage.repository import Repository


CODEX_FIXTURE = Path("tests/fixtures/codex/rollout.jsonl")
HEADROOM_FIXTURE = Path("tests/fixtures/headroom")


def populated(tmp_path):
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
    return repo, AnalyticsService(repo)


def test_safe_exports_create_required_csv_and_json_without_message_content(tmp_path):
    repo, analytics = populated(tmp_path)
    out = tmp_path / "reports"
    created = export_datasets(repo, analytics, out, include_content=False)
    required = {
        "sessions.csv", "token_usage.csv", "costs.csv", "agents.csv", "skills.csv",
        "tool_calls.csv", "optimizations.csv", "usage_by_project.csv",
        "usage_by_model.csv", "usage_by_day.csv", "datasets.json",
    }
    assert required.issubset({p.name for p in created})
    combined = "\n".join(p.read_text(encoding="utf-8") for p in created if p.suffix in {".csv", ".json"})
    assert "Read C:" not in combined
    assert "TOOL_OUTPUT_SECRET" not in combined


def test_full_content_export_is_explicit(tmp_path):
    repo, analytics = populated(tmp_path)
    out = tmp_path / "reports"
    created = export_datasets(repo, analytics, out, include_content=True)
    full = next(p for p in created if p.name == "messages_full.json")
    assert "Read C:" in full.read_text(encoding="utf-8")


def test_html_report_contains_analysis_sections_and_no_prompt_text(tmp_path):
    repo, analytics = populated(tmp_path)
    target = tmp_path / "report.html"
    generate_html_report(repo, analytics, target)
    text = target.read_text(encoding="utf-8")
    for label in [
        "Executive Summary", "Tokens", "Cache", "Costs", "Savings", "Models",
        "Projects", "Agents", "Skills", "Tools / MCPs", "Optimizers",
        "Temporal Trends", "Data Quality"
    ]:
        assert label in text
    assert "Read C:" not in text
    assert "gpt-5.6-terra" in text
    assert "Headroom" in text
    assert "Tokens by day" in text
    assert "Savings by day" in text
