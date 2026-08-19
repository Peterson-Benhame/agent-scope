from agentscope.analytics.team_service import TeamAnalyticsService
from agentscope.storage.database import Database
from agentscope.storage.repository import Repository


def test_team_summary_combines_cost_savings_and_optimizer_fallback_per_session(tmp_path):
    db = Database(tmp_path / "team-savings.db")
    db.initialize()
    with db.connect() as conn:
        conn.execute("INSERT INTO sources(name, type) VALUES('codex', 'agent')")
        source_id = conn.execute("SELECT id FROM sources WHERE name='codex'").fetchone()[0]
        conn.execute("INSERT INTO models(provider, name) VALUES('test', 'model')")
        model_id = conn.execute("SELECT id FROM models WHERE name='model'").fetchone()[0]
        conn.execute(
            "INSERT INTO users(stable_key, display_name, identity_confidence) VALUES('u1', 'Dev 1', 'inferred')"
        )
        conn.execute(
            "INSERT INTO users(stable_key, display_name, identity_confidence) VALUES('u2', 'Dev 2', 'inferred')"
        )
        conn.execute("INSERT INTO machines(stable_key, display_name) VALUES('m1', 'Machine 1')")
        conn.execute("INSERT INTO machines(stable_key, display_name) VALUES('m2', 'Machine 2')")
        u1 = conn.execute("SELECT id FROM users WHERE stable_key='u1'").fetchone()[0]
        u2 = conn.execute("SELECT id FROM users WHERE stable_key='u2'").fetchone()[0]
        m1 = conn.execute("SELECT id FROM machines WHERE stable_key='m1'").fetchone()[0]
        m2 = conn.execute("SELECT id FROM machines WHERE stable_key='m2'").fetchone()[0]
        conn.execute(
            """
            INSERT INTO sessions(source_id, external_session_id, started_at, model_id, user_id, machine_id)
            VALUES(?, 's1', '2026-08-18T09:00:00Z', ?, ?, ?)
            """,
            (source_id, model_id, u1, m1),
        )
        conn.execute(
            """
            INSERT INTO sessions(source_id, external_session_id, started_at, model_id, user_id, machine_id)
            VALUES(?, 's2', '2026-08-18T10:00:00Z', ?, ?, ?)
            """,
            (source_id, model_id, u2, m2),
        )
        s1 = conn.execute("SELECT id FROM sessions WHERE external_session_id='s1'").fetchone()[0]
        s2 = conn.execute("SELECT id FROM sessions WHERE external_session_id='s2'").fetchone()[0]
        conn.execute(
            """
            INSERT INTO costs(session_id, model_id, period_start, total_savings_usd, event_key)
            VALUES(?, ?, '2026-08-18T09:00:00Z', 1.5, 'cost-savings')
            """,
            (s1, model_id),
        )
        conn.execute("INSERT INTO optimizers(name, version) VALUES('headroom', 'test')")
        optimizer_id = conn.execute("SELECT id FROM optimizers WHERE name='headroom'").fetchone()[0]
        conn.execute(
            """
            INSERT INTO optimizations(
                optimizer_id, session_id, timestamp, model_id,
                compression_savings_usd, cache_savings_usd,
                correlation_confidence, event_key
            ) VALUES(?, ?, '2026-08-18T10:00:00Z', ?, 2.0, 3.0, 'exact', 'optimizer-savings')
            """,
            (optimizer_id, s2, model_id),
        )

    summary = TeamAnalyticsService(Repository(db)).summary()

    assert summary.total_savings_usd == 6.5
