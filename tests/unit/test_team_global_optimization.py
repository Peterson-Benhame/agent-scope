from agentscope.analytics.team_service import TeamAnalyticsService
from agentscope.storage.database import Database
from agentscope.storage.repository import Repository
from agentscope.team.bundle import build_team_bundle
from agentscope.team.importer import import_team_bundle


def source_repo_with_global_optimization(tmp_path):
    db = Database(tmp_path / "source-global-optimization.db")
    db.initialize()
    with db.connect() as conn:
        conn.execute("INSERT INTO sources(name, type) VALUES('codex', 'agent')")
        source_id = conn.execute("SELECT id FROM sources WHERE name='codex'").fetchone()[0]
        conn.execute(
            "INSERT INTO users(stable_key, display_name, identity_confidence) "
            "VALUES('user-a', 'Dev A', 'inferred')"
        )
        user_id = conn.execute("SELECT id FROM users WHERE stable_key='user-a'").fetchone()[0]
        conn.execute(
            "INSERT INTO machines(stable_key, display_name) "
            "VALUES('machine-a', 'Notebook A')"
        )
        machine_id = conn.execute(
            "SELECT id FROM machines WHERE stable_key='machine-a'"
        ).fetchone()[0]
        conn.execute(
            """
            INSERT INTO sessions(
                source_id, external_session_id, started_at, user_id, machine_id
            ) VALUES(?, 'session-a', '2026-08-18T09:00:00Z', ?, ?)
            """,
            (source_id, user_id, machine_id),
        )
        conn.execute("INSERT INTO optimizers(name, version) VALUES('headroom', '0.35.0')")
        optimizer_id = conn.execute(
            "SELECT id FROM optimizers WHERE name='headroom'"
        ).fetchone()[0]
        conn.execute(
            """
            INSERT INTO optimizations(
                optimizer_id, session_id, timestamp,
                original_tokens, optimized_tokens, tokens_saved,
                compression_savings_usd, cache_savings_usd,
                correlation_confidence, event_key
            ) VALUES(
                ?, NULL, '2026-08-18T09:10:00Z',
                1000, 800, 200, 1.25, 2.75,
                'unknown', 'global-headroom-event'
            )
            """,
            (optimizer_id,),
        )
    return Repository(db)


def test_team_bundle_preserves_uncorrelated_optimizer_event(tmp_path):
    bundle = build_team_bundle(source_repo_with_global_optimization(tmp_path))

    assert len(bundle["records"]["optimizations"]) == 1
    optimization = bundle["records"]["optimizations"][0]
    assert optimization["session_key"] is None
    assert optimization["optimizer"] == "headroom"
    assert optimization["compression_savings_usd"] == 1.25
    assert optimization["cache_savings_usd"] == 2.75


def test_team_import_preserves_global_savings_without_user_attribution(tmp_path):
    bundle = build_team_bundle(source_repo_with_global_optimization(tmp_path))
    target_db = Database(tmp_path / "team-global-optimization.db")
    target_db.initialize()
    target = Repository(target_db)

    result = import_team_bundle(target, bundle)

    assert result.events_imported == 1
    with target_db.connect() as conn:
        row = conn.execute(
            "SELECT session_id, compression_savings_usd, cache_savings_usd "
            "FROM optimizations"
        ).fetchone()
        assert row["session_id"] is None
        assert row["compression_savings_usd"] == 1.25
        assert row["cache_savings_usd"] == 2.75

    analytics = TeamAnalyticsService(target)
    assert analytics.summary().total_savings_usd == 4.0
    assert analytics.savings_by_user() == []
