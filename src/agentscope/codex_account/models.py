from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class BillingSource(str, Enum):
    INCLUDED_PLAN = "included_plan"
    ADDITIONAL_CREDITS = "additional_credits"
    MIXED = "mixed"
    UNKNOWN = "unknown"


class AttributionConfidence(str, Enum):
    EXPLICIT = "explicit"
    INFERRED_HIGH = "inferred_high"
    INFERRED_LOW = "inferred_low"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class CodexAccountSnapshot:
    captured_at: str
    auth_mode: str | None = None
    plan_type: str | None = None
    limit_id: str | None = None
    limit_name: str | None = None
    primary_used_percent: int | None = None
    primary_window_duration_mins: int | None = None
    primary_resets_at: int | None = None
    secondary_used_percent: int | None = None
    secondary_window_duration_mins: int | None = None
    secondary_resets_at: int | None = None
    credits_has_credits: bool | None = None
    credits_balance: str | None = None
    credits_unlimited: bool | None = None
    spend_control_reached: bool | None = None
    individual_limit: str | None = None
    individual_used: str | None = None
    individual_remaining_percent: int | None = None
    individual_resets_at: int | None = None
    source: str = "codex_app_server"
    status: str = "complete"
    error_code: str | None = None


@dataclass(frozen=True, slots=True)
class CodexThreadUsageGroup:
    model: str | None
    reasoning_effort: str | None
    speed: str | None
    estimated_usage_credits_micros: int
    net_new_input_tokens: int | None = None
    cached_input_tokens: int | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None


@dataclass(frozen=True, slots=True)
class CodexThreadUsageSnapshot:
    captured_at: str
    thread_id: str
    session_id: int | None
    estimated_usage_credits_micros: int | None
    estimated_usage_usd_micros: int | None
    source: str = "codex_app_server"
    status: str = "complete"
    billing_route_available: bool = True
    billing_source: BillingSource = BillingSource.UNKNOWN
    attribution_confidence: AttributionConfidence = AttributionConfidence.UNKNOWN
    evidence_json: str = "{}"
    groups: tuple[CodexThreadUsageGroup, ...] = field(default_factory=tuple)
