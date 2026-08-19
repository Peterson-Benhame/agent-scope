from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class SkillUsageType(str, Enum):
    AVAILABLE = "available"
    LOADED = "loaded"
    INVOKED = "invoked"


class CorrelationConfidence(str, Enum):
    EXACT = "exact"
    HIGH = "high"
    MEDIUM = "medium"
    UNKNOWN = "unknown"


class IdentityConfidence(str, Enum):
    EXACT = "exact"
    INFERRED = "inferred"
    UNKNOWN = "unknown"


@dataclass(slots=True)
class NormalizedUser:
    stable_key: str
    display_name: str | None = None
    provider_user_id: str | None = None
    provider: str | None = None
    confidence: IdentityConfidence = IdentityConfidence.UNKNOWN
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class NormalizedMachine:
    stable_key: str
    display_name: str | None = None
    os: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class NormalizedSession:
    external_session_id: str
    source: str
    started_at: str | None = None
    ended_at: str | None = None
    project_path: str | None = None
    originator: str | None = None
    provider: str | None = None
    model: str | None = None
    cli_version: str | None = None
    raw_file_path: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class NormalizedTurn:
    external_turn_id: str
    session_external_id: str
    started_at: str | None = None
    ended_at: str | None = None
    model: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class NormalizedMessage:
    role: str
    timestamp: str
    content: str | None = None
    content_type: str = "text"
    phase: str | None = None
    session_external_id: str | None = None
    turn_external_id: str | None = None
    source_file: str | None = None
    source_line: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class NormalizedToolCall:
    name: str
    timestamp: str
    external_call_id: str | None = None
    session_external_id: str | None = None
    turn_external_id: str | None = None
    status: str | None = None
    duration_ms: float | None = None
    input_size: int | None = None
    output_size: int | None = None
    provider: str | None = None
    category: str | None = None
    source_file: str | None = None
    source_line: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class NormalizedTokenUsage:
    timestamp: str
    session_external_id: str | None = None
    turn_external_id: str | None = None
    model: str | None = None
    input_tokens: int | None = None
    cached_input_tokens: int | None = None
    cache_write_input_tokens: int | None = None
    output_tokens: int | None = None
    reasoning_output_tokens: int | None = None
    total_tokens: int | None = None
    context_window: int | None = None
    source_file: str | None = None
    source_line: int | None = None


@dataclass(slots=True)
class NormalizedOptimization:
    timestamp: str
    optimizer: str
    model: str | None = None
    session_external_id: str | None = None
    original_tokens: int | None = None
    optimized_tokens: int | None = None
    tokens_saved: int | None = None
    compression_percent: float | None = None
    cache_read_tokens: int | None = None
    compression_savings_usd: float | None = None
    cache_savings_usd: float | None = None
    observed_input_cost_usd: float | None = None
    confidence: CorrelationConfidence = CorrelationConfidence.UNKNOWN
    source_file: str | None = None
    source_line: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class AgentEvidence:
    name: str
    agent_type: str
    evidence_type: str
    parent_name: str | None = None
    timestamp: str | None = None
    session_external_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class SkillEvidence:
    name: str
    usage_type: SkillUsageType
    evidence_type: str
    timestamp: str | None = None
    session_external_id: str | None = None
    source: str | None = None
    version: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
