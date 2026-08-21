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
        conn.execute("INSERT INTO models(provider, name) VALUES('openai', 'gpt-5.6-sol')")
        source_id = conn.execute("SELECT id FROM sources WHERE name='codex'").fetchone()[0]
        project_id = conn.execute("SELECT id FROM projects WHERE name='demo'").fetchone()[0]
        model_id = conn.execute("SELECT id FROM models WHERE name='gpt-5.6-sol'").fetchone()[0]
        conn.execute(
            """
            INSERT INTO sessions(source_id, external_session_id, project_id, started_at, model_id)
            VALUES(?, 's1', ?, '2026-08-18T10:00:00Z', ?)
            """,
            (source_id, project_id, model_id),
        )
        session_id = conn.execute("SELECT id FROM sessions WHERE external_session_id='s1'").fetchone()[0]
        for idx, hour in ((1, 10), (2, 11)):
            conn.execute(
                """
                INSERT INTO token_usage(
                    session_id, timestamp, model_id, input_tokens,
                    cached_input_tokens, output_tokens, total_tokens, event_key
                ) VALUES(?, ?, ?, 100, 80, 20, 120, ?)
                """,
                (session_id, f"2026-08-18T{hour:02d}:05:00Z", model_id, f"token-{idx}"),
            )
        first_usage_id = conn.execute(
            "SELECT id FROM token_usage WHERE event_key='token-1'"
        ).fetchone()[0]
        conn.execute(
            """
            INSERT INTO costs(
                session_id, model_id, period_start, estimated_raw_cost_usd, event_key
            ) VALUES(?, ?, '2026-08-18T10:05:00Z', 0.20, ?)
            """,
            (session_id, model_id, f"token_usage_cost:{first_usage_id}"),
        )
    return db, repo


def _filters():
    return AnalyticsFilter(
        from_date=date(2026, 8, 18),
        to_date=date(2026, 8, 18),
        project="demo",
        model="gpt-5.6-sol",
        source="codex",
        utc_offset_minutes=0,
    )


def test_dashboard_summary_does_not_present_partial_estimate_as_total(tmp_path):
    _, repo = _repo(tmp_path)
    analytics = DashboardAnalyticsService(repo, _filters())

    summary = analytics.summary()
    coverage = analytics.estimated_cost_coverage()

    assert summary.estimated_raw_cost_usd is None
    assert coverage == {
        "events_total": 2,
        "events_priced": 1,
        "known_estimated_cost_usd": 0.20,
        "complete": False,
    }


def test_dashboard_daily_estimate_is_null_when_day_has_partial_coverage(tmp_path):
    _, repo = _repo(tmp_path)

    row = DashboardAnalyticsService(repo, _filters()).by_day()[0]

    assert row["estimated_cost_usd"] is None


def test_dashboard_exposes_total_only_when_every_usage_event_is_priced(tmp_path):
    db, repo = _repo(tmp_path)
    with db.connect() as conn:
        second_usage_id = conn.execute(
            "SELECT id FROM token_usage WHERE event_key='token-2'"
        ).fetchone()[0]
        session_id = conn.execute("SELECT id FROM sessions WHERE external_session_id='s1'").fetchone()[0]
        model_id = conn.execute("SELECT id FROM models WHERE name='gpt-5.6-sol'").fetchone()[0]
        conn.execute(
            """
            INSERT INTO costs(
                session_id, model_id, period_start, estimated_raw_cost_usd, event_key
            ) VALUES(?, ?, '2026-08-18T11:05:00Z', 0.30, ?)
            """,
            (session_id, model_id, f"token_usage_cost:{second_usage_id}"),
        )

    analytics = DashboardAnalyticsService(repo, _filters())
    summary = analytics.summary()
    coverage = analytics.estimated_cost_coverage()

    assert coverage == {
        "events_total": 2,
        "events_priced": 2,
        "known_estimated_cost_usd": 0.50,
        "complete": True,
    }
    assert summary.estimated_raw_cost_usd == 0.50
