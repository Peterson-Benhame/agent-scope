import json
from pathlib import Path

from agentscope.analytics.filters import AnalyticsFilter
from agentscope.extension.snapshot import build_extension_snapshot
from agentscope.storage.database import Database
from agentscope.storage.repository import Repository


def make_repo(tmp_path: Path) -> tuple[Repository, Database]:
    db = Database(tmp_path / "agentscope.db")
    db.initialize()
    with db.connect() as conn:
        conn.execute("INSERT INTO sources(name, type) VALUES('codex', 'agent')")
        source_id = conn.execute("SELECT id FROM sources WHERE name='codex'").fetchone()[0]
        conn.execute("INSERT INTO projects(name, path) VALUES('example-project', 'example-project')")
        project_id = conn.execute("SELECT id FROM projects WHERE name='example-project'").fetchone()[0]
        conn.execute("INSERT INTO projects(name, path) VALUES('no-cost-project', 'no-cost-project')")
        no_cost_project_id = conn.execute("SELECT id FROM projects WHERE name='no-cost-project'").fetchone()[0]
        conn.execute("INSERT INTO models(provider, name) VALUES('openai', 'gpt-example')")
        model_id = conn.execute("SELECT id FROM models WHERE name='gpt-example'").fetchone()[0]
        conn.execute(
            "INSERT INTO users(stable_key, display_name, identity_confidence) VALUES('user-a', 'Dev A', 'inferred')"
        )
        user_id = conn.execute("SELECT id FROM users WHERE stable_key='user-a'").fetchone()[0]
        conn.execute(
            "INSERT INTO machines(stable_key, display_name) VALUES('machine-a', 'Notebook A')"
        )
        machine_id = conn.execute("SELECT id FROM machines WHERE stable_key='machine-a'").fetchone()[0]
        conn.execute(
            """
            INSERT INTO sessions(
                source_id, external_session_id, project_id, started_at, model_id,
                raw_file_path, user_id, machine_id
            ) VALUES(?, 'session-a', ?, '2026-08-18T10:00:00Z', ?, ?, ?, ?)
            """,
            (source_id, project_id, model_id, r"C:\private\provider\rollout.jsonl", user_id, machine_id),
        )
        session_id = conn.execute("SELECT id FROM sessions WHERE external_session_id='session-a'").fetchone()[0]
        conn.execute(
            """
            INSERT INTO token_usage(
                session_id, timestamp, model_id, input_tokens, cached_input_tokens,
                output_tokens, total_tokens, event_key
            ) VALUES(?, '2026-08-18T10:01:00Z', ?, 100, 40, 50, 150, 'token-a')
            """,
            (session_id, model_id),
        )
        conn.execute(
            """
            INSERT INTO costs(
                session_id, model_id, period_start, observed_cost_usd,
                total_savings_usd, event_key
            ) VALUES(?, ?, '2026-08-18T10:00:00Z', 0.12, 0.03, 'cost-a')
            """,
            (session_id, model_id),
        )
        conn.execute(
            """
            INSERT INTO messages(session_id, role, timestamp, content, event_key)
            VALUES(?, 'user', '2026-08-18T10:00:30Z', 'PRIVATE_PROMPT_SENTINEL', 'message-a')
            """,
            (session_id,),
        )
        conn.execute(
            """
            INSERT INTO sessions(
                source_id, external_session_id, project_id, started_at, model_id,
                user_id, machine_id
            ) VALUES(?, 'session-b', ?, '2026-08-18T11:00:00Z', ?, ?, ?)
            """,
            (source_id, no_cost_project_id, model_id, user_id, machine_id),
        )
        session_b = conn.execute("SELECT id FROM sessions WHERE external_session_id='session-b'").fetchone()[0]
        conn.execute(
            """
            INSERT INTO token_usage(
                session_id, timestamp, model_id, input_tokens, cached_input_tokens,
                output_tokens, total_tokens, event_key
            ) VALUES(?, '2026-08-18T11:01:00Z', ?, 10, 0, 5, 15, 'token-b')
            """,
            (session_b, model_id),
        )
    return Repository(db), db


def test_build_extension_snapshot_has_stable_allow_listed_contract(tmp_path):
    repo, db = make_repo(tmp_path)
    snapshot = build_extension_snapshot(
        repo,
        AnalyticsFilter(project="example-project"),
        period=None,
        database_path=db.path,
    )

    assert snapshot["schema"] == "agentscope-extension-snapshot"
    assert snapshot["version"] == 1
    assert snapshot["summary"]["sessions"] == 1
    assert snapshot["summary"]["total_tokens"] == 150
    assert snapshot["summary"]["observed_cost_usd"] == 0.12
    assert "example-project" in snapshot["dimensions"]["projects"]
    assert "codex" in snapshot["dimensions"]["sources"]

    serialized = json.dumps(snapshot, ensure_ascii=False)
    assert "PRIVATE_PROMPT_SENTINEL" not in serialized
    assert r"C:\private\provider\rollout.jsonl" not in serialized


def test_extension_snapshot_keeps_unknown_cost_null(tmp_path):
    repo, db = make_repo(tmp_path)
    snapshot = build_extension_snapshot(
        repo,
        AnalyticsFilter(project="no-cost-project"),
        period=None,
        database_path=db.path,
    )

    assert snapshot["summary"]["sessions"] == 1
    assert snapshot["summary"]["observed_cost_usd"] is None
