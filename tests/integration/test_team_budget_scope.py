from typer.testing import CliRunner

from agentscope.cli import app
from agentscope.storage.database import Database


runner = CliRunner()


def team_database(path):
    db = Database(path)
    db.initialize()
    with db.connect() as conn:
        conn.execute("INSERT INTO sources(name, type) VALUES('codex', 'team-import')")
        source_id = conn.execute("SELECT id FROM sources WHERE name='codex'").fetchone()[0]
        conn.execute(
            "INSERT INTO users(stable_key, display_name, identity_confidence) VALUES('u1', 'Dev A', 'inferred')"
        )
        user_id = conn.execute("SELECT id FROM users WHERE stable_key='u1'").fetchone()[0]
        conn.execute("INSERT INTO machines(stable_key, display_name) VALUES('m1', 'Notebook A')")
        machine_id = conn.execute("SELECT id FROM machines WHERE stable_key='m1'").fetchone()[0]
        for session, timestamp, cost in (
            ('s1', '2026-08-01T09:00:00Z', 10.0),
            ('s2', '2026-08-18T09:00:00Z', 20.0),
        ):
            conn.execute(
                """
                INSERT INTO sessions(
                    source_id, external_session_id, started_at, user_id, machine_id
                ) VALUES(?, ?, ?, ?, ?)
                """,
                (source_id, session, timestamp, user_id, machine_id),
            )
            session_id = conn.execute(
                "SELECT id FROM sessions WHERE external_session_id=?",
                (session,),
            ).fetchone()[0]
            conn.execute(
                """
                INSERT INTO costs(
                    session_id, period_start, observed_cost_usd, event_key
                ) VALUES(?, ?, ?, ?)
                """,
                (session_id, timestamp, cost, f'cost-{session}'),
            )
    return db


def test_team_budget_uses_month_to_date_spend_not_report_date_slice(tmp_path):
    db_path = tmp_path / "team.db"
    output = tmp_path / "report.html"
    team_database(db_path)

    result = runner.invoke(
        app,
        [
            "team", "report",
            "--database", str(db_path),
            "--output", str(output),
            "--from", "2026-08-18",
            "--to", "2026-08-18",
            "--monthly-budget-usd", "100",
        ],
    )

    assert result.exit_code == 0, result.output
    html = output.read_text(encoding="utf-8")
    assert "Custos — observado</span><strong>US$ 20,00" in html
    assert "Gasto observado</span><strong>US$ 30,00" in html
    assert "Consumo</span><strong>30,00%" in html
    assert "Projeção até o fim do mês</span><strong>US$ 51,67" in html
