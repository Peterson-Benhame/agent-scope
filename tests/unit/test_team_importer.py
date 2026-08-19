from agentscope.analytics.service import AnalyticsService
from agentscope.storage.database import Database
from agentscope.storage.repository import Repository
from agentscope.team.bundle import build_team_bundle
from agentscope.team.importer import import_team_bundle


def source_repo(tmp_path):
    db = Database(tmp_path / "source.db")
    db.initialize()
    repo = Repository(db)
    with db.connect() as conn:
        conn.execute("INSERT INTO sources(name, type) VALUES('codex', 'agent')")
        source_id = conn.execute("SELECT id FROM sources WHERE name='codex'").fetchone()[0]
        conn.execute("INSERT INTO projects(name, path) VALUES('demo', 'C:\\source\\demo')")
        project_id = conn.execute("SELECT id FROM projects WHERE name='demo'").fetchone()[0]
        conn.execute("INSERT INTO models(provider, name) VALUES('openai', 'gpt-5.6-terra')")
        model_id = conn.execute("SELECT id FROM models WHERE name='gpt-5.6-terra'").fetchone()[0]
        conn.execute(
            "INSERT INTO users(stable_key, display_name, identity_confidence) VALUES('user-a', 'Dev A', 'inferred')"
        )
        user_id = conn.execute("SELECT id FROM users WHERE stable_key='user-a'").fetchone()[0]
        conn.execute(
            "INSERT INTO machines(stable_key, display_name, os) VALUES('machine-a', 'Notebook A', 'Windows')"
        )
        machine_id = conn.execute("SELECT id FROM machines WHERE stable_key='machine-a'").fetchone()[0]
        conn.execute(
            """
            INSERT INTO sessions(
                source_id, external_session_id, project_id, started_at,
                provider, model_id, user_id, machine_id
            ) VALUES(?, 'local-session', ?, '2026-08-18T10:00:00Z', 'openai', ?, ?, ?)
            """,
            (source_id, project_id, model_id, user_id, machine_id),
        )
        session_id = conn.execute(
            "SELECT id FROM sessions WHERE external_session_id='local-session'"
        ).fetchone()[0]
        conn.execute(
            """
            INSERT INTO token_usage(
                session_id, timestamp, model_id, input_tokens, cached_input_tokens,
                output_tokens, total_tokens, event_key
            ) VALUES(?, '2026-08-18T10:01:00Z', ?, 1000, 800, 200, 1200, 'local-token-1')
            """,
            (session_id, model_id),
        )
        conn.execute(
            """
            INSERT INTO costs(
                session_id, model_id, period_start, observed_cost_usd,
                total_savings_usd, event_key
            ) VALUES(?, ?, '2026-08-18T10:00:00Z', 0.10, 0.02, 'local-cost-1')
            """,
            (session_id, model_id),
        )
    return db, repo


def target_repo(tmp_path):
    db = Database(tmp_path / "target.db")
    db.initialize()
    return db, Repository(db)


def test_import_bundle_reconstructs_safe_analytics(tmp_path):
    _, source = source_repo(tmp_path)
    target_db, target = target_repo(tmp_path)
    bundle = build_team_bundle(source, organization="Org", team="Backend")

    result = import_team_bundle(target, bundle)

    assert result.bundle_id == bundle["bundle_id"]
    assert result.sessions_imported == 1
    assert result.events_imported == 2
    assert result.errors == 0
    summary = AnalyticsService(target).summary()
    assert summary.sessions == 1
    assert summary.input_tokens == 1000
    assert summary.total_tokens == 1200
    assert summary.observed_cost_usd == 0.10
    with target_db.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM team_bundles").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM team_event_provenance").fetchone()[0] == 2


def test_reimport_same_bundle_does_not_change_totals(tmp_path):
    _, source = source_repo(tmp_path)
    target_db, target = target_repo(tmp_path)
    bundle = build_team_bundle(source)

    first = import_team_bundle(target, bundle)
    second = import_team_bundle(target, bundle)

    assert first.events_imported == 2
    assert second.events_imported == 0
    assert second.events_skipped == 2
    with target_db.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM token_usage").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM costs").fetchone()[0] == 1


def test_regenerated_overlapping_bundle_only_imports_new_event(tmp_path):
    source_db, source = source_repo(tmp_path)
    target_db, target = target_repo(tmp_path)
    first_bundle = build_team_bundle(source)
    import_team_bundle(target, first_bundle)

    with source_db.connect() as conn:
        session_id = conn.execute("SELECT id FROM sessions").fetchone()[0]
        model_id = conn.execute("SELECT id FROM models").fetchone()[0]
        conn.execute(
            """
            INSERT INTO token_usage(
                session_id, timestamp, model_id, input_tokens,
                output_tokens, total_tokens, event_key
            ) VALUES(?, '2026-08-18T10:02:00Z', ?, 500, 50, 550, 'local-token-2')
            """,
            (session_id, model_id),
        )

    second_bundle = build_team_bundle(source)
    result = import_team_bundle(target, second_bundle)

    assert second_bundle["bundle_id"] != first_bundle["bundle_id"]
    assert result.events_imported == 1
    assert result.events_skipped == 2
    with target_db.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM token_usage").fetchone()[0] == 2
        assert conn.execute("SELECT COUNT(*) FROM costs").fetchone()[0] == 1
