from __future__ import annotations

import json

from agentscope.codex_account.attribution import attribute_thread_billing
from agentscope.codex_account.models import (
    AttributionConfidence,
    BillingSource,
    CodexAccountSnapshot,
    CodexThreadUsageSnapshot,
)
from agentscope.codex_account.storage import CodexAccountStorage
from agentscope.storage.database import Database
from agentscope.storage.repository import Repository


THREAD_ID = "01a016b9-605d-7ef2-87c4-d8da231b547c"


def _repo_with_target_thread(tmp_path):
    db = Database(tmp_path / "agentscope.db")
    db.initialize()
    with db.connect() as conn:
        conn.execute("INSERT INTO sources(name, type) VALUES('codex', 'agent')")
        source_id = conn.execute(
            "SELECT id FROM sources WHERE name='codex'"
        ).fetchone()[0]
        conn.execute(
            """
            INSERT INTO sessions(
                source_id, external_session_id, started_at, ended_at
            ) VALUES(?, ?, ?, ?)
            """,
            (
                source_id,
                THREAD_ID,
                "2026-08-20T10:00:00+00:00",
                "2026-08-20T10:10:00+00:00",
            ),
        )
        session_id = conn.execute(
            "SELECT id FROM sessions WHERE external_session_id=?",
            (THREAD_ID,),
        ).fetchone()[0]
        conn.execute(
            """
            INSERT INTO token_usage(
                session_id, timestamp, total_tokens, event_key
            ) VALUES(?, ?, ?, ?)
            """,
            (
                session_id,
                "2026-08-20T10:09:30+00:00",
                42000,
                "target-token",
            ),
        )
    repo = Repository(db)
    storage = CodexAccountStorage(db)
    thread_snapshot_id = storage.insert_thread_usage_snapshot(
        CodexThreadUsageSnapshot(
            captured_at="2026-08-20T10:12:00+00:00",
            thread_id=THREAD_ID,
            session_id=session_id,
            estimated_usage_credits_micros=1_250_000,
            estimated_usage_usd_micros=490_000,
        )
    )
    return repo, storage, thread_snapshot_id, session_id


def _insert_bracket(
    storage: CodexAccountStorage,
    *,
    pre_balance: str,
    post_balance: str,
    pre_primary: int = 40,
    post_primary: int = 40,
):
    pre_id = storage.insert_account_snapshot(
        CodexAccountSnapshot(
            captured_at="2026-08-20T09:59:00+00:00",
            auth_mode="chatgpt",
            plan_type="prolite",
            primary_used_percent=pre_primary,
            credits_balance=pre_balance,
        )
    )
    post_id = storage.insert_account_snapshot(
        CodexAccountSnapshot(
            captured_at="2026-08-20T10:11:00+00:00",
            auth_mode="chatgpt",
            plan_type="prolite",
            primary_used_percent=post_primary,
            credits_balance=post_balance,
        )
    )
    return pre_id, post_id


def _stored_thread_row(repo: Repository, snapshot_id: int):
    with repo.database.connect() as conn:
        return conn.execute(
            "SELECT * FROM codex_thread_usage_snapshots WHERE id=?",
            (snapshot_id,),
        ).fetchone()


def test_no_bracketing_snapshots_stays_unknown(tmp_path):
    repo, _, snapshot_id, _ = _repo_with_target_thread(tmp_path)

    attribution = attribute_thread_billing(repo, snapshot_id)

    assert attribution.billing_source is BillingSource.UNKNOWN
    assert attribution.confidence is AttributionConfidence.UNKNOWN
    assert attribution.pre_snapshot_id is None
    assert attribution.post_snapshot_id is None
    stored = _stored_thread_row(repo, snapshot_id)
    assert stored["billing_source"] == "unknown"
    assert stored["attribution_confidence"] == "unknown"


def test_isolated_credit_balance_drop_is_additional_credits_high_confidence(tmp_path):
    repo, storage, snapshot_id, _ = _repo_with_target_thread(tmp_path)
    pre_id, post_id = _insert_bracket(
        storage,
        pre_balance="10.00",
        post_balance="8.75",
    )

    attribution = attribute_thread_billing(repo, snapshot_id)

    assert attribution.billing_source is BillingSource.ADDITIONAL_CREDITS
    assert attribution.confidence is AttributionConfidence.INFERRED_HIGH
    assert attribution.credit_balance_delta == "1.25"
    assert attribution.pre_snapshot_id == pre_id
    assert attribution.post_snapshot_id == post_id
    assert attribution.overlapping_session_count == 1

    stored = _stored_thread_row(repo, snapshot_id)
    assert stored["billing_source"] == "additional_credits"
    assert stored["attribution_confidence"] == "inferred_high"
    assert stored["estimated_usage_credits_micros"] == 1_250_000
    assert stored["estimated_usage_usd_micros"] == 490_000
    evidence = json.loads(stored["evidence_json"])
    assert set(evidence) == {
        "pre_snapshot_id",
        "pre_captured_at",
        "post_snapshot_id",
        "post_captured_at",
        "credit_balance_delta",
        "overlapping_session_count",
    }
    assert evidence["credit_balance_delta"] == "1.25"


def test_credit_drop_with_overlapping_codex_activity_stays_unknown_low(tmp_path):
    repo, storage, snapshot_id, _ = _repo_with_target_thread(tmp_path)
    _insert_bracket(storage, pre_balance="10.00", post_balance="8.75")
    with repo.database.connect() as conn:
        source_id = conn.execute(
            "SELECT id FROM sources WHERE name='codex'"
        ).fetchone()[0]
        conn.execute(
            """
            INSERT INTO sessions(
                source_id, external_session_id, started_at, ended_at
            ) VALUES(?, ?, ?, ?)
            """,
            (
                source_id,
                "019fed81-fe9b-74c3-96ed-ef3702293f04",
                "2026-08-20T10:02:00+00:00",
                "2026-08-20T10:08:00+00:00",
            ),
        )

    attribution = attribute_thread_billing(repo, snapshot_id)

    assert attribution.billing_source is BillingSource.UNKNOWN
    assert attribution.confidence is AttributionConfidence.INFERRED_LOW
    assert attribution.credit_balance_delta == "1.25"
    assert attribution.overlapping_session_count == 2


def test_plan_usage_rise_without_credit_change_is_included_plan_low(tmp_path):
    repo, storage, snapshot_id, _ = _repo_with_target_thread(tmp_path)
    _insert_bracket(
        storage,
        pre_balance="0",
        post_balance="0",
        pre_primary=40,
        post_primary=45,
    )

    attribution = attribute_thread_billing(repo, snapshot_id)

    assert attribution.billing_source is BillingSource.INCLUDED_PLAN
    assert attribution.confidence is AttributionConfidence.INFERRED_LOW
    assert attribution.credit_balance_delta == "0"
    stored = _stored_thread_row(repo, snapshot_id)
    assert stored["billing_source"] == "included_plan"
    assert stored["attribution_confidence"] == "inferred_low"
