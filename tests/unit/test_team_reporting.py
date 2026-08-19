from datetime import date

from agentscope.analytics.budget import calculate_budget_status
from agentscope.analytics.team_service import TeamAnalyticsService
from agentscope.reporting.team_html_report import generate_team_html_report
from agentscope.storage.database import Database
from agentscope.storage.repository import Repository


def team_repo(tmp_path):
    db = Database(tmp_path / "team-report.db")
    db.initialize()
    with db.connect() as conn:
        conn.execute("INSERT INTO sources(name, type) VALUES('codex', 'agent')")
        source_id = conn.execute("SELECT id FROM sources WHERE name='codex'").fetchone()[0]
        conn.execute("INSERT INTO projects(name, path) VALUES('Projeto A', 'Projeto A')")
        project_id = conn.execute("SELECT id FROM projects WHERE name='Projeto A'").fetchone()[0]
        conn.execute("INSERT INTO models(provider, name) VALUES('codex', 'gpt-team')")
        model_id = conn.execute("SELECT id FROM models WHERE name='gpt-team'").fetchone()[0]
        conn.execute(
            "INSERT INTO users(stable_key, display_name, identity_confidence) VALUES('u-a', 'Dev A', 'inferred')"
        )
        user_id = conn.execute("SELECT id FROM users WHERE stable_key='u-a'").fetchone()[0]
        conn.execute(
            "INSERT INTO machines(stable_key, display_name, os) VALUES('m-a', 'Notebook A', 'Windows')"
        )
        machine_id = conn.execute("SELECT id FROM machines WHERE stable_key='m-a'").fetchone()[0]
        conn.execute(
            """
            INSERT INTO sessions(
                source_id, external_session_id, project_id, started_at,
                provider, model_id, user_id, machine_id
            ) VALUES(?, 'team-report-session', ?, '2026-08-18T10:00:00Z',
                     'codex', ?, ?, ?)
            """,
            (source_id, project_id, model_id, user_id, machine_id),
        )
        session_id = conn.execute("SELECT id FROM sessions").fetchone()[0]
        conn.execute(
            """
            INSERT INTO token_usage(
                session_id, timestamp, model_id, input_tokens,
                cached_input_tokens, output_tokens, total_tokens, event_key
            ) VALUES(?, '2026-08-18T10:00:01Z', ?, 1000, 750, 250, 1250, 'tr-token')
            """,
            (session_id, model_id),
        )
        conn.execute(
            """
            INSERT INTO costs(
                session_id, model_id, period_start, observed_cost_usd,
                estimated_raw_cost_usd, total_savings_usd, event_key
            ) VALUES(?, ?, '2026-08-18T10:00:00Z', 12.345, 18.5, 4.2, 'tr-cost')
            """,
            (session_id, model_id),
        )
    return Repository(db)


def test_team_report_contains_required_sections_and_pt_br_formatting(tmp_path):
    repo = team_repo(tmp_path)
    analytics = TeamAnalyticsService(repo)
    output = tmp_path / "team-report.html"

    generate_team_html_report(repo, analytics, output)

    html = output.read_text(encoding="utf-8")
    for label in (
        "Resumo da equipe",
        "Desenvolvedores",
        "Máquinas",
        "Tokens",
        "Cache",
        "Custos",
        "Economia",
        "Por usuário",
        "Por projeto",
        "Por fonte",
        "Por modelo",
        "Tendência diária",
        "Qualidade dos dados",
    ):
        assert label in html
    assert "1.250" in html
    assert "75,00%" in html
    assert "US$ 12,35" in html
    assert "US$ 18,50" in html
    assert "US$ 4,20" in html
    assert "Volume de tokens mede uso, não produtividade ou desempenho individual." in html
    assert "Orçamento mensal" not in html


def test_team_report_renders_budget_only_when_provided(tmp_path):
    repo = team_repo(tmp_path)
    analytics = TeamAnalyticsService(repo)
    budget = calculate_budget_status(100.0, 50.0, date(2026, 8, 15))
    output = tmp_path / "team-budget.html"

    generate_team_html_report(repo, analytics, output, budget=budget)

    html = output.read_text(encoding="utf-8")
    assert "Orçamento mensal" in html
    assert "US$ 100,00" in html
    assert "50,00%" in html
    assert "Projeção até o fim do mês" in html
