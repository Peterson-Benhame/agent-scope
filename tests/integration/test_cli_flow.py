import shutil
from pathlib import Path

from typer.testing import CliRunner

from agentscope.cli import app


runner = CliRunner()
CODEX_FIXTURE = Path("tests/fixtures/codex/rollout.jsonl")
HEADROOM_FIXTURE = Path("tests/fixtures/headroom")


def arrange_sources(tmp_path):
    codex_home = tmp_path / ".codex"
    sdir = codex_home / "sessions" / "2026" / "08" / "18"
    sdir.mkdir(parents=True)
    shutil.copy(CODEX_FIXTURE, sdir / "rollout.jsonl")
    headroom_home = tmp_path / ".headroom"
    shutil.copytree(HEADROOM_FIXTURE, headroom_home)
    return codex_home, headroom_home


def test_cli_collect_status_analyze_export_and_report(tmp_path):
    codex_home, headroom_home = arrange_sources(tmp_path)
    db = tmp_path / "agentscope.db"
    reports = tmp_path / "reports"
    collect = runner.invoke(app, [
        "collect", "--codex-home", str(codex_home), "--headroom-home", str(headroom_home),
        "--database", str(db),
    ])
    assert collect.exit_code == 0, collect.output
    assert "sessions_imported=1" in collect.output
    status = runner.invoke(app, ["status", "--database", str(db), "--codex-home", str(codex_home), "--headroom-home", str(headroom_home)])
    assert status.exit_code == 0
    assert "sessions=1" in status.output
    analyze = runner.invoke(app, ["analyze", "--database", str(db)])
    assert analyze.exit_code == 0
    assert '"input_tokens": 18019' in analyze.output
    export = runner.invoke(app, ["export", "--database", str(db), "--output-dir", str(reports)])
    assert export.exit_code == 0
    assert (reports / "sessions.csv").exists()
    report = runner.invoke(app, ["report", "--database", str(db), "--output", str(reports / "report.html")])
    assert report.exit_code == 0
    assert (reports / "report.html").exists()
