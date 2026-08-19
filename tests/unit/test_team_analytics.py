from datetime import date

from agentscope.analytics.filters import AnalyticsFilter
from agentscope.analytics.team_service import TeamAnalyticsService
from agentscope.storage.database import Database
from agentscope.storage.repository import Repository
from agentscope.team.bundle import build_team_bundle
from agentscope.team.importer import import_team_bundle


def local_bundle(
    tmp_path,
    *,
    name: str,
    user_key: str,
    user_name: str,
    machine_key: str,
    machine_name: str,
    source: str,
    project: str,
    model: str,
    started_at: str,
    input_tokens: int,
    cached_tokens: int,
    output_tokens: int,
):
    db = Database(tmp_path / f"{name}.db")
    db.initialize()
    with db.connect() as conn:
        conn.execute("INSERT INTO sources(name, type) VALUES(?, 'agent')", (source,))
        source_id = conn.execute(
            "SELECT id FROM sources WHERE name=?", (source,)
        ).fetchone()[0]
        conn.execute(
            "INSERT INTO projects(name, path) VALUES(?, ?)",
            (project, f"C:/private/{name}/{project}"),
        )
        project_id = conn.execute(
            "SELECT id FROM projects WHERE name=?", (project,)
        ).fetchone()[0]
        conn.execute(
            "INSERT INTO models(provider, name) VALUES(?, ?)",
            (source, model),
        )
        model_id = conn.execute(
            "SELECT id FROM models WHERE provider=? AND name=?", (source, model)
        ).fetchone()[0]
        conn.execute(
            """
            INSERT INTO users(stable_key, display_name, identity_confidence)
            VALUES(?, ?, 'inferred')
            """,
            (user_key, user_name),
        )
        user_id = conn.execute(
            "SELECT id FROM users WHERE stable_key=?", (user_key,)
        ).fetchone()[0]
        conn.execute(
            """
            INSERT INTO machines(stable_key, display_name, os)
            VALUES(?, ?, 'Windows')
            """,
            (machine_key, machine_name),
        )
        machine_id = conn.execute(
            "SELECT id FROM machines WHERE stable_key=?", (machine_key,)
        ).fetchone()[0]
        conn.execute(
            """
            INSERT INTO sessions(
                source_id, external_session_id, project_id, started_at,
                provider, model_id, user_id, machine_id
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                source_id,
                f"session-{name}",
                project_id,
                started_at,
                source,
                model_id,
                user_id,
                machine_id,
            ),
        )
        session_id = conn.execute(
            "SELECT id FROM sessions WHERE external_session_id=?",
            (f"session-{name}",),
        ).fetchone()[0]
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
                f"token-{name}",
            ),
        )
    return build_team_bundle(Repository(db), organization="Org", team="Backend")


def consolidated_team_repo(tmp_path):
    bundle_a = local_bundle(
        tmp_path,
        name="a",
        user_key="user-a",
        user_name="Dev A",
        machine_key="machine-a",
        machine_name="Notebook A",
        source="codex",
        project="Projeto A",
        model="gpt-a",
        started_at="2026-08-17T10:00:00Z",
        input_tokens=1000,
        cached_tokens=700,
        output_tokens=200,
    )
    bundle_b = local_bundle(
        tmp_path,
        name="b",
        user_key="user-b",
        user_name="Dev B",
        machine_key="machine-b",
        machine_name="Notebook B",
        source="claude_code",
        project="Projeto B",
        model="claude-b",
        started_at="2026-08-18T11:00:00Z",
        input_tokens=2000,
        cached_tokens=500,
        output_tokens=300,
    )

    team_db = Database(tmp_path / "team.db")
    team_db.initialize()
    repo = Repository(team_db)
    import_team_bundle(repo, bundle_a)
    import_team_bundle(repo, bundle_b)
    return repo


def test_team_summary_counts_people_machines_sessions_and_tokens(tmp_path):
    analytics = TeamAnalyticsService(consolidated_team_repo(tmp_path))

    summary = analytics.summary()

    assert summary.users == 2
    assert summary.machines == 2
    assert summary.sessions == 2
    assert summary.input_tokens == 3000
    assert summary.cached_input_tokens == 1200
    assert summary.output_tokens == 500
    assert summary.total_tokens == 3500
    assert summary.observed_cost_usd is None
    assert summary.estimated_raw_cost_usd is None
    assert summary.total_savings_usd is None


def test_team_usage_is_aggregated_by_each_dimension(tmp_path):
    analytics = TeamAnalyticsService(consolidated_team_repo(tmp_path))

    assert [(row["user"], row["total_tokens"]) for row in analytics.by_user()] == [
        ("Dev B", 2300),
        ("Dev A", 1200),
    ]
    assert [(row["machine"], row["total_tokens"]) for row in analytics.by_machine()] == [
        ("Notebook B", 2300),
        ("Notebook A", 1200),
    ]
    assert {row["project"] for row in analytics.by_project()} == {"Projeto A", "Projeto B"}
    assert {row["source"] for row in analytics.by_source()} == {"codex", "claude_code"}
    assert {row["model"] for row in analytics.by_model()} == {"gpt-a", "claude-b"}
    assert [(row["day"], row["total_tokens"]) for row in analytics.by_day()] == [
        ("2026-08-17", 1200),
        ("2026-08-18", 2300),
    ]


def test_team_summary_obeys_shared_user_and_date_filters(tmp_path):
    repo = consolidated_team_repo(tmp_path)
    analytics = TeamAnalyticsService(
        repo,
        AnalyticsFilter(
            from_date=date(2026, 8, 18),
            to_date=date(2026, 8, 18),
            user="Dev B",
        ),
    )

    summary = analytics.summary()

    assert summary.users == 1
    assert summary.machines == 1
    assert summary.sessions == 1
    assert summary.total_tokens == 2300
