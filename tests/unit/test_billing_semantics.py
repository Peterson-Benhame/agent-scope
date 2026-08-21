from pathlib import Path

from agentscope.analytics.filters import AnalyticsFilter
from agentscope.extension.snapshot import build_extension_snapshot
from agentscope.storage.database import Database
from agentscope.storage.repository import Repository
from agentscope.usage_context import (
    SessionUsageContext,
    persist_session_usage_context,
)


def _repo(tmp_path: Path) -> tuple[Repository, Database, dict[str, int]]:
    db = Database(tmp_path / "agentscope.db")
    db.initialize()
    repo = Repository(db)
    with db.connect() as conn:
        conn.execute("INSERT INTO sources(name, type) VALUES('codex', 'codex')")
        conn.execute("INSERT INTO projects(name, path) VALUES('demo', '/work/demo')")
        conn.execute("INSERT INTO models(provider, name) VALUES('openai', 'gpt-5.6-sol')")
        source_id = conn.execute("SELECT id FROM sources WHERE name='codex'").fetchone()[0]
        project_id = conn.execute("SELECT id FROM projects WHERE name='demo'").fetchone()[0]
        model_id = conn.execute("SELECT id FROM models WHERE name='gpt-5.6-sol'").fetchone()[0]
        ids: dict[str, int] = {}
        for external_id, hour in (("s1", 10), ("s2", 11)):
            conn.execute(
                """
                INSERT INTO sessions(
                    source_id, external_session_id, project_id, started_at, model_id
                ) VALUES(?, ?, ?, ?, ?)
                """,
                (
                    source_id,
                    external_id,
                    project_id,
                    f"2026-08-18T{hour:02d}:00:00Z",
                    model_id,
                ),
            )
            session_id = conn.execute(
                "SELECT id FROM sessions WHERE external_session_id=?",
                (external_id,),
            ).fetchone()[0]
            ids[external_id] = session_id
            conn.execute(
                """
                INSERT INTO token_usage(
                    session_id, timestamp, model_id, input_tokens,
                    cached_input_tokens, output_tokens, total_tokens, event_key
                ) VALUES(?, ?, ?, 100, 80, 20, 120, ?)
                """,
                (
                    session_id,
                    f"2026-08-18T{hour:02d}:05:00Z",
                    model_id,
                    f"token-{external_id}",
                ),
            )
    return repo, db, ids


def _snapshot(repo: Repository, db: Database) -> dict[str, object]:
    return build_extension_snapshot(
        repo,
        AnalyticsFilter(project="demo", utc_offset_minutes=0),
        period=None,
        database_path=db.path,
    )


def _context(mode: str, confidence: str = "explicit") -> SessionUsageContext:
    return SessionUsageContext(
        provider="openai",
        product="codex",
        client="vscode",
        billing_mode=mode,
        client_confidence="explicit",
        billing_confidence=confidence,
    )


def test_snapshot_marks_api_usage_as_estimated_api_cost(tmp_path):
    repo, db, ids = _repo(tmp_path)
    persist_session_usage_context(repo, ids["s1"], _context("api"))
    persist_session_usage_context(repo, ids["s2"], _context("api"))

    billing = _snapshot(repo, db)["billing"]

    assert billing == {
        "mode": "api",
        "confidence": "explicit",
        "estimated_cost_basis": "openai_api_estimate",
        "is_observed_spend": False,
    }


def test_snapshot_marks_chatgpt_plan_as_api_equivalent_not_spend(tmp_path):
    repo, db, ids = _repo(tmp_path)
    persist_session_usage_context(repo, ids["s1"], _context("chatgpt_codex_plan"))
    persist_session_usage_context(repo, ids["s2"], _context("chatgpt_codex_plan"))

    billing = _snapshot(repo, db)["billing"]

    assert billing == {
        "mode": "chatgpt_codex_plan",
        "confidence": "explicit",
        "estimated_cost_basis": "openai_api_equivalent",
        "is_observed_spend": False,
    }


def test_snapshot_keeps_unknown_billing_as_api_equivalent(tmp_path):
    repo, db, _ = _repo(tmp_path)

    billing = _snapshot(repo, db)["billing"]

    assert billing == {
        "mode": "unknown",
        "confidence": "unknown",
        "estimated_cost_basis": "openai_api_equivalent",
        "is_observed_spend": False,
    }


def test_snapshot_marks_multiple_billing_modes_as_mixed(tmp_path):
    repo, db, ids = _repo(tmp_path)
    persist_session_usage_context(repo, ids["s1"], _context("api"))
    persist_session_usage_context(repo, ids["s2"], _context("chatgpt_codex_plan"))

    billing = _snapshot(repo, db)["billing"]

    assert billing == {
        "mode": "mixed",
        "confidence": "mixed",
        "estimated_cost_basis": "openai_api_equivalent",
        "is_observed_spend": False,
    }
