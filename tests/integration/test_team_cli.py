import json

from typer.testing import CliRunner

from agentscope.cli import app
from agentscope.storage.database import Database


runner = CliRunner()


def populate_source(path):
    db = Database(path)
    db.initialize()
    with db.connect() as conn:
        conn.execute("INSERT INTO sources(name, type) VALUES('codex', 'agent')")
        source_id = conn.execute("SELECT id FROM sources WHERE name='codex'").fetchone()[0]
        conn.execute("INSERT INTO projects(name, path) VALUES('demo', 'C:\\source\\demo')")
        project_id = conn.execute("SELECT id FROM projects WHERE name='demo'").fetchone()[0]
        conn.execute("INSERT INTO users(stable_key, display_name, identity_confidence) VALUES('user-a', 'Dev A', 'inferred')")
        user_id = conn.execute("SELECT id FROM users WHERE stable_key='user-a'").fetchone()[0]
        conn.execute("INSERT INTO machines(stable_key, display_name, os) VALUES('machine-a', 'Notebook A', 'Windows')")
        machine_id = conn.execute("SELECT id FROM machines WHERE stable_key='machine-a'").fetchone()[0]
        conn.execute(
            """
            INSERT INTO sessions(source_id, external_session_id, project_id, started_at, user_id, machine_id)
            VALUES(?, 'session-a', ?, '2026-08-18T10:00:00Z', ?, ?)
            """,
            (source_id, project_id, user_id, machine_id),
        )
        session_id = conn.execute("SELECT id FROM sessions").fetchone()[0]
        conn.execute(
            """
            INSERT INTO messages(session_id, role, timestamp, content, event_key)
            VALUES(?, 'user', '2026-08-18T10:00:01Z', 'TEAM_CLI_PROMPT_SECRET', 'msg-a')
            """,
            (session_id,),
        )
        conn.execute(
            """
            INSERT INTO token_usage(session_id, timestamp, input_tokens, output_tokens, total_tokens, event_key)
            VALUES(?, '2026-08-18T10:00:02Z', 1000, 200, 1200, 'token-a')
            """,
            (session_id,),
        )
    return db


def test_team_export_import_and_reimport_cli(tmp_path):
    source_db = tmp_path / "source.db"
    target_db = tmp_path / "team.db"
    bundle_path = tmp_path / "team-bundle.json"
    populate_source(source_db)

    export = runner.invoke(
        app,
        [
            "team", "export",
            "--database", str(source_db),
            "--output", str(bundle_path),
            "--organization", "Org",
            "--team", "Backend",
        ],
    )
    assert export.exit_code == 0, export.output
    assert bundle_path.exists()
    serialized = bundle_path.read_text(encoding="utf-8")
    assert "TEAM_CLI_PROMPT_SECRET" not in serialized

    first_import = runner.invoke(
        app,
        ["team", "import", str(bundle_path), "--database", str(target_db)],
    )
    second_import = runner.invoke(
        app,
        ["team", "import", str(bundle_path), "--database", str(target_db)],
    )

    assert first_import.exit_code == 0, first_import.output
    assert "events_imported=1" in first_import.output
    assert second_import.exit_code == 0, second_import.output
    assert "events_imported=0" in second_import.output
    assert "events_skipped=1" in second_import.output
    with Database(target_db).connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM token_usage").fetchone()[0] == 1


def test_invalid_team_bundle_does_not_change_existing_team_data(tmp_path):
    source_db = tmp_path / "source.db"
    target_db = tmp_path / "team.db"
    valid_path = tmp_path / "valid.json"
    invalid_path = tmp_path / "invalid.json"
    populate_source(source_db)

    export = runner.invoke(
        app,
        ["team", "export", "--database", str(source_db), "--output", str(valid_path)],
    )
    assert export.exit_code == 0, export.output
    imported = runner.invoke(
        app,
        ["team", "import", str(valid_path), "--database", str(target_db)],
    )
    assert imported.exit_code == 0, imported.output

    invalid = json.loads(valid_path.read_text(encoding="utf-8"))
    invalid["records"]["sessions"][0]["content"] = "FORBIDDEN"
    invalid_path.write_text(json.dumps(invalid), encoding="utf-8")

    before_db = Database(target_db)
    with before_db.connect() as conn:
        before_sessions = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
        before_bundles = conn.execute("SELECT COUNT(*) FROM team_bundles").fetchone()[0]

    result = runner.invoke(
        app,
        ["team", "import", str(invalid_path), "--database", str(target_db)],
    )

    assert result.exit_code != 0
    with before_db.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0] == before_sessions
        assert conn.execute("SELECT COUNT(*) FROM team_bundles").fetchone()[0] == before_bundles
