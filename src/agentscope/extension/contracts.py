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
    estimated_savings_usd: float | None


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


def to_dict(value: Any) -> dict[str, Any]:
    return asdict(value)
