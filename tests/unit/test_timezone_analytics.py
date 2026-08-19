from datetime import date

from agentscope.analytics.dashboard import DashboardAnalyticsService
from agentscope.analytics.filters import AnalyticsFilter
from agentscope.diagnostics.codex_origin import CodexOriginDiagnostics
from agentscope.storage.database import Database
from agentscope.storage.repository import Repository


def _repo(tmp_path):
    db = Database(tmp_path / "agentscope.db")
    db.initialize()
    repo = Repository(db)
    with db.connect() as conn:
        conn.execute("INSERT INTO sources(name, type) VALUES('codex', 'codex')")
        conn.execute("INSERT INTO projects(name, path) VALUES('Project A', '/work/a')")
        conn.execute("INSERT INTO models(provider, name) VALUES('openai', 'gpt-5.6-sol')")
        conn.execute(
            "INSERT INTO users(stable_key, display_name, identity_confidence) "
            "VALUES('user-a', 'Dev A', 'inferred')"
        )
        conn.execute(
            "INSERT INTO machines(stable_key, display_name, os) "
            "VALUES('machine-a', 'Notebook A', 'Windows')"
        )
        source_id = conn.execute("SELECT id FROM sources WHERE name='codex'").fetchone()[0]
        project_id = conn.execute("SELECT id FROM projects WHERE name='Project A'").fetchone()[0]
        model_id = conn.execute("SELECT id FROM models WHERE name='gpt-5.6-sol'").fetchone()[0]
        user_id = conn.execute("SELECT id FROM users WHERE display_name='Dev A'").fetchone()[0]
        machine_id = conn.execute("SELECT id FROM machines WHERE display_name='Notebook A'").fetchone()[0]
        conn.execute(
            """
            INSERT INTO sessions(
                source_id, external_session_id, project_id, started_at,
                originator, provider, model_id, metadata_json, user_id, machine_id
            ) VALUES(?, 'cross-midnight', ?, '2026-08-18T23:41:22.488Z',
                     'codex_vscode', 'headroom', ?, '{"source":"vscode","thread_source":"user"}', ?, ?)
            """,
            (source_id, project_id, model_id, user_id, machine_id),
        )
        session_id = conn.execute(
            "SELECT id FROM sessions WHERE external_session_id='cross-midnight'"
        ).fetchone()[0]
        conn.execute(
            """
            INSERT INTO token_usage(
                session_id, timestamp, model_id, input_tokens,
                cached_input_tokens, output_tokens, total_tokens, event_key
            ) VALUES(?, '2026-08-19T00:10:00.000Z', ?, 500, 400, 0, 500, 'token-cross-midnight')
            """,
            (session_id, model_id),
        )
    return repo


def _filters(day):
    return AnalyticsFilter(
        from_date=day,
        to_date=day,
        user="Dev A",
        machine="Notebook A",
        utc_offset_minutes=-180,
    )


def test_dashboard_uses_local_day_for_utc_events_after_midnight(tmp_path):
    repo = _repo(tmp_path)

    local_previous_day = DashboardAnalyticsService(
        repo,
        _filters(date(2026, 8, 18)),
    )
    local_today = DashboardAnalyticsService(
        repo,
        _filters(date(2026, 8, 19)),
    )

    assert local_previous_day.summary().sessions == 1
    assert local_previous_day.summary().total_tokens == 500
    assert local_previous_day.by_day() == [
        {
            "date": "2026-08-18",
            "sessions": 1,
            "total_tokens": 500,
            "cache_ratio": 0.8,
            "observed_cost_usd": None,
            "estimated_cost_usd": None,
            "estimated_savings_usd": None,
        }
    ]
    assert local_today.summary().sessions == 0
    assert local_today.summary().total_tokens == 0
    assert local_today.by_day() == []


def test_codex_origin_diagnostics_uses_same_local_day_boundary(tmp_path):
    repo = _repo(tmp_path)

    previous_day = CodexOriginDiagnostics(
        repo,
        _filters(date(2026, 8, 18)),
    ).inspect()
    today = CodexOriginDiagnostics(
        repo,
        _filters(date(2026, 8, 19)),
    ).inspect()

    assert previous_day["summary"]["sessions"] == 1
    assert previous_day["summary"]["total_tokens"] == 500
    assert today["summary"]["sessions"] == 0
    assert today["summary"]["total_tokens"] == 0
