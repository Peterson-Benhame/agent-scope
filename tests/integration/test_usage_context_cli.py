import json
import shutil
from pathlib import Path

from typer.testing import CliRunner

from agentscope.cli import app


runner = CliRunner()
FIXTURE = Path("tests/fixtures/codex/rollout.jsonl")


def test_usage_context_backfill_cli_reports_historical_classification(tmp_path):
    codex_home = tmp_path / ".codex"
    session_dir = codex_home / "sessions" / "2026" / "08" / "18"
    session_dir.mkdir(parents=True)
    shutil.copy(FIXTURE, session_dir / "rollout.jsonl")
    db = tmp_path / "agentscope.db"
    env = {"AGENTSCOPE_SOURCES": "codex"}

    collected = runner.invoke(
        app,
        ["collect", "--codex-home", str(codex_home), "--database", str(db)],
        env=env,
    )
    assert collected.exit_code == 0, collected.output

    with __import__("sqlite3").connect(db) as conn:
        conn.execute("DELETE FROM session_usage_context")

    result = runner.invoke(
        app,
        [
            "usage-context",
            "backfill",
            "--database",
            str(db),
            "--source",
            "codex",
            "--json",
        ],
        env=env,
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["sessions_scanned"] == 1
    assert payload["sessions_updated"] == 1
    assert payload["sessions_existing"] == 0
    assert payload["clients"] == {"vscode": 1}
    assert payload["billing_modes"] == {"unknown": 1}
    assert payload["errors"] == 0
