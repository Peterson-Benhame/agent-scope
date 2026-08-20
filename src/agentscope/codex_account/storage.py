from __future__ import annotations

from agentscope.codex_account.models import (
    AttributionConfidence,
    BillingSource,
    CodexAccountSnapshot,
    CodexThreadUsageSnapshot,
)
from agentscope.storage.database import Database


class CodexAccountStorage:
    def __init__(self, database: Database):
        self.database = database

    def insert_account_snapshot(self, snapshot: CodexAccountSnapshot) -> int:
        with self.database.connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO codex_account_usage_snapshots(
                    captured_at, auth_mode, plan_type, limit_id, limit_name,
                    primary_used_percent, primary_window_duration_mins, primary_resets_at,
                    secondary_used_percent, secondary_window_duration_mins, secondary_resets_at,
                    credits_has_credits, credits_balance, credits_unlimited,
                    spend_control_reached, individual_limit, individual_used,
                    individual_remaining_percent, individual_resets_at,
                    source, status, error_code
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    snapshot.captured_at,
                    snapshot.auth_mode,
                    snapshot.plan_type,
                    snapshot.limit_id,
                    snapshot.limit_name,
                    snapshot.primary_used_percent,
                    snapshot.primary_window_duration_mins,
                    snapshot.primary_resets_at,
                    snapshot.secondary_used_percent,
                    snapshot.secondary_window_duration_mins,
                    snapshot.secondary_resets_at,
                    snapshot.credits_has_credits,
                    snapshot.credits_balance,
                    snapshot.credits_unlimited,
                    snapshot.spend_control_reached,
                    snapshot.individual_limit,
                    snapshot.individual_used,
                    snapshot.individual_remaining_percent,
                    snapshot.individual_resets_at,
                    snapshot.source,
                    snapshot.status,
                    snapshot.error_code,
                ),
            )
            return int(cursor.lastrowid)

    def latest_account_snapshot(self) -> CodexAccountSnapshot | None:
        with self.database.connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM codex_account_usage_snapshots
                WHERE status='complete'
                ORDER BY captured_at DESC, id DESC
                LIMIT 1
                """
            ).fetchone()
        if row is None:
            return None
        return CodexAccountSnapshot(
            captured_at=str(row["captured_at"]),
            auth_mode=row["auth_mode"],
            plan_type=row["plan_type"],
            limit_id=row["limit_id"],
            limit_name=row["limit_name"],
            primary_used_percent=row["primary_used_percent"],
            primary_window_duration_mins=row["primary_window_duration_mins"],
            primary_resets_at=row["primary_resets_at"],
            secondary_used_percent=row["secondary_used_percent"],
            secondary_window_duration_mins=row["secondary_window_duration_mins"],
            secondary_resets_at=row["secondary_resets_at"],
            credits_has_credits=(
                bool(row["credits_has_credits"])
                if row["credits_has_credits"] is not None
                else None
            ),
            credits_balance=row["credits_balance"],
            credits_unlimited=(
                bool(row["credits_unlimited"])
                if row["credits_unlimited"] is not None
                else None
            ),
            spend_control_reached=(
                bool(row["spend_control_reached"])
                if row["spend_control_reached"] is not None
                else None
            ),
            individual_limit=row["individual_limit"],
            individual_used=row["individual_used"],
            individual_remaining_percent=row["individual_remaining_percent"],
            individual_resets_at=row["individual_resets_at"],
            source=str(row["source"]),
            status=str(row["status"]),
            error_code=row["error_code"],
        )

    def insert_thread_usage_snapshot(self, snapshot: CodexThreadUsageSnapshot) -> int:
        with self.database.connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO codex_thread_usage_snapshots(
                    captured_at, thread_id, session_id,
                    estimated_usage_credits_micros, estimated_usage_usd_micros,
                    source, status, billing_route_available,
                    billing_source, attribution_confidence, evidence_json
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    snapshot.captured_at,
                    snapshot.thread_id,
                    snapshot.session_id,
                    snapshot.estimated_usage_credits_micros,
                    snapshot.estimated_usage_usd_micros,
                    snapshot.source,
                    snapshot.status,
                    snapshot.billing_route_available,
                    snapshot.billing_source.value,
                    snapshot.attribution_confidence.value,
                    snapshot.evidence_json,
                ),
            )
            snapshot_id = int(cursor.lastrowid)
            for group in snapshot.groups:
                conn.execute(
                    """
                    INSERT INTO codex_thread_usage_groups(
                        thread_usage_snapshot_id, model, reasoning_effort, speed,
                        estimated_usage_credits_micros, net_new_input_tokens,
                        cached_input_tokens, input_tokens, output_tokens, total_tokens
                    ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        snapshot_id,
                        group.model,
                        group.reasoning_effort,
                        group.speed,
                        group.estimated_usage_credits_micros,
                        group.net_new_input_tokens,
                        group.cached_input_tokens,
                        group.input_tokens,
                        group.output_tokens,
                        group.total_tokens,
                    ),
                )
            return snapshot_id

    def latest_thread_usage(self, thread_id: str) -> CodexThreadUsageSnapshot | None:
        with self.database.connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM codex_thread_usage_snapshots
                WHERE thread_id=?
                ORDER BY captured_at DESC, id DESC LIMIT 1
                """,
                (thread_id,),
            ).fetchone()
        if row is None:
            return None
        return CodexThreadUsageSnapshot(
            captured_at=str(row["captured_at"]),
            thread_id=str(row["thread_id"]),
            session_id=row["session_id"],
            estimated_usage_credits_micros=row["estimated_usage_credits_micros"],
            estimated_usage_usd_micros=row["estimated_usage_usd_micros"],
            source=str(row["source"]),
            status=str(row["status"]),
            billing_route_available=bool(row["billing_route_available"]),
            billing_source=BillingSource(str(row["billing_source"])),
            attribution_confidence=AttributionConfidence(str(row["attribution_confidence"])),
            evidence_json=str(row["evidence_json"]),
        )
