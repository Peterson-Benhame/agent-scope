import json
import shutil
import sqlite3
from pathlib import Path

from typer.testing import CliRunner

from agentscope.cli import app


runner = CliRunner()
FIXTURE = Path("tests/fixtures/codex/rollout.jsonl")


def test_report_accepts_user_and_machine_filters(tmp_path):
    codex_home = tmp_path / ".codex"
    session_dir = codex_home / "sessions" / "2026" / "08" / "18"
    session_dir.mkdir(parents=True)
    shutil.copy(FIXTURE, session_dir / "rollout.jsonl")
    db = tmp_path / "agentscope.db"
    report_path = tmp_path / "report.html"
    env = {
        "AGENTSCOPE_SOURCES": "codex",
        "AGENTSCOPE_USER_NAME": "Dev A",
        "AGENTSCOPE_MACHINE_NAME": "Notebook A",
    }

    collected = runner.invoke(
        app,
        [
            "collect",
            "--codex-home",
            str(codex_home),
            "--database",
            str(db),
        ],
        env=env,
    )
    assert collected.exit_code == 0, collected.output

    report = runner.invoke(
        app,
        [
            "report",
            "--database",
            str(db),
            "--output",
            str(report_path),
            "--user",
            "Dev A",
            "--machine",
            "Notebook A",
        ],
        env=env,
    )

    assert report.exit_code == 0, report.output
    text = report_path.read_text(encoding="utf-8")
    assert "Dev A" in text
    assert "Notebook A" in text


def test_missing_user_filter_returns_empty_summary(tmp_path):
    codex_home = tmp_path / ".codex"
    session_dir = codex_home / "sessions" / "2026" / "08" / "18"
    session_dir.mkdir(parents=True)
    shutil.copy(FIXTURE, session_dir / "rollout.jsonl")
    db = tmp_path / "agentscope.db"
    env = {
        "AGENTSCOPE_SOURCES": "codex",
        "AGENTSCOPE_USER_NAME": "Dev A",
    }

    collected = runner.invoke(
        app,
        ["collect", "--codex-home", str(codex_home), "--database", str(db)],
        env=env,
    )
    assert collected.exit_code == 0, collected.output

    analyze = runner.invoke(
        app,
        ["analyze", "--database", str(db), "--user", "Missing"],
        env=env,
    )

    assert analyze.exit_code == 0, analyze.output
    assert '"input_tokens": 0' in analyze.output


def test_identity_backfill_cli_repairs_historical_session(tmp_path):
    codex_home = tmp_path / ".codex"
    session_dir = codex_home / "sessions" / "2026" / "08" / "18"
    session_dir.mkdir(parents=True)
    shutil.copy(FIXTURE, session_dir / "rollout.jsonl")
    db = tmp_path / "agentscope.db"
    env = {
        "AGENTSCOPE_SOURCES": "codex",
        "AGENTSCOPE_CODEX_HOME": str(codex_home),
    }

    collected = runner.invoke(
        app,
        ["collect", "--codex-home", str(codex_home), "--database", str(db)],
        env=env,
    )
    assert collected.exit_code == 0, collected.output

    with sqlite3.connect(db) as conn:
        conn.execute("UPDATE sessions SET user_id=NULL, machine_id=NULL")

    backfilled = runner.invoke(
        app,
        [
            "identity",
            "backfill",
            "--database",
            str(db),
            "--source",
            "codex",
            "--user-name",
            "Dev A",
            "--machine-name",
            "Notebook A",
        ],
        env=env,
    )

    assert backfilled.exit_code == 0, backfilled.output
    assert "sessions_scanned=1" in backfilled.output
    assert "sessions_updated=1" in backfilled.output
    assert "sessions_without_user=0" in backfilled.output
    assert "sessions_without_machine=0" in backfilled.output

    analyze = runner.invoke(
        app,
        [
            "analyze",
            "--database",
            str(db),
            "--user",
            "Dev A",
            "--machine",
            "Notebook A",
        ],
        env=env,
    )
    assert analyze.exit_code == 0, analyze.output
    payload = json.loads(analyze.output)
    assert payload["sessions"] == 1
    assert payload["total_tokens"] > 0
