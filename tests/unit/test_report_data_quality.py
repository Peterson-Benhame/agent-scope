import shutil
from pathlib import Path

from agentscope.analytics.service import AnalyticsService
from agentscope.importer import collect_sources
from agentscope.reporting.html_report import generate_html_report
from agentscope.storage.database import Database
from agentscope.storage.repository import Repository


CODEX_FIXTURE = Path("tests/fixtures/codex/rollout.jsonl")
HEADROOM_FIXTURE = Path("tests/fixtures/headroom")


def test_report_surfaces_explicit_data_quality_metrics(tmp_path):
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

    target = tmp_path / "report.html"
    generate_html_report(repo, AnalyticsService(repo), target)
    text = target.read_text(encoding="utf-8")

    assert "Qualidade dos dados" in text
    assert "Modelos desconhecidos" in text
    assert "Participação de tokens sem modelo" in text
    assert "Evidências de habilidades" in text
    assert "Evidências de agentes" in text
    assert "Confiança de correlação das otimizações" in text
