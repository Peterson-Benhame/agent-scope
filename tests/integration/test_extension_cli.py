import json

import pytest
from typer.testing import CliRunner

from agentscope.cli import app
from tests.integration.test_cli_flow import FIXTURE_ENV, collect_fixture_data


runner = CliRunner()


def invoke_snapshot(db, *args):
    return runner.invoke(
        app,
        ["extension", "snapshot", "--database", str(db), "--json", *args],
        env=FIXTURE_ENV,
    )


def test_extension_snapshot_cli_returns_machine_readable_json(tmp_path):
    db, _, _, _ = collect_fixture_data(tmp_path)

    result = invoke_snapshot(db, "--period", "30d")

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["schema"] == "agentscope-extension-snapshot"
    assert payload["version"] == 2
    assert payload["summary"]["sessions"] == 1
    assert "estimated_cost_usd" in payload["summary"]
    assert set(payload["availability"]) == {
        "observed_cost",
        "estimated_cost",
        "estimated_savings",
    }
    assert isinstance(payload["series"]["daily"], list)
    assert isinstance(payload["breakdowns"]["projects"], list)
    assert isinstance(payload["breakdowns"]["models"], list)
    assert isinstance(payload["breakdowns"]["sources"], list)
    assert isinstance(payload["dimensions"]["projects"], list)
    assert isinstance(payload["dimensions"]["models"], list)
    assert isinstance(payload["dimensions"]["sources"], list)
    assert isinstance(payload["dimensions"]["users"], list)
    assert isinstance(payload["dimensions"]["machines"], list)


def test_extension_snapshot_cli_applies_custom_date_range(tmp_path):
    db, _, _, _ = collect_fixture_data(tmp_path)

    inside = invoke_snapshot(db, "--from", "2026-08-18", "--to", "2026-08-18")
    outside = invoke_snapshot(db, "--from", "2026-08-17", "--to", "2026-08-17")

    assert inside.exit_code == 0, inside.output
    assert json.loads(inside.output)["summary"]["sessions"] == 1
    assert outside.exit_code == 0, outside.output
    outside_payload = json.loads(outside.output)
    assert outside_payload["summary"]["sessions"] == 0
    assert outside_payload["series"]["daily"] == []
    assert outside_payload["breakdowns"]["projects"] == []
    assert outside_payload["breakdowns"]["models"] == []
    assert outside_payload["breakdowns"]["sources"] == []


@pytest.mark.parametrize(
    ("flag", "value"),
    [
        ("--project", "missing-project"),
        ("--model", "missing-model"),
        ("--source", "missing-source"),
        ("--user", "missing-user"),
        ("--machine", "missing-machine"),
    ],
)
def test_extension_snapshot_cli_applies_dimension_filters(tmp_path, flag, value):
    db, _, _, _ = collect_fixture_data(tmp_path)

    result = invoke_snapshot(db, flag, value)

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["summary"]["sessions"] == 0
    assert payload["series"]["daily"] == []


def test_extension_snapshot_cli_rejects_missing_database(tmp_path):
    missing = tmp_path / "missing.db"

    result = runner.invoke(
        app,
        ["extension", "snapshot", "--database", str(missing), "--json"],
        env=FIXTURE_ENV,
    )

    assert result.exit_code != 0
    assert "database not found:" in result.output
