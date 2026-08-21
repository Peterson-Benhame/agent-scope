from __future__ import annotations

from datetime import date

from agentscope.codex_account.collector import (
    LocalCodexThread,
    select_local_codex_threads,
    sync_thread_usage,
)
from agentscope.storage.database import Database
from agentscope.storage.repository import Repository


THREAD_ID = "01a016bf-d4e0-7383-9c3d-872eeeb5c5fa"


class ThreadUsageClient:
    def account_usage_read(self, thread_id: str | None = None):
        assert thread_id == THREAD_ID
        return {
            "threadUsage": {
                "threadId": THREAD_ID,
                "estimatedUsageCreditsMicros": 1250000,
                "estimatedUsageUsdMicros": 490000,
                "groups": [
                    {
                        "model": "gpt-5.3-codex",
                        "reasoningEffort": "high",
                        "speed": "standard",
                        "estimatedUsageCreditsMicros": 1250000,
                        "netNewInputTokens": 2700,
                        "cachedInputTokens": 19200,
                        "inputTokens": 21900,
                        "outputTokens": 90,
                        "totalTokens": 21990,
                    }
                ],
            }
        }


def _repo_with_sessions(tmp_path):
    db = Database(tmp_path / "agentscope.db")
    db.initialize()
    with db.connect() as conn:
        conn.execute("INSERT INTO sources(name, type) VALUES('codex', 'agent')")
        conn.execute("INSERT INTO sources(name, type) VALUES('kimi', 'agent')")
        codex_id = conn.execute("SELECT id FROM sources WHERE name='codex'").fetchone()[0]
        kimi_id = conn.execute("SELECT id FROM sources WHERE name='kimi'").fetchone()[0]
        conn.execute("INSERT INTO models(provider, name) VALUES('openai', 'codex-auto-review')")
        model_id = conn.execute("SELECT id FROM models WHERE name='codex-auto-review'").fetchone()[0]
        conn.execute(
            """
            INSERT INTO sessions(source_id, external_session_id, started_at, model_id, raw_file_path)
            VALUES(?, ?, '2026-08-18T21:21:05Z', ?, 'exact-rollout.jsonl')
            """,
            (codex_id, THREAD_ID, model_id),
        )
        exact_session = conn.execute(
            "SELECT id FROM sessions WHERE source_id=? AND external_session_id=?",
            (codex_id, THREAD_ID),
        ).fetchone()[0]
        conn.execute(
            """
            INSERT INTO sessions(source_id, external_session_id, started_at, model_id, raw_file_path)
            VALUES(?, 'different-thread', '2026-08-18T21:21:05Z', ?, ?)
            """,
            (codex_id, model_id, f"rollout-{THREAD_ID}.jsonl"),
        )
        conn.execute(
            """
            INSERT INTO sessions(source_id, external_session_id, started_at, model_id)
            VALUES(?, ?, '2026-08-18T21:21:05Z', ?)
            """,
            (kimi_id, THREAD_ID, model_id),
        )
        conn.execute(
            """
            INSERT INTO token_usage(
                session_id, timestamp, model_id, input_tokens, cached_input_tokens,
                output_tokens, total_tokens, event_key
            ) VALUES(?, '2026-08-18T21:21:12Z', ?, 20031, 4864, 155, 20186, 'review-token')
            """,
            (exact_session, model_id),
        )
    return Repository(db), exact_session


def test_select_local_threads_uses_exact_codex_external_id_not_filename(tmp_path):
    repo, exact_session = _repo_with_sessions(tmp_path)
    threads = select_local_codex_threads(
        repo,
        date(2026, 8, 18),
        date(2026, 8, 18),
        utc_offset_minutes=0,
    )

    assert LocalCodexThread(
        thread_id=THREAD_ID,
        session_id=exact_session,
        started_at="2026-08-18T21:21:05Z",
    ) in threads
    assert all(thread.thread_id != "different-thread" or thread.session_id != exact_session for thread in threads)
    assert sum(thread.thread_id == THREAD_ID for thread in threads) == 1


def test_sync_thread_usage_persists_backend_model_without_rewriting_raw_model(tmp_path):
    repo, exact_session = _repo_with_sessions(tmp_path)
    summary = sync_thread_usage(
        repo,
        client=ThreadUsageClient(),
        thread_ids=[
            LocalCodexThread(
                thread_id=THREAD_ID,
                session_id=exact_session,
                started_at="2026-08-18T21:21:05Z",
            )
        ],
    )

    assert summary.threads_requested == 1
    assert summary.threads_synced == 1
    assert summary.threads_unavailable == 0
    assert summary.thread_usage_supported is True

    with repo.database.connect() as conn:
        snapshot = conn.execute(
            "SELECT * FROM codex_thread_usage_snapshots WHERE thread_id=?",
            (THREAD_ID,),
        ).fetchone()
        groups = conn.execute(
            """
            SELECT g.* FROM codex_thread_usage_groups g
            WHERE g.thread_usage_snapshot_id=?
            """,
            (snapshot["id"],),
        ).fetchall()
        raw_model = conn.execute(
            """
            SELECT m.name FROM token_usage tu
            JOIN models m ON m.id=tu.model_id
            WHERE tu.event_key='review-token'
            """
        ).fetchone()[0]

    assert snapshot["session_id"] == exact_session
    assert snapshot["estimated_usage_credits_micros"] == 1250000
    assert snapshot["estimated_usage_usd_micros"] == 490000
    assert snapshot["billing_route_available"] == 1
    assert len(groups) == 1
    assert groups[0]["model"] == "gpt-5.3-codex"
    assert groups[0]["cached_input_tokens"] == 19200
    assert groups[0]["output_tokens"] == 90
    assert raw_model == "codex-auto-review"


def test_sync_thread_usage_preserves_multiple_backend_model_groups(tmp_path):
    repo, exact_session = _repo_with_sessions(tmp_path)

    class MultiClient(ThreadUsageClient):
        def account_usage_read(self, thread_id=None):
            payload = super().account_usage_read(thread_id)
            payload["threadUsage"]["groups"].append(
                {
                    "model": "gpt-5.6-luna",
                    "reasoningEffort": "low",
                    "speed": "standard",
                    "estimatedUsageCreditsMicros": 100000,
                    "inputTokens": 1000,
                    "cachedInputTokens": 500,
                    "outputTokens": 50,
                    "totalTokens": 1050,
                }
            )
            return payload

    sync_thread_usage(
        repo,
        client=MultiClient(),
        thread_ids=[LocalCodexThread(THREAD_ID, exact_session, "2026-08-18T21:21:05Z")],
    )
    with repo.database.connect() as conn:
        models = [
            row[0]
            for row in conn.execute(
                """
                SELECT g.model FROM codex_thread_usage_groups g
                JOIN codex_thread_usage_snapshots s ON s.id=g.thread_usage_snapshot_id
                WHERE s.thread_id=? ORDER BY g.id
                """,
                (THREAD_ID,),
            )
        ]
    assert models == ["gpt-5.3-codex", "gpt-5.6-luna"]


def test_unavailable_thread_billing_route_stays_null(tmp_path):
    repo, exact_session = _repo_with_sessions(tmp_path)

    class UnavailableClient:
        def account_usage_read(self, thread_id=None):
            return {"threadUsage": None}

    summary = sync_thread_usage(
        repo,
        client=UnavailableClient(),
        thread_ids=[LocalCodexThread(THREAD_ID, exact_session, "2026-08-18T21:21:05Z")],
    )
    assert summary.threads_unavailable == 1
    with repo.database.connect() as conn:
        row = conn.execute(
            "SELECT * FROM codex_thread_usage_snapshots WHERE thread_id=?",
            (THREAD_ID,),
        ).fetchone()
    assert row["billing_route_available"] == 0
    assert row["estimated_usage_credits_micros"] is None
    assert row["estimated_usage_usd_micros"] is None


def test_unsupported_thread_usage_marks_all_unavailable_without_rpc_calls(tmp_path):
    repo, exact_session = _repo_with_sessions(tmp_path)

    class MustNotCallClient:
        def account_usage_read(self, thread_id=None):
            raise AssertionError("thread usage RPC must not be called")

    summary = sync_thread_usage(
        repo,
        client=MustNotCallClient(),
        thread_ids=[LocalCodexThread(THREAD_ID, exact_session, "2026-08-18T21:21:05Z")],
        thread_usage_supported=False,
    )

    assert summary.thread_usage_supported is False
    assert summary.threads_requested == 1
    assert summary.threads_synced == 0
    assert summary.threads_unavailable == 1
    assert summary.errors == 0
