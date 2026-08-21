import json
from datetime import date

from typer.testing import CliRunner

from agentscope.cli import app
from agentscope.costs.calculator import CostCalculationSummary


runner = CliRunner()


def _summary():
    return CostCalculationSummary(
        events_scanned=3,
        events_priced=3,
        events_unpriced=0,
        complete=True,
        by_model={"gpt-5.6-sol": 1.25, "gpt-5.6-terra": 0.75},
        total_estimated_cost_usd=2.0,
        unpriced_reasons={},
    )


def test_costs_calculate_cli_returns_machine_readable_summary(monkeypatch, tmp_path):
    db = tmp_path / "agentscope.db"
    monkeypatch.setattr(
        "agentscope.cli.calculate_token_usage_costs",
        lambda repository, **kwargs: _summary(),
    )

    result = runner.invoke(
        app,
        ["costs", "calculate", "--database", str(db), "--json"],
    )

    assert result.exit_code == 0, result.output
    assert json.loads(result.output) == {
        "events_scanned": 3,
        "events_priced": 3,
        "events_unpriced": 0,
        "complete": True,
        "by_model": {"gpt-5.6-sol": 1.25, "gpt-5.6-terra": 0.75},
        "total_estimated_cost_usd": 2.0,
        "unpriced_reasons": {},
    }


def test_costs_calculate_cli_resolves_period_and_passes_local_dates(monkeypatch, tmp_path):
    db = tmp_path / "agentscope.db"
    captured = {}

    def calculate(repository, **kwargs):
        captured.update(kwargs)
        return _summary()

    monkeypatch.setattr("agentscope.cli.calculate_token_usage_costs", calculate)
    monkeypatch.setattr("agentscope.cli.date", type("FakeDate", (), {"today": staticmethod(lambda: date(2026, 8, 19))}))

    result = runner.invoke(
        app,
        ["costs", "calculate", "--database", str(db), "--period", "7d", "--json"],
    )

    assert result.exit_code == 0, result.output
    assert captured["from_date"] == date(2026, 8, 13)
    assert captured["to_date"] == date(2026, 8, 19)


def test_costs_calculate_cli_accepts_explicit_range(monkeypatch, tmp_path):
    db = tmp_path / "agentscope.db"
    captured = {}

    def calculate(repository, **kwargs):
        captured.update(kwargs)
        return _summary()

    monkeypatch.setattr("agentscope.cli.calculate_token_usage_costs", calculate)
    result = runner.invoke(
        app,
        [
            "costs",
            "calculate",
            "--database",
            str(db),
            "--from",
            "2026-08-13",
            "--to",
            "2026-08-19",
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    assert captured["from_date"] == date(2026, 8, 13)
    assert captured["to_date"] == date(2026, 8, 19)
