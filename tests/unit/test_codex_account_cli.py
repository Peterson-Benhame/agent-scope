from __future__ import annotations

import json

from typer.testing import CliRunner

from agentscope.cli import app
from agentscope.codex_account.models import CodexAccountSnapshot
from agentscope.codex_account.storage import CodexAccountStorage
from agentscope.storage.database import Database


runner = CliRunner()


def test_codex_account_status_empty_database_is_unavailable(tmp_path):
    database = tmp_path / "agentscope.db"
    result = runner.invoke(
        app,
        ["codex-account", "status", "--database", str(database), "--json"],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload == {"available": False, "reason": "no_account_snapshot"}


def test_codex_account_status_reads_only_stored_snapshot(tmp_path):
    database = tmp_path / "agentscope.db"
    db = Database(database)
    db.initialize()
    CodexAccountStorage(db).insert_account_snapshot(
        CodexAccountSnapshot(
            captured_at="2026-08-20T16:00:00+00:00",
            auth_mode="chatgpt",
            plan_type="pro",
            primary_used_percent=63,
            credits_has_credits=True,
            credits_balance="18.42",
            credits_unlimited=False,
        )
    )

    result = runner.invoke(
        app,
        ["codex-account", "status", "--database", str(database), "--json"],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["available"] is True
    assert payload["plan_type"] == "pro"
    assert payload["primary_used_percent"] == 63
    assert payload["credits_balance"] == "18.42"
    assert "email" not in payload
