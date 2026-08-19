from datetime import date

from agentscope.analytics.filters import AnalyticsFilter
from agentscope.storage.database import Database
from agentscope.storage.repository import Repository
from agentscope.team.bundle import build_team_bundle


def repo_with_cross_day_events(tmp_path):
    db = Database(tmp_path / "bundle-dates.db")
    db.initialize()
    with db.connect() as conn:
        conn.execute("INSERT INTO sources(name, type) VALUES('codex', 'agent')")
        source_id = conn.execute("SELECT id FROM sources WHERE name='codex'").fetchone()[0]
        conn.execute(
            """
            INSERT INTO users(stable_key, display_name, identity_confidence)
            VALUES('u1', 'Dev A', 'inferred')
            """
        )
        user_id = conn.execute("SELECT id FROM users WHERE stable_key='u1'").fetchone()[0]
        conn.execute("INSERT INTO machines(stable_key, display_name) VALUES('m1', 'Notebook A')")
        machine_id = conn.execute("SELECT id FROM machines WHERE stable_key='m1'").fetchone()[0]

        conn.execute(
            """
            INSERT INTO sessions(
                source_id, external_session_id, started_at, user_id, machine_id
            ) VALUES(?, 'started-before', '2026-08-17T23:50:00Z', ?, ?)
            """,
            (source_id, user_id, machine_id),
        )
        before_id = conn.execute(
            "SELECT id FROM sessions WHERE external_session_id='started-before'"
        ).fetchone()[0]
        conn.execute(
            """
            INSERT INTO token_usage(
                session_id, timestamp, input_tokens, output_tokens,
                total_tokens, event_key
            ) VALUES(?, '2026-08-18T00:10:00Z', 100, 20, 120, 'inside-from-old-session')
            """,
            (before_id,),
        )

        conn.execute(
            """
            INSERT INTO sessions(
                source_id, external_session_id, started_at, user_id, machine_id
            ) VALUES(?, 'started-inside', '2026-08-18T09:00:00Z', ?, ?)
            """,
            (source_id, user_id, machine_id),
        )
        inside_id = conn.execute(
            "SELECT id FROM sessions WHERE external_session_id='started-inside'"
        ).fetchone()[0]
        conn.execute(
            """
            INSERT INTO token_usage(
                session_id, timestamp, input_tokens, output_tokens,
                total_tokens, event_key
            ) VALUES(?, '2026-08-18T09:05:00Z', 200, 30, 230, 'inside-event')
            """,
            (inside_id,),
        )
        conn.execute(
            """
            INSERT INTO token_usage(
                session_id, timestamp, input_tokens, output_tokens,
                total_tokens, event_key
            ) VALUES(?, '2026-08-19T00:05:00Z', 300, 40, 340, 'outside-event')
            """,
            (inside_id,),
        )
    return Repository(db)


def test_team_bundle_date_filter_includes_in_range_event_from_older_session(tmp_path):
    bundle = build_team_bundle(
        repo_with_cross_day_events(tmp_path),
        AnalyticsFilter(from_date=date(2026, 8, 18), to_date=date(2026, 8, 18)),
    )

    sessions = {row["external_session_id"] for row in bundle["records"]["sessions"]}
    totals = sorted(row["total_tokens"] for row in bundle["records"]["token_usage"])

    assert "started-before" in sessions
    assert "started-inside" in sessions
    assert totals == [120, 230]


def test_team_bundle_date_filter_excludes_event_after_selected_day(tmp_path):
    bundle = build_team_bundle(
        repo_with_cross_day_events(tmp_path),
        AnalyticsFilter(from_date=date(2026, 8, 18), to_date=date(2026, 8, 18)),
    )

    assert all(
        row["timestamp"].startswith("2026-08-18")
        for row in bundle["records"]["token_usage"]
    )
    assert sum(row["total_tokens"] for row in bundle["records"]["token_usage"]) == 350
