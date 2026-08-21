from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from agentscope.codex_account.models import AttributionConfidence, BillingSource
from agentscope.codex_account.storage import CodexAccountStorage
from agentscope.storage.repository import Repository


@dataclass(frozen=True, slots=True)
class BillingAttribution:
    billing_source: BillingSource
    confidence: AttributionConfidence
    credit_balance_delta: str | None
    pre_snapshot_id: int | None
    post_snapshot_id: int | None
    overlapping_session_count: int


def _decimal_or_none(value: object) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _decimal_text(value: Decimal) -> str:
    if value == 0:
        return "0"
    normalized = value.normalize()
    return format(normalized, "f")


def _persist(
    storage: CodexAccountStorage,
    thread_snapshot_id: int,
    attribution: BillingAttribution,
    *,
    pre_row=None,
    post_row=None,
) -> BillingAttribution:
    evidence: dict[str, object] = {}
    if pre_row is not None:
        evidence["pre_snapshot_id"] = int(pre_row["id"])
        evidence["pre_captured_at"] = str(pre_row["captured_at"])
    if post_row is not None:
        evidence["post_snapshot_id"] = int(post_row["id"])
        evidence["post_captured_at"] = str(post_row["captured_at"])
    if attribution.credit_balance_delta is not None:
        evidence["credit_balance_delta"] = attribution.credit_balance_delta
    if pre_row is not None or post_row is not None:
        evidence["overlapping_session_count"] = attribution.overlapping_session_count

    storage.update_thread_attribution(
        thread_snapshot_id,
        billing_source=attribution.billing_source,
        confidence=attribution.confidence,
        evidence_json=json.dumps(evidence, separators=(",", ":")),
    )
    return attribution


def attribute_thread_billing(
    repository: Repository,
    thread_snapshot_id: int,
) -> BillingAttribution:
    storage = CodexAccountStorage(repository.database)
    context = storage.attribution_context(thread_snapshot_id)
    if context is None or context["session_started_at"] is None:
        return _persist(
            storage,
            thread_snapshot_id,
            BillingAttribution(
                BillingSource.UNKNOWN,
                AttributionConfidence.UNKNOWN,
                None,
                None,
                None,
                0,
            ),
        )

    session_start = str(context["session_started_at"])
    explicit_end = context["session_ended_at"]
    last_usage = context["last_usage_at"]
    fallback_end = context["thread_captured_at"]
    bracket_end = str(explicit_end or last_usage or fallback_end)

    pre_row = storage.account_snapshot_before(session_start)
    post_row = storage.account_snapshot_after(bracket_end)
    if pre_row is None or post_row is None:
        return _persist(
            storage,
            thread_snapshot_id,
            BillingAttribution(
                BillingSource.UNKNOWN,
                AttributionConfidence.UNKNOWN,
                None,
                int(pre_row["id"]) if pre_row is not None else None,
                int(post_row["id"]) if post_row is not None else None,
                0,
            ),
            pre_row=pre_row,
            post_row=post_row,
        )

    overlap_count = storage.count_overlapping_codex_sessions(
        str(pre_row["captured_at"]),
        str(post_row["captured_at"]),
    )

    pre_balance = _decimal_or_none(pre_row["credits_balance"])
    post_balance = _decimal_or_none(post_row["credits_balance"])
    delta = None
    if pre_balance is not None and post_balance is not None:
        delta = pre_balance - post_balance
    delta_text = _decimal_text(delta) if delta is not None else None

    billing_source = BillingSource.UNKNOWN
    confidence = AttributionConfidence.UNKNOWN

    if delta is not None and delta > 0:
        if explicit_end is not None and overlap_count == 1:
            billing_source = BillingSource.ADDITIONAL_CREDITS
            confidence = AttributionConfidence.INFERRED_HIGH
        else:
            confidence = AttributionConfidence.INFERRED_LOW
    elif delta == 0:
        pre_usage = pre_row["primary_used_percent"]
        post_usage = post_row["primary_used_percent"]
        if (
            pre_usage is not None
            and post_usage is not None
            and int(post_usage) > int(pre_usage)
        ):
            billing_source = BillingSource.INCLUDED_PLAN
            confidence = AttributionConfidence.INFERRED_LOW

    return _persist(
        storage,
        thread_snapshot_id,
        BillingAttribution(
            billing_source=billing_source,
            confidence=confidence,
            credit_balance_delta=delta_text,
            pre_snapshot_id=int(pre_row["id"]),
            post_snapshot_id=int(post_row["id"]),
            overlapping_session_count=overlap_count,
        ),
        pre_row=pre_row,
        post_row=post_row,
    )


__all__ = ["BillingAttribution", "attribute_thread_billing"]
