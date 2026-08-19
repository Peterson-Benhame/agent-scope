from datetime import date

from agentscope.analytics.filters import AnalyticsFilter
from agentscope.analytics.team_service import TeamAnalyticsService
from agentscope.storage.database import Database
from agentscope.storage.repository import Repository


def test_source_coverage_obeys_selected_period(tmp_path):
    db = Database(tmp_path / "quality-filter.db")
    db.initialize()
    with db.connect() as conn:
        conn.execute("INSERT INTO sources(name, type) VALUES('codex', 'team-import')")
        source_id = conn.execute("SELECT id FROM sources WHERE name='codex'").fetchone()[0]
        conn.execute(
            """
            INSERT INTO sessions(source_id, external_session_id, started_at)
            VALUES(?, 'aug-1', '2026-08-01T09:00:00Z')
            """,
            (source_id,),
        )
        aug1 = conn.execute(
            "SELECT id FROM sessions WHERE external_session_id='aug-1'"
        ).fetchone()[0]
        conn.execute(
            """
            INSERT INTO costs(session_id, period_start, observed_cost_usd, event_key)
            VALUES(?, '2026-08-01T09:00:00Z', 10.0, 'cost-aug-1')
            """,
            (aug1,),
        )
        conn.execute(
            """
            INSERT INTO sessions(source_id, external_session_id, started_at)
            VALUES(?, 'aug-18', '2026-08-18T09:00:00Z')
            """,
            (source_id,),
        )
        aug18 = conn.execute(
            "SELECT id FROM sessions WHERE external_session_id='aug-18'"
        ).fetchone()[0]
        conn.execute(
            """
            INSERT INTO token_usage(
                session_id, timestamp, input_tokens, cached_input_tokens,
                output_tokens, total_tokens, event_key
            ) VALUES(?, '2026-08-18T09:01:00Z', 100, NULL, 20, 120, 'tokens-aug-18')
            """,
            (aug18,),
        )

    quality = TeamAnalyticsService(
        Repository(db),
        AnalyticsFilter(
            from_date=date(2026, 8, 18),
            to_date=date(2026, 8, 18),
        ),
    ).data_quality()

    coverage = quality["source_coverage"]
    assert coverage == [
        {
            "source": "codex",
            "sessions": 1,
            "has_tokens": True,
            "has_cache": False,
            "has_cost": False,
        }
    ]
