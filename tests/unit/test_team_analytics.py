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
    observed_cost: float | None = None,
    estimated_cost: float | None = None,
    total_savings: float | None = None,
    optimizer_compression_savings: float | None = None,
    optimizer_cache_savings: float | None = None,
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
        if any(value is not None for value in (observed_cost, estimated_cost, total_savings)):
            conn.execute(
                """
                INSERT INTO costs(
                    session_id, model_id, period_start, observed_cost_usd,
                    estimated_raw_cost_usd, total_savings_usd, event_key
                ) VALUES(?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    model_id,
                    started_at,
                    observed_cost,
                    estimated_cost,
                    total_savings,
                    f"cost-{name}",
                ),
            )
        if any(
            value is not None
            for value in (optimizer_compression_savings, optimizer_cache_savings)
        ):
            conn.execute(
                "INSERT INTO optimizers(name, version) VALUES('headroom', 'test')"
            )
            optimizer_id = conn.execute(
                "SELECT id FROM optimizers WHERE name='headroom' AND version='test'"
            ).fetchone()[0]
            conn.execute(
                """
                INSERT INTO optimizations(
                    optimizer_id, session_id, timestamp, model_id,
                    compression_savings_usd, cache_savings_usd,
                    correlation_confidence, event_key
                ) VALUES(?, ?, ?, ?, ?, ?, 'exact', ?)
                """,
                (
                    optimizer_id,
                    session_id,
                    started_at,
                    model_id,
                    optimizer_compression_savings,
                    optimizer_cache_savings,
                    f"optimizer-{name}",
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


def financial_team_repo(tmp_path):
    bundles = [
        local_bundle(
            tmp_path,
            name="cost-a",
            user_key="cost-user-a",
            user_name="Dev Cost A",
            machine_key="cost-machine-a",
            machine_name="Notebook Cost A",
            source="codex",
            project="Projeto Cost A",
            model="gpt-cost-a",
            started_at="2026-08-18T09:00:00Z",
            input_tokens=100,
            cached_tokens=50,
            output_tokens=20,
            observed_cost=4.0,
            total_savings=1.5,
        ),
        local_bundle(
            tmp_path,
            name="cost-b",
            user_key="cost-user-b",
            user_name="Dev Cost B",
            machine_key="cost-machine-b",
            machine_name="Notebook Cost B",
            source="claude_code",
            project="Projeto Cost B",
            model="claude-cost-b",
            started_at="2026-08-18T10:00:00Z",
            input_tokens=200,
            cached_tokens=75,
            output_tokens=30,
            estimated_cost=7.0,
        ),
        local_bundle(
            tmp_path,
            name="cost-c",
            user_key="cost-user-c",
            user_name="Dev Cost C",
            machine_key="cost-machine-c",
            machine_name="Notebook Cost C",
            source="gemini",
            project="Projeto Cost C",
            model="gemini-cost-c",
            started_at="2026-08-18T11:00:00Z",
            input_tokens=300,
            cached_tokens=100,
            output_tokens=40,
            optimizer_compression_savings=2.0,
            optimizer_cache_savings=3.0,
        ),
    ]
    team_db = Database(tmp_path / "team-financial.db")
    team_db.initialize()
    repo = Repository(team_db)
    for bundle in bundles:
        import_team_bundle(repo, bundle)
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


def test_team_cost_attribution_keeps_observed_and_estimated_separate(tmp_path):
    analytics = TeamAnalyticsService(financial_team_repo(tmp_path))

    by_user = {row["user"]: row for row in analytics.cost_by_user()}
    assert by_user["Dev Cost A"]["observed_cost_usd"] == 4.0
    assert by_user["Dev Cost A"]["estimated_raw_cost_usd"] is None
    assert by_user["Dev Cost B"]["observed_cost_usd"] is None
    assert by_user["Dev Cost B"]["estimated_raw_cost_usd"] == 7.0
    assert "Dev Cost C" not in by_user

    assert {row["project"] for row in analytics.cost_by_project()} == {
        "Projeto Cost A",
        "Projeto Cost B",
    }
    assert {row["source"] for row in analytics.cost_by_source()} == {
        "codex",
        "claude_code",
    }
    assert {row["model"] for row in analytics.cost_by_model()} == {
        "gpt-cost-a",
        "claude-cost-b",
    }


def test_team_savings_attribution_combines_cost_and_optimizer_sources(tmp_path):
    analytics = TeamAnalyticsService(financial_team_repo(tmp_path))

    by_user = {row["user"]: row for row in analytics.savings_by_user()}
    assert by_user["Dev Cost A"]["total_savings_usd"] == 1.5
    assert by_user["Dev Cost C"]["total_savings_usd"] == 5.0
    assert "Dev Cost B" not in by_user

    assert {row["project"] for row in analytics.savings_by_project()} == {
        "Projeto Cost A",
        "Projeto Cost C",
    }
    assert {row["source"] for row in analytics.savings_by_source()} == {
        "codex",
        "gemini",
    }
    assert {row["model"] for row in analytics.savings_by_model()} == {
        "gpt-cost-a",
        "gemini-cost-c",
    }
