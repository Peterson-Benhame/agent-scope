import json

from typer.testing import CliRunner

from agentscope.cli import app
from agentscope.costs.calculator import CostCalculationSummary


runner = CliRunner()


def test_costs_calculate_cli_returns_machine_readable_summary(monkeypatch, tmp_path):
    db = tmp_path / "agentscope.db"
    monkeypatch.setattr(
        "agentscope.cli.calculate_token_usage_costs",
        lambda repository, utc_offset_minutes: CostCalculationSummary(
            events_scanned=3,
            events_priced=3,
            events_unpriced=0,
            complete=True,
            by_model={"gpt-5.6-sol": 1.25, "gpt-5.6-terra": 0.75},
            total_estimated_cost_usd=2.0,
            unpriced_reasons={},
        ),
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
