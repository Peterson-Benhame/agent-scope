import shutil
from datetime import date
from pathlib import Path

from agentscope.analytics.filters import AnalyticsFilter
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
    combined = "\n".join(
        p.read_text(encoding="utf-8")
        for p in created
        if p.suffix in {".csv", ".json"}
    )
    assert "Read C:" not in combined
    assert "TOOL_OUTPUT_SECRET" not in combined


def test_full_content_export_is_explicit(tmp_path):
    repo, analytics = populated(tmp_path)
    out = tmp_path / "reports"
    created = export_datasets(repo, analytics, out, include_content=True)
    full = next(p for p in created if p.name == "messages_full.json")
    assert "Read C:" in full.read_text(encoding="utf-8")


def test_html_report_uses_v2_labels_pt_br_formatting_and_safe_metadata(tmp_path):
    repo, analytics = populated(tmp_path)
    target = tmp_path / "report.html"

    generate_html_report(repo, analytics, target)

    text = target.read_text(encoding="utf-8")
    for label in [
        "Resumo executivo",
        "Tokens",
        "Cache",
        "Custos",
        "Economia",
        "Modelos",
        "Projetos",
        "Agentes",
        "Habilidades",
        "Ferramentas / MCPs",
        "Otimizadores",
        "Tendências temporais",
        "Qualidade dos dados",
    ]:
        assert label in text

    assert "Todo o histórico" in text
    assert "Tokens economizados" in text
    assert "Taxa de cache" in text
    assert "Custo observado/reportado pela fonte" in text
    assert "Economia estimada" in text
    assert "US$ 0,08" in text
    assert "95,19%" in text
    assert "US$ 0,080000" not in text
    assert "Read C:" not in text
    assert "TOOL_OUTPUT_SECRET" not in text
    assert "gpt-5.6-terra" in text
    assert "Headroom" in text
    assert "Tokens por dia" in text
    assert "Economia por dia" in text


def test_html_report_exposes_data_quality_metrics(tmp_path):
    repo, analytics = populated(tmp_path)
    target = tmp_path / "quality-report.html"

    generate_html_report(repo, analytics, target)

    text = target.read_text(encoding="utf-8")
    assert "Erros de importação" in text
    assert "Sessões sem modelo identificado" in text
    assert "Participação de tokens sem modelo identificado" in text
    assert "Evidências de habilidades" in text
    assert "Evidências de agentes" in text
    assert "Confiança de correlação das otimizações" in text


def test_html_report_displays_selected_period(tmp_path):
    repo, _ = populated(tmp_path)
    filters = AnalyticsFilter(
        from_date=date(2026, 8, 18),
        to_date=date(2026, 8, 18),
    )
    analytics = AnalyticsService(repo, filters)
    target = tmp_path / "filtered-report.html"

    generate_html_report(repo, analytics, target, filters=filters)

    text = target.read_text(encoding="utf-8")
    assert "Período" in text
    assert "18/08/2026 a 18/08/2026" in text
    assert "1" in text
    assert "18.019" in text
