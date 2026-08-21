import json

from agentscope.storage.database import Database
from agentscope.storage.repository import Repository
from agentscope.usage_context_backfill import backfill_usage_context


def _repo(tmp_path):
    db = Database(tmp_path / "agentscope.db")
    db.initialize()
    repo = Repository(db)
    with db.connect() as conn:
        conn.execute("INSERT INTO sources(name, type) VALUES('codex', 'codex')")
        conn.execute("INSERT INTO sources(name, type) VALUES('kimi', 'kimi')")
        codex_id = conn.execute("SELECT id FROM sources WHERE name='codex'").fetchone()[0]
        kimi_id = conn.execute("SELECT id FROM sources WHERE name='kimi'").fetchone()[0]
        conn.execute(
            """
            INSERT INTO sessions(
                source_id, external_session_id, started_at, originator,
                provider, metadata_json
            ) VALUES(?, 'vscode-session', '2026-08-18T20:00:00Z',
                     'codex_vscode', 'headroom', ?)
            """,
            (
                codex_id,
                json.dumps({"source": "vscode", "thread_source": "user"}),
            ),
        )
        conn.execute(
            """
            INSERT INTO sessions(
                source_id, external_session_id, started_at, originator,
                provider, metadata_json
            ) VALUES(?, 'cli-api-session', '2026-08-18T21:00:00Z',
                     'codex_cli', 'openai', ?)
            """,
            (
                codex_id,
                json.dumps({"source": "cli", "billing_mode": "api"}),
            ),
        )
        conn.execute(
            """
            INSERT INTO sessions(
                source_id, external_session_id, started_at, originator,
                provider, metadata_json
            ) VALUES(?, 'kimi-session', '2026-08-18T22:00:00Z',
                     'kimi_cli', 'kimi', '{}')
            """,
            (kimi_id,),
        )
    return db, repo


def test_backfill_persists_historical_codex_context_without_rescanning_files(tmp_path):
    db, repo = _repo(tmp_path)

    summary = backfill_usage_context(repo, sources=frozenset({"codex"}))

    assert summary.sessions_scanned == 2
    assert summary.sessions_updated == 2
    assert summary.sessions_existing == 0
    assert summary.clients == {"cli": 1, "vscode": 1}
    assert summary.billing_modes == {"api": 1, "unknown": 1}
    assert summary.errors == 0

    with db.connect() as conn:
        rows = conn.execute(
            """
            SELECT s.external_session_id, uc.provider, uc.product, uc.client,
                   uc.billing_mode, uc.client_confidence, uc.billing_confidence,
                   uc.evidence_json, uc.metadata_json
            FROM session_usage_context uc
            JOIN sessions s ON s.id=uc.session_id
            ORDER BY s.external_session_id
            """
        ).fetchall()

    assert len(rows) == 2
    api = rows[0]
    assert api["external_session_id"] == "cli-api-session"
    assert api["provider"] == "openai"
    assert api["product"] == "codex"
    assert api["client"] == "cli"
    assert api["billing_mode"] == "api"
    assert api["client_confidence"] == "explicit"
    assert api["billing_confidence"] == "explicit"

    vscode = rows[1]
    assert vscode["external_session_id"] == "vscode-session"
    assert vscode["client"] == "vscode"
    assert vscode["billing_mode"] == "unknown"
    assert json.loads(vscode["metadata_json"])["model_provider"] == "headroom"


def test_backfill_is_idempotent_and_reports_existing_contexts(tmp_path):
    db, repo = _repo(tmp_path)

    first = backfill_usage_context(repo, sources=frozenset({"codex"}))
    second = backfill_usage_context(repo, sources=frozenset({"codex"}))

    assert first.sessions_updated == 2
    assert second.sessions_scanned == 2
    assert second.sessions_updated == 0
    assert second.sessions_existing == 2
    assert second.clients == {"cli": 1, "vscode": 1}
    assert second.billing_modes == {"api": 1, "unknown": 1}
    assert second.errors == 0
    with db.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM session_usage_context").fetchone()[0] == 2
        assert conn.execute(
            """
            SELECT COUNT(*)
            FROM session_usage_context uc
            JOIN sessions s ON s.id=uc.session_id
            JOIN sources src ON src.id=s.source_id
            WHERE src.name='kimi'
            """
        ).fetchone()[0] == 0
