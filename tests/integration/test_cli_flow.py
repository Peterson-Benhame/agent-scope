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


def collect_fixture_data(tmp_path):
    codex_home, headroom_home = arrange_sources(tmp_path)
    db = tmp_path / "agentscope.db"
    result = runner.invoke(
        app,
        [
            "collect",
            "--codex-home",
            str(codex_home),
            "--headroom-home",
            str(headroom_home),
            "--database",
            str(db),
        ],
    )
    assert result.exit_code == 0, result.output
    return db, codex_home, headroom_home, result


def test_cli_collect_status_analyze_export_and_report(tmp_path):
    db, codex_home, headroom_home, collect = collect_fixture_data(tmp_path)
    reports = tmp_path / "reports"

    assert "Coletando" in collect.output
    assert "100%" in collect.output
    assert "sessions_imported=1" in collect.output

    status = runner.invoke(
        app,
        [
            "status",
            "--database",
            str(db),
            "--codex-home",
            str(codex_home),
            "--headroom-home",
            str(headroom_home),
        ],
    )
    assert status.exit_code == 0
    assert "sessions=1" in status.output

    analyze = runner.invoke(app, ["analyze", "--database", str(db)])
    assert analyze.exit_code == 0
    assert '"input_tokens": 18019' in analyze.output

    export = runner.invoke(
        app,
        ["export", "--database", str(db), "--output-dir", str(reports)],
    )
    assert export.exit_code == 0
    assert (reports / "sessions.csv").exists()

    report = runner.invoke(
        app,
        [
            "report",
            "--database",
            str(db),
            "--output",
            str(reports / "report.html"),
        ],
    )
    assert report.exit_code == 0
    assert (reports / "report.html").exists()


def test_report_accepts_inclusive_from_and_to_dates(tmp_path):
    db, _, _, _ = collect_fixture_data(tmp_path)
    report_path = tmp_path / "filtered-report.html"

    result = runner.invoke(
        app,
        [
            "report",
            "--database",
            str(db),
            "--output",
            str(report_path),
            "--from",
            "2026-08-18",
            "--to",
            "2026-08-18",
        ],
    )

    assert result.exit_code == 0, result.output
    text = report_path.read_text(encoding="utf-8")
    assert "18/08/2026 a 18/08/2026" in text
    assert "18.019" in text


def test_analyze_accepts_period_alias(tmp_path):
    db, _, _, _ = collect_fixture_data(tmp_path)

    result = runner.invoke(
        app,
        ["analyze", "--database", str(db), "--period", "30d"],
    )

    assert result.exit_code == 0, result.output
    assert '"input_tokens": 18019' in result.output


def test_export_filters_raw_datasets_by_project(tmp_path):
    db, _, _, _ = collect_fixture_data(tmp_path)
    reports = tmp_path / "filtered-export"

    result = runner.invoke(
        app,
        [
            "export",
            "--database",
            str(db),
            "--output-dir",
            str(reports),
            "--project",
            "missing-project",
        ],
    )

    assert result.exit_code == 0, result.output
    assert (reports / "sessions.csv").read_text(encoding="utf-8") == ""
    assert (reports / "token_usage.csv").read_text(encoding="utf-8") == ""


def test_invalid_period_returns_clear_cli_error(tmp_path):
    db, _, _, _ = collect_fixture_data(tmp_path)

    result = runner.invoke(
        app,
        ["analyze", "--database", str(db), "--period", "90d"],
    )

    assert result.exit_code != 0
    assert "90d" in result.output


def test_invalid_date_returns_clear_cli_error(tmp_path):
    db, _, _, _ = collect_fixture_data(tmp_path)

    result = runner.invoke(
        app,
        ["report", "--database", str(db), "--from", "18/08/2026"],
    )

    assert result.exit_code != 0
    assert "YYYY-MM-DD" in result.output
