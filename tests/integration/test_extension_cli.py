import json

from typer.testing import CliRunner

from agentscope.cli import app
from tests.integration.test_cli_flow import FIXTURE_ENV, collect_fixture_data


runner = CliRunner()


def test_extension_snapshot_cli_returns_machine_readable_json(tmp_path):
    db, _, _, _ = collect_fixture_data(tmp_path)

    result = runner.invoke(
        app,
        [
            "extension",
            "snapshot",
            "--database",
            str(db),
            "--period",
            "30d",
            "--json",
        ],
        env=FIXTURE_ENV,
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["schema"] == "agentscope-extension-snapshot"
    assert payload["version"] == 1
    assert payload["summary"]["sessions"] == 1
    assert isinstance(payload["dimensions"]["projects"], list)


def test_extension_snapshot_cli_applies_project_filter(tmp_path):
    db, _, _, _ = collect_fixture_data(tmp_path)

    result = runner.invoke(
        app,
        [
            "extension",
            "snapshot",
            "--database",
            str(db),
            "--project",
            "missing-project",
            "--json",
        ],
        env=FIXTURE_ENV,
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["summary"]["sessions"] == 0


def test_extension_snapshot_cli_rejects_missing_database(tmp_path):
    missing = tmp_path / "missing.db"

    result = runner.invoke(
        app,
        ["extension", "snapshot", "--database", str(missing), "--json"],
        env=FIXTURE_ENV,
    )

    assert result.exit_code != 0
    assert "database not found:" in result.output
