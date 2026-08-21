from datetime import date

from agentscope.analytics.dashboard import DashboardAnalyticsService
from agentscope.analytics.filters import AnalyticsFilter
from agentscope.storage.database import Database
from agentscope.storage.repository import Repository


def _repo(tmp_path):
    db = Database(tmp_path / "agentscope.db")
    db.initialize()
    repo = Repository(db)
    with db.connect() as conn:
        conn.execute("INSERT INTO sources(name, type) VALUES('codex', 'codex')")
        conn.execute("INSERT INTO projects(name, path) VALUES('demo', '/work/demo')")
        conn.execute("INSERT INTO projects(name, path) VALUES('other', '/work/other')")
        for model in ("gpt-5.6-sol", "gpt-5.6-terra", "codex-auto-review"):
            conn.execute("INSERT INTO models(provider, name) VALUES('openai', ?)", (model,))
        conn.execute(
            "INSERT INTO users(stable_key, display_name) VALUES('user-a', 'Dev A')"
        )
        conn.execute(
            "INSERT INTO users(stable_key, display_name) VALUES('user-b', 'Dev B')"
        )
        conn.execute(
            "INSERT INTO machines(stable_key, display_name) VALUES('machine-a', 'Notebook A')"
        )
        conn.execute(
            "INSERT INTO machines(stable_key, display_name) VALUES('machine-b', 'Notebook B')"
        )

        source_id = conn.execute("SELECT id FROM sources WHERE name='codex'").fetchone()[0]
        demo_id = conn.execute("SELECT id FROM projects WHERE name='demo'").fetchone()[0]
        other_id = conn.execute("SELECT id FROM projects WHERE name='other'").fetchone()[0]
        user_a = conn.execute("SELECT id FROM users WHERE stable_key='user-a'").fetchone()[0]
        user_b = conn.execute("SELECT id FROM users WHERE stable_key='user-b'").fetchone()[0]
        machine_a = conn.execute("SELECT id FROM machines WHERE stable_key='machine-a'").fetchone()[0]
        machine_b = conn.execute("SELECT id FROM machines WHERE stable_key='machine-b'").fetchone()[0]

        def model_id(name):
            return conn.execute("SELECT id FROM models WHERE name=?", (name,)).fetchone()[0]

        def session(external_id, model, project_id, user_id, machine_id, hour):
            mid = model_id(model)
            conn.execute(
                """
                INSERT INTO sessions(
                    source_id, external_session_id, project_id, started_at, model_id,
                    user_id, machine_id
                ) VALUES(?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    source_id,
                    external_id,
                    project_id,
                    f"2026-08-18T{hour:02d}:00:00Z",
                    mid,
                    user_id,
                    machine_id,
                ),
            )
            return conn.execute(
                "SELECT id FROM sessions WHERE external_session_id=?", (external_id,)
            ).fetchone()[0]

        def usage(session_id, model, event_key, hour, total_tokens=120, token_source="source_reported"):
            mid = model_id(model)
            conn.execute(
                """
                INSERT INTO token_usage(
                    session_id, timestamp, model_id, input_tokens,
                    cached_input_tokens, output_tokens, total_tokens,
                    token_source, event_key
                ) VALUES(?, ?, ?, 100, 80, 20, ?, ?, ?)
                """,
                (
                    session_id,
                    f"2026-08-18T{hour:02d}:05:00Z",
                    mid,
                    total_tokens,
                    token_source,
                    event_key,
                ),
            )
            return conn.execute(
                "SELECT id FROM token_usage WHERE event_key=?", (event_key,)
            ).fetchone()[0]

        def cost(session_id, model, usage_id, value, hour):
            conn.execute(
                """
                INSERT INTO costs(
                    session_id, model_id, period_start,
                    estimated_raw_cost_usd, event_key
                ) VALUES(?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    model_id(model),
                    f"2026-08-18T{hour:02d}:05:00Z",
                    value,
                    f"token_usage_cost:{usage_id}",
                ),
            )

        sol = session("sol", "gpt-5.6-sol", demo_id, user_a, machine_a, 10)
        sol_1 = usage(sol, "gpt-5.6-sol", "sol-1", 10)
        sol_2 = usage(sol, "gpt-5.6-sol", "sol-2", 11)
        cost(sol, "gpt-5.6-sol", sol_1, 0.20, 10)
        cost(sol, "gpt-5.6-sol", sol_2, 0.30, 11)

        terra = session("terra", "gpt-5.6-terra", demo_id, user_a, machine_a, 12)
        terra_1 = usage(terra, "gpt-5.6-terra", "terra-1", 12)
        usage(terra, "gpt-5.6-terra", "terra-2", 13)
        cost(terra, "gpt-5.6-terra", terra_1, 0.40, 12)

        review = session("review", "codex-auto-review", demo_id, user_a, machine_a, 14)
        usage(review, "codex-auto-review", "review-1", 14)

        excluded = session("excluded", "gpt-5.6-sol", other_id, user_b, machine_b, 15)
        excluded_usage = usage(excluded, "gpt-5.6-sol", "excluded-1", 15, total_tokens=999)
        cost(excluded, "gpt-5.6-sol", excluded_usage, 9.99, 15)

        estimated = session("estimated", "gpt-5.6-sol", demo_id, user_a, machine_a, 16)
        usage(
            estimated,
            "gpt-5.6-sol",
            "estimated-1",
            16,
            total_tokens=50,
            token_source="tiktoken_estimate",
        )
    return repo


def _filters():
    return AnalyticsFilter(
        from_date=date(2026, 8, 18),
        to_date=date(2026, 8, 18),
        project="demo",
        source="codex",
        user="Dev A",
        machine="Notebook A",
        utc_offset_minutes=0,
    )


def test_model_breakdown_exposes_cost_only_for_complete_model_coverage(tmp_path):
    rows = DashboardAnalyticsService(_repo(tmp_path), _filters()).by_model()
    by_model = {row["model"]: row for row in rows}

    assert by_model["gpt-5.6-sol"] == {
        "model": "gpt-5.6-sol",
        "sessions": 2,
        "total_tokens": 290,
        "estimated_cost_usd": None,
        "cost_events_total": 3,
        "cost_events_priced": 2,
        "cost_complete": False,
    }
    assert by_model["gpt-5.6-terra"] == {
        "model": "gpt-5.6-terra",
        "sessions": 1,
        "total_tokens": 240,
        "estimated_cost_usd": None,
        "cost_events_total": 2,
        "cost_events_priced": 1,
        "cost_complete": False,
    }
    assert by_model["codex-auto-review"] == {
        "model": "codex-auto-review",
        "sessions": 1,
        "total_tokens": 120,
        "estimated_cost_usd": None,
        "cost_events_total": 1,
        "cost_events_priced": 0,
        "cost_complete": False,
    }


def test_model_breakdown_exposes_exact_cost_when_model_coverage_is_complete(tmp_path):
    repo = _repo(tmp_path)
    with repo.database.connect() as conn:
        conn.execute("DELETE FROM token_usage WHERE event_key='estimated-1'")

    rows = DashboardAnalyticsService(repo, _filters()).by_model()
    sol = next(row for row in rows if row["model"] == "gpt-5.6-sol")

    assert sol["sessions"] == 1
    assert sol["total_tokens"] == 240
    assert sol["estimated_cost_usd"] == 0.50
    assert sol["cost_events_total"] == 2
    assert sol["cost_events_priced"] == 2
    assert sol["cost_complete"] is True
