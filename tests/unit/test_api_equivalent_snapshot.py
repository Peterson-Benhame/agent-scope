import pytest

from agentscope.analytics.filters import AnalyticsFilter
from agentscope.extension.snapshot import build_extension_snapshot
from agentscope.storage.database import Database
from agentscope.storage.repository import Repository


def test_snapshot_exposes_known_api_equivalent_and_partial_coverage(tmp_path):
    db = Database(tmp_path / "agentscope.db")
    db.initialize()
    with db.connect() as conn:
        conn.execute("INSERT INTO sources(name, type) VALUES('codex', 'agent')")
        conn.execute("INSERT INTO projects(name, path) VALUES('demo', '/work/demo')")
        conn.execute("INSERT INTO models(provider, name) VALUES('openai', 'gpt-5.6-sol')")
        source_id = conn.execute("SELECT id FROM sources WHERE name='codex'").fetchone()[0]
        project_id = conn.execute("SELECT id FROM projects WHERE name='demo'").fetchone()[0]
        model_id = conn.execute("SELECT id FROM models WHERE name='gpt-5.6-sol'").fetchone()[0]
        conn.execute(
            """
            INSERT INTO sessions(source_id, external_session_id, project_id, started_at, model_id)
            VALUES(?, 'session-a', ?, '2026-08-18T10:00:00Z', ?)
            """,
            (source_id, project_id, model_id),
        )
        session_id = conn.execute(
            "SELECT id FROM sessions WHERE external_session_id='session-a'"
        ).fetchone()[0]
        for event_key, minute in (("token-a", 1), ("token-b", 2)):
            conn.execute(
                """
                INSERT INTO token_usage(
                    session_id, timestamp, model_id, input_tokens,
                    cached_input_tokens, output_tokens, total_tokens, event_key
                ) VALUES(?, ?, ?, 100, 80, 20, 120, ?)
                """,
                (
                    session_id,
                    f"2026-08-18T10:{minute:02d}:00Z",
                    model_id,
                    event_key,
                ),
            )
        priced_usage_id = conn.execute(
            "SELECT id FROM token_usage WHERE event_key='token-a'"
        ).fetchone()[0]
        conn.execute(
            """
            INSERT INTO costs(
                session_id, model_id, period_start,
                estimated_raw_cost_usd, event_key
            ) VALUES(?, ?, '2026-08-18T10:01:00Z', 31.65021856, ?)
            """,
            (session_id, model_id, f"token_usage_cost:{priced_usage_id}"),
        )

    snapshot = build_extension_snapshot(
        Repository(db),
        AnalyticsFilter(project="demo", utc_offset_minutes=0),
        period=None,
        database_path=db.path,
    )
    summary = snapshot["summary"]

    assert summary["estimated_cost_usd"] is None
    assert summary["known_estimated_cost_usd"] == pytest.approx(31.65021856)
    assert summary["estimated_cost_events_total"] == 2
    assert summary["estimated_cost_events_priced"] == 1
    assert summary["estimated_cost_coverage"] == pytest.approx(0.5)
    assert summary["estimated_cost_complete"] is False
