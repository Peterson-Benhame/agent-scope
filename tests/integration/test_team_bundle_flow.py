import json

from agentscope.storage.database import Database
from agentscope.storage.repository import Repository
from agentscope.team.bundle import build_team_bundle
from agentscope.team.importer import import_team_bundle


SENTINELS = (
    "TEAM_FLOW_PROMPT_SECRET",
    "TEAM_FLOW_RESPONSE_SECRET",
    "TEAM_FLOW_TOOL_PAYLOAD_SECRET",
    r"C:\work\sensitive-project",
)


def source_repository(path):
    db = Database(path)
    db.initialize()
    with db.connect() as conn:
        conn.execute("INSERT INTO sources(name, type) VALUES('codex', 'agent')")
        source_id = conn.execute("SELECT id FROM sources WHERE name='codex'").fetchone()[0]
        conn.execute(
            "INSERT INTO projects(name, path) VALUES('SensitiveProject', ?)",
            (r"C:\work\sensitive-project",),
        )
        project_id = conn.execute(
            "SELECT id FROM projects WHERE name='SensitiveProject'"
        ).fetchone()[0]
        conn.execute(
            """
            INSERT INTO users(stable_key, display_name, identity_confidence)
            VALUES('user-team-flow', 'Dev Flow', 'inferred')
            """
        )
        user_id = conn.execute(
            "SELECT id FROM users WHERE stable_key='user-team-flow'"
        ).fetchone()[0]
        conn.execute(
            """
            INSERT INTO machines(stable_key, display_name, os)
            VALUES('machine-team-flow', 'Notebook Flow', 'Windows')
            """
        )
        machine_id = conn.execute(
            "SELECT id FROM machines WHERE stable_key='machine-team-flow'"
        ).fetchone()[0]
        conn.execute(
            """
            INSERT INTO sessions(
                source_id, external_session_id, project_id, started_at,
                user_id, machine_id, raw_file_path, metadata_json
            ) VALUES(?, 'session-team-flow', ?, '2026-08-18T10:00:00Z', ?, ?, ?, ?)
            """,
            (
                source_id,
                project_id,
                user_id,
                machine_id,
                r"C:\work\sensitive-project\.codex\rollout.jsonl",
                json.dumps({"secret": "TEAM_FLOW_TOOL_PAYLOAD_SECRET"}),
            ),
        )
        session_id = conn.execute(
            "SELECT id FROM sessions WHERE external_session_id='session-team-flow'"
        ).fetchone()[0]
        conn.execute(
            """
            INSERT INTO messages(session_id, role, timestamp, content, event_key)
            VALUES(?, 'user', '2026-08-18T10:00:01Z', ?, 'message-secret')
            """,
            (session_id, "TEAM_FLOW_PROMPT_SECRET"),
        )
        conn.execute(
            """
            INSERT INTO messages(session_id, role, timestamp, content, event_key)
            VALUES(?, 'assistant', '2026-08-18T10:00:02Z', ?, 'message-response')
            """,
            (session_id, "TEAM_FLOW_RESPONSE_SECRET"),
        )
        conn.execute(
            """
            INSERT INTO token_usage(
                session_id, timestamp, input_tokens, cached_input_tokens,
                output_tokens, total_tokens, source_file, event_key
            ) VALUES(?, '2026-08-18T10:00:03Z', 1000, 700, 200, 1200, ?, 'token-1')
            """,
            (session_id, r"C:\work\sensitive-project\rollout.jsonl"),
        )
    return Repository(db)


def test_team_bundle_end_to_end_is_private_and_idempotent(tmp_path):
    source = source_repository(tmp_path / "source.db")
    target_db = Database(tmp_path / "team.db")
    target_db.initialize()
    target = Repository(target_db)

    first_bundle = build_team_bundle(source, organization="Org", team="Backend")
    serialized = json.dumps(first_bundle, ensure_ascii=False, sort_keys=True).encode("utf-8")

    for sentinel in SENTINELS:
        assert sentinel.encode("utf-8") not in serialized

    first = import_team_bundle(target, first_bundle)
    assert first.sessions_imported == 1
    assert first.events_imported == 1
    assert first.events_skipped == 0

    with target_db.connect() as conn:
        totals_before = (
            conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0],
            conn.execute("SELECT COUNT(*) FROM token_usage").fetchone()[0],
            conn.execute(
                "SELECT COALESCE(SUM(total_tokens), 0) FROM token_usage"
            ).fetchone()[0],
        )

    repeated = import_team_bundle(target, first_bundle)
    assert repeated.sessions_imported == 0
    assert repeated.events_imported == 0
    assert repeated.events_skipped == 1

    with source.database.connect() as conn:
        session_id = conn.execute(
            "SELECT id FROM sessions WHERE external_session_id='session-team-flow'"
        ).fetchone()[0]
        conn.execute(
            """
            INSERT INTO token_usage(
                session_id, timestamp, input_tokens, output_tokens,
                total_tokens, event_key
            ) VALUES(?, '2026-08-18T10:05:00Z', 500, 100, 600, 'token-2')
            """,
            (session_id,),
        )

    second_bundle = build_team_bundle(source, organization="Org", team="Backend")
    assert second_bundle["bundle_id"] != first_bundle["bundle_id"]

    incremental = import_team_bundle(target, second_bundle)
    assert incremental.sessions_imported == 0
    assert incremental.events_imported == 1
    assert incremental.events_skipped == 1

    with target_db.connect() as conn:
        totals_after = (
            conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0],
            conn.execute("SELECT COUNT(*) FROM token_usage").fetchone()[0],
            conn.execute(
                "SELECT COALESCE(SUM(total_tokens), 0) FROM token_usage"
            ).fetchone()[0],
        )

    assert totals_before == (1, 1, 1200)
    assert totals_after == (1, 2, 1800)
