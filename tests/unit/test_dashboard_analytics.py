from datetime import date

from agentscope.analytics.filters import AnalyticsFilter
from agentscope.analytics.service import AnalyticsService
from agentscope.storage.database import Database
from agentscope.storage.repository import Repository


def _repo(tmp_path):
    db = Database(tmp_path / "agentscope.db")
    db.initialize()
    repo = Repository(db)
    with db.connect() as conn:
        conn.execute("INSERT INTO sources(name, type) VALUES('codex', 'codex')")
        conn.execute("INSERT INTO projects(name, path) VALUES('Project A', '/work/project-a')")
        conn.execute("INSERT INTO models(provider, name) VALUES('openai', 'gpt-5.6-sol')")
        conn.execute(
            """
            INSERT INTO users(stable_key, display_name, identity_confidence)
            VALUES('user-a', 'Dev A', 'inferred')
            """
        )
        conn.execute(
            """
            INSERT INTO machines(stable_key, display_name, os)
            VALUES('machine-a', 'Notebook A', 'Windows')
            """
        )
    return db, repo


def _ids(db):
    with db.connect() as conn:
        return {
            "source": conn.execute("SELECT id FROM sources WHERE name='codex'").fetchone()[0],
            "project": conn.execute("SELECT id FROM projects WHERE name='Project A'").fetchone()[0],
            "model": conn.execute("SELECT id FROM models WHERE name='gpt-5.6-sol'").fetchone()[0],
            "user": conn.execute("SELECT id FROM users WHERE display_name='Dev A'").fetchone()[0],
            "machine": conn.execute("SELECT id FROM machines WHERE display_name='Notebook A'").fetchone()[0],
        }


def _insert_session(db, external_id, started_at, *, with_usage=True, with_money=True):
    ids = _ids(db)
    with db.connect() as conn:
        conn.execute(
            """
            INSERT INTO sessions(
                source_id, external_session_id, project_id, started_at,
                provider, model_id, user_id, machine_id
            ) VALUES(?, ?, ?, ?, 'openai', ?, ?, ?)
            """,
            (
                ids["source"], external_id, ids["project"], started_at,
                ids["model"], ids["user"], ids["machine"],
            ),
        )
        session_id = conn.execute(
            "SELECT id FROM sessions WHERE external_session_id=?",
            (external_id,),
        ).fetchone()[0]
        day = started_at[:10]
        if with_usage:
            conn.execute(
                """
                INSERT INTO token_usage(
                    session_id, timestamp, model_id, input_tokens,
                    cached_input_tokens, output_tokens, total_tokens, event_key
                ) VALUES(?, ?, ?, 100, 80, 50, 150, ?)
                """,
                (session_id, f"{day}T10:05:00Z", ids["model"], f"token-{external_id}"),
            )
        if with_money:
            conn.execute(
                """
                INSERT INTO costs(
                    session_id, model_id, period_start,
                    estimated_raw_cost_usd, observed_cost_usd,
                    total_savings_usd, event_key
                ) VALUES(?, ?, ?, 0.20, 0.12, 0.08, ?)
                """,
                (session_id, ids["model"], f"{day}T00:00:00Z", f"cost-{external_id}"),
            )


def test_by_day_combines_session_usage_cache_and_monetary_metrics(tmp_path):
    db, repo = _repo(tmp_path)
    _insert_session(db, "session-1", "2026-08-19T10:00:00Z")

    rows = AnalyticsService(repo).by_day()

    assert rows == [
        {
            "date": "2026-08-19",
            "sessions": 1,
            "total_tokens": 150,
            "cache_ratio": 0.8,
            "observed_cost_usd": 0.12,
            "estimated_cost_usd": 0.20,
            "estimated_savings_usd": 0.08,
        }
    ]


def test_by_day_keeps_session_without_token_or_money_events(tmp_path):
    db, repo = _repo(tmp_path)
    _insert_session(
        db,
        "session-only",
        "2026-08-20T10:00:00Z",
        with_usage=False,
        with_money=False,
    )

    rows = AnalyticsService(repo).by_day()

    assert rows == [
        {
            "date": "2026-08-20",
            "sessions": 1,
            "total_tokens": 0,
            "cache_ratio": None,
            "observed_cost_usd": None,
            "estimated_cost_usd": None,
            "estimated_savings_usd": None,
        }
    ]


def test_dashboard_breakdowns_and_series_honor_all_filters(tmp_path):
    db, repo = _repo(tmp_path)
    _insert_session(db, "session-1", "2026-08-19T10:00:00Z")

    filters = AnalyticsFilter(
        from_date=date(2026, 8, 19),
        to_date=date(2026, 8, 19),
        project="Project A",
        model="gpt-5.6-sol",
        source="codex",
        user="Dev A",
        machine="Notebook A",
    )
    analytics = AnalyticsService(repo, filters)

    assert analytics.by_day()[0]["date"] == "2026-08-19"
    assert analytics.by_project()[0]["project"] == "Project A"
    assert analytics.by_project()[0]["total_tokens"] == 150
    assert analytics.by_model()[0]["model"] == "gpt-5.6-sol"
    assert analytics.by_model()[0]["total_tokens"] == 150
    assert analytics.by_source() == [
        {"source": "codex", "sessions": 1, "total_tokens": 150}
    ]

    missing = AnalyticsService(repo, AnalyticsFilter(user="Missing"))
    assert missing.by_day() == []
    assert missing.by_source() == []
