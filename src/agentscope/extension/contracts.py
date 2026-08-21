from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


SNAPSHOT_SCHEMA = "agentscope-extension-snapshot"
SNAPSHOT_VERSION = 2


@dataclass(frozen=True, slots=True)
class SnapshotSummary:
    sessions: int
    total_tokens: int
    tokens_saved: int
    cache_ratio: float | None
    observed_cost_usd: float | None
    estimated_cost_usd: float | None
    known_estimated_cost_usd: float | None
    estimated_cost_events_total: int
    estimated_cost_events_priced: int
    estimated_cost_coverage: float
    estimated_cost_complete: bool
    estimated_savings_usd: float | None


@dataclass(frozen=True, slots=True)
class SnapshotBilling:
    mode: str
    confidence: str
    estimated_cost_basis: str
    is_observed_spend: bool


@dataclass(frozen=True, slots=True)
class SnapshotDimensions:
    projects: list[str]
    models: list[str]
    sources: list[str]
    users: list[str]
    machines: list[str]


@dataclass(frozen=True, slots=True)
class SnapshotQuality:
    import_errors: int
    tokens_without_model: int
    identity_confidence: dict[str, int]
    correlation_confidence: dict[str, int]


@dataclass(frozen=True, slots=True)
class AvailabilityItem:
    available: bool
    reason: str | None


@dataclass(frozen=True, slots=True)
class SnapshotAvailability:
    observed_cost: AvailabilityItem
    estimated_cost: AvailabilityItem
    estimated_savings: AvailabilityItem


@dataclass(frozen=True, slots=True)
class SnapshotCodexCredits:
    has_credits: bool | None
    balance: str | None
    unlimited: bool | None


@dataclass(frozen=True, slots=True)
class SnapshotCodexAccount:
    available: bool
    captured_at: str | None = None
    plan_type: str | None = None
    primary_used_percent: int | None = None
    primary_resets_at: int | None = None
    secondary_used_percent: int | None = None
    secondary_resets_at: int | None = None
    credits: SnapshotCodexCredits | None = None
    spend_control_reached: bool | None = None


def to_dict(value: Any) -> dict[str, Any]:
    return asdict(value)
