from agentscope.analytics.filters import AnalyticsFilter
from agentscope.analytics.team_service import TeamAnalyticsService
from agentscope.reporting.team_html_report import generate_team_html_report
from agentscope.storage.database import Database
from agentscope.storage.repository import Repository
from agentscope.team.bundle import build_team_bundle
from agentscope.team.importer import import_team_bundle


SENTINELS = (
    "TEAM_REPORT_PROMPT_SECRET",
    "TEAM_REPORT_RESPONSE_SECRET",
    r"C:\private\project-a",
    r"C:\private\project-b",
)


def developer_bundle(
    path,
    *,
    suffix,
    user,
    machine,
    project,
    source,
    model,
    started_at,
    input_tokens,
    cached_tokens,
    output_tokens,
    observed_cost=None,
    estimated_cost=None,
):
    db = Database(path)
    db.initialize()
    with db.connect() as conn:
        conn.execute("INSERT INTO sources(name, type) VALUES(?, 'agent')", (source,))
        source_id = conn.execute("SELECT id FROM sources WHERE name=?", (source,)).fetchone()[0]
        private_path = rf"C:\private\project-{suffix}"
        conn.execute("INSERT INTO projects(name, path) VALUES(?, ?)", (project, private_path))
        project_id = conn.execute("SELECT id FROM projects WHERE name=?", (project,)).fetchone()[0]
        conn.execute("INSERT INTO models(provider, name) VALUES(?, ?)", (source, model))
        model_id = conn.execute("SELECT id FROM models WHERE name=?", (model,)).fetchone()[0]
        conn.execute(
            "INSERT INTO users(stable_key, display_name, identity_confidence) VALUES(?, ?, 'inferred')",
            (f"user-{suffix}", user),
        )
        user_id = conn.execute("SELECT id FROM users WHERE stable_key=?", (f"user-{suffix}",)).fetchone()[0]
        conn.execute(
            "INSERT INTO machines(stable_key, display_name, os) VALUES(?, ?, 'Windows')",
            (f"machine-{suffix}", machine),
        )
        machine_id = conn.execute("SELECT id FROM machines WHERE stable_key=?", (f"machine-{suffix}",)).fetchone()[0]
        conn.execute(
            """
            INSERT INTO sessions(
                source_id, external_session_id, project_id, started_at,
                provider, model_id, user_id, machine_id, raw_file_path
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                source_id,
                f"session-{suffix}",
                project_id,
                started_at,
                source,
                model_id,
                user_id,
                machine_id,
                private_path + r"\session.jsonl",
            ),
        )
        session_id = conn.execute("SELECT id FROM sessions").fetchone()[0]
        conn.execute(
            "INSERT INTO messages(session_id, role, timestamp, content, event_key) VALUES(?, 'user', ?, 'TEAM_REPORT_PROMPT_SECRET', ?)",
            (session_id, started_at, f"prompt-{suffix}"),
        )
        conn.execute(
            "INSERT INTO messages(session_id, role, timestamp, content, event_key) VALUES(?, 'assistant', ?, 'TEAM_REPORT_RESPONSE_SECRET', ?)",
            (session_id, started_at, f"response-{suffix}"),
        )
        conn.execute(
            """
            INSERT INTO token_usage(
                session_id, timestamp, model_id, input_tokens,
                cached_input_tokens, output_tokens, total_tokens, event_key
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session_id,
                started_at,
                model_id,
                input_tokens,
                cached_tokens,
                output_tokens,
                input_tokens + output_tokens,
                f"tokens-{suffix}",
            ),
        )
        if observed_cost is not None or estimated_cost is not None:
            conn.execute(
                """
                INSERT INTO costs(
                    session_id, model_id, period_start,
                    observed_cost_usd, estimated_raw_cost_usd, event_key
                ) VALUES(?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    model_id,
                    started_at,
                    observed_cost,
                    estimated_cost,
                    f"cost-{suffix}",
                ),
            )
    return build_team_bundle(Repository(db), organization="Org", team="Backend")


def test_two_developer_team_report_flow_is_filtered_private_and_idempotent(tmp_path):
    bundle_a = developer_bundle(
        tmp_path / "a.db",
        suffix="a",
        user="Dev A",
        machine="Notebook A",
        project="Projeto A",
        source="codex",
        model="gpt-a",
        started_at="2026-08-17T10:00:00Z",
        input_tokens=1000,
        cached_tokens=700,
        output_tokens=200,
        observed_cost=4.25,
    )
    bundle_b = developer_bundle(
        tmp_path / "b.db",
        suffix="b",
        user="Dev B",
        machine="Notebook B",
        project="Projeto B",
        source="claude_code",
        model="claude-b",
        started_at="2026-08-18T11:00:00Z",
        input_tokens=2000,
        cached_tokens=500,
        output_tokens=300,
        estimated_cost=7.5,
    )

    team_db = Database(tmp_path / "team.db")
    team_db.initialize()
    repo = Repository(team_db)
    first_a = import_team_bundle(repo, bundle_a)
    first_b = import_team_bundle(repo, bundle_b)
    assert first_a.events_imported == 2
    assert first_b.events_imported == 2

    all_report = tmp_path / "all.html"
    all_analytics = TeamAnalyticsService(repo)
    generate_team_html_report(repo, all_analytics, all_report)
    all_html = all_report.read_text(encoding="utf-8")

    assert "Dev A" in all_html
    assert "Dev B" in all_html
    assert "3.500" in all_html
    assert "US$ 4,25" in all_html
    assert "US$ 7,50" in all_html
    for sentinel in SENTINELS:
        assert sentinel not in all_html

    filtered_report = tmp_path / "filtered.html"
    filtered = TeamAnalyticsService(repo, AnalyticsFilter(user="Dev A"))
    generate_team_html_report(repo, filtered, filtered_report)
    filtered_html = filtered_report.read_text(encoding="utf-8")

    assert "Dev A" in filtered_html
    assert "Dev B" not in filtered_html
    assert "1.200" in filtered_html
    assert "US$ 4,25" in filtered_html
    assert "US$ 7,50" not in filtered_html

    with team_db.connect() as conn:
        before = (
            conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0],
            conn.execute("SELECT COUNT(*) FROM token_usage").fetchone()[0],
            conn.execute("SELECT COUNT(*) FROM costs").fetchone()[0],
        )
    repeated_a = import_team_bundle(repo, bundle_a)
    repeated_b = import_team_bundle(repo, bundle_b)
    assert repeated_a.events_imported == 0
    assert repeated_b.events_imported == 0
    with team_db.connect() as conn:
        after = (
            conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0],
            conn.execute("SELECT COUNT(*) FROM token_usage").fetchone()[0],
            conn.execute("SELECT COUNT(*) FROM costs").fetchone()[0],
        )
    assert before == after == (2, 2, 2)
