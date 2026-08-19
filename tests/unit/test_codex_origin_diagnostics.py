import json
from datetime import date

from agentscope.analytics.filters import AnalyticsFilter
from agentscope.diagnostics.codex_origin import (
    CodexOriginDiagnostics,
    classify_codex_client,
)
from agentscope.storage.database import Database
from agentscope.storage.repository import Repository


def _repo(tmp_path):
    db = Database(tmp_path / "agentscope.db")
    db.initialize()
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
    return Repository(db), db


def _ids(db):
    with db.connect() as conn:
        return {
            "source": conn.execute("SELECT id FROM sources WHERE name='codex'").fetchone()[0],
            "project": conn.execute("SELECT id FROM projects WHERE name='Project A'").fetchone()[0],
            "model": conn.execute("SELECT id FROM models WHERE name='gpt-5.6-sol'").fetchone()[0],
            "user": conn.execute("SELECT id FROM users WHERE display_name='Dev A'").fetchone()[0],
            "machine": conn.execute("SELECT id FROM machines WHERE display_name='Notebook A'").fetchone()[0],
        }


def _insert_session(
    db,
    *,
    external_id,
    started_at,
    activity_at,
    originator=None,
    metadata_source=None,
    thread_source=None,
    total_tokens=100,
):
    ids = _ids(db)
    metadata = json.dumps(
        {"source": metadata_source, "thread_source": thread_source},
        ensure_ascii=False,
    )
    with db.connect() as conn:
        conn.execute(
            """
            INSERT INTO sessions(
                source_id, external_session_id, project_id, started_at,
                originator, provider, model_id, metadata_json, user_id, machine_id
            ) VALUES(?, ?, ?, ?, ?, 'openai', ?, ?, ?, ?)
            """,
            (
                ids["source"], external_id, ids["project"], started_at,
                originator, ids["model"], metadata, ids["user"], ids["machine"],
            ),
        )
        session_id = conn.execute(
            "SELECT id FROM sessions WHERE external_session_id=?",
            (external_id,),
        ).fetchone()[0]
        conn.execute(
            """
            INSERT INTO token_usage(
                session_id, timestamp, model_id, input_tokens,
                cached_input_tokens, output_tokens, total_tokens, event_key
            ) VALUES(?, ?, ?, ?, 0, 0, ?, ?)
            """,
            (
                session_id,
                activity_at,
                ids["model"],
                total_tokens,
                total_tokens,
                f"token-{external_id}",
            ),
        )


def test_classify_codex_client_uses_only_explicit_metadata_evidence():
    vscode = classify_codex_client(
        originator="codex_vscode",
        metadata_source="vscode",
        thread_source=None,
    )
    cli = classify_codex_client(
        originator="codex_cli",
        metadata_source="cli",
        thread_source=None,
    )
    unknown = classify_codex_client(
        originator="codex",
        metadata_source="local",
        thread_source="agent",
    )

    assert vscode.client == "vscode"
    assert "originator=codex_vscode" in vscode.evidence
    assert cli.client == "cli"
    assert unknown.client == "unknown"
    assert unknown.evidence == ()


def test_diagnostics_attributes_tokens_to_client_and_keeps_raw_evidence(tmp_path):
    repo, db = _repo(tmp_path)
    _insert_session(
        db,
        external_id="vscode-session",
        started_at="2026-08-19T09:00:00Z",
        activity_at="2026-08-19T09:10:00Z",
        originator="codex_vscode",
        metadata_source="vscode",
        total_tokens=700,
    )
    _insert_session(
        db,
        external_id="unknown-session",
        started_at="2026-08-19T10:00:00Z",
        activity_at="2026-08-19T10:10:00Z",
        originator="codex",
        metadata_source="local",
        thread_source="agent",
        total_tokens=300,
    )

    payload = CodexOriginDiagnostics(repo).inspect()

    assert payload["summary"] == {
        "sessions": 2,
        "total_tokens": 1000,
        "unclassified_sessions": 1,
        "clients": [
            {"client": "vscode", "sessions": 1, "total_tokens": 700},
            {"client": "unknown", "sessions": 1, "total_tokens": 300},
        ],
    }
    first = payload["sessions"][0]
    assert first["external_session_id"] == "vscode-session"
    assert first["originator"] == "codex_vscode"
    assert first["metadata_source"] == "vscode"
    assert first["client"] == "vscode"
    assert first["total_tokens"] == 700
    assert first["models"] == ["gpt-5.6-sol"]


def test_period_filter_uses_token_activity_not_only_session_start(tmp_path):
    repo, db = _repo(tmp_path)
    _insert_session(
        db,
        external_id="cross-day",
        started_at="2026-08-18T23:50:00Z",
        activity_at="2026-08-19T00:10:00Z",
        originator="codex_vscode",
        metadata_source="vscode",
        total_tokens=500,
    )
    filters = AnalyticsFilter(
        from_date=date(2026, 8, 19),
        to_date=date(2026, 8, 19),
        user="Dev A",
        machine="Notebook A",
    )

    payload = CodexOriginDiagnostics(repo, filters).inspect()

    assert payload["summary"]["sessions"] == 1
    assert payload["summary"]["total_tokens"] == 500
    assert payload["sessions"][0]["last_activity_at"] == "2026-08-19T00:10:00Z"
