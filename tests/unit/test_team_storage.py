from agentscope.storage.database import Database


def test_team_provenance_migration_is_additive_and_idempotent(tmp_path):
    db = Database(tmp_path / "agentscope.db")
    db.initialize()
    db.initialize()

    with db.connect() as conn:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        assert "team_bundles" in tables
        assert "team_event_provenance" in tables
        assert "model_pricing" in tables
        versions = [
            row[0]
            for row in conn.execute(
                "SELECT version FROM schema_migrations ORDER BY version"
            ).fetchall()
        ]
        assert versions == [1, 2, 3, 4]

        conn.execute(
            """
            INSERT INTO team_bundles(
                bundle_id, schema_version, organization, team, metadata_json
            ) VALUES('bundle-a', 1, 'Org', 'Backend', '{}')
            """
        )
        conn.execute(
            """
            INSERT INTO team_event_provenance(
                event_key, bundle_id, source, user_key, machine_key
            ) VALUES('event-a', 'bundle-a', 'codex', 'user-a', 'machine-a')
            """
        )

    db.initialize()
    with db.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM team_bundles").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM team_event_provenance").fetchone()[0] == 1
