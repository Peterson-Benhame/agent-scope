import json
from datetime import datetime, timezone

from typer.testing import CliRunner

from agentscope.cli import app
from agentscope.pricing.refresh import PricingRefreshResult


runner = CliRunner()


def test_pricing_refresh_cli_returns_machine_readable_summary(monkeypatch, tmp_path):
    db = tmp_path / "agentscope.db"

    monkeypatch.setattr(
        "agentscope.cli.refresh_openai_pricing",
        lambda repository, force=False: PricingRefreshResult(
            status="updated",
            models_checked=3,
            records_inserted=6,
            used_last_known_good=False,
            last_success_at="2026-08-19T21:00:00+00:00",
            error=None,
        ),
    )

    result = runner.invoke(
        app,
        ["pricing", "refresh", "--database", str(db), "--json", "--force"],
    )

    assert result.exit_code == 0, result.output
    assert json.loads(result.output) == {
        "status": "updated",
        "models_checked": 3,
        "records_inserted": 6,
        "used_last_known_good": False,
        "last_success_at": "2026-08-19T21:00:00+00:00",
        "error": None,
    }


def test_collect_keeps_token_collection_successful_when_pricing_refresh_fails(monkeypatch, tmp_path):
    codex_home = tmp_path / ".codex"
    (codex_home / "sessions").mkdir(parents=True)
    db = tmp_path / "agentscope.db"

    monkeypatch.setattr(
        "agentscope.cli.refresh_openai_pricing",
        lambda repository, force=False: PricingRefreshResult(
            status="failed",
            models_checked=0,
            records_inserted=0,
            used_last_known_good=True,
            last_success_at="2026-08-18T10:00:00+00:00",
            error="offline",
        ),
    )

    result = runner.invoke(
        app,
        ["collect", "--codex-home", str(codex_home), "--database", str(db)],
        env={"AGENTSCOPE_SOURCES": "codex"},
    )

    assert result.exit_code == 0, result.output
    assert "pricing_status=failed" in result.output
    assert "pricing_fallback=last_known_good" in result.output
    assert "pricing_error=offline" in result.output
