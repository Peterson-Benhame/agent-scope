from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from agentscope.domain.models import CorrelationConfidence, NormalizedOptimization


@dataclass(slots=True, frozen=True)
class SessionCandidate:
    external_session_id: str
    started_at: str | None
    ended_at: str | None
    model: str | None
    project_path: str | None = None


@dataclass(slots=True, frozen=True)
class CorrelationResult:
    session_external_id: str | None
    confidence: CorrelationConfidence


def _dt(value: str | None) -> datetime | None:
    if not value:
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def correlate_optimization(
    optimization: NormalizedOptimization,
    candidates: list[SessionCandidate],
) -> CorrelationResult:
    if optimization.session_external_id:
        for candidate in candidates:
            if candidate.external_session_id == optimization.session_external_id:
                return CorrelationResult(candidate.external_session_id, CorrelationConfidence.EXACT)

    timestamp = _dt(optimization.timestamp)
    if timestamp is None:
        return CorrelationResult(None, CorrelationConfidence.UNKNOWN)

    model_matches = [
        c for c in candidates
        if not optimization.model or not c.model or c.model == optimization.model
    ]

    bounded: list[SessionCandidate] = []
    for candidate in model_matches:
        start = _dt(candidate.started_at)
        end = _dt(candidate.ended_at)
        if start and end and start <= timestamp <= end:
            bounded.append(candidate)
    if len(bounded) == 1:
        return CorrelationResult(bounded[0].external_session_id, CorrelationConfidence.HIGH)
    if len(bounded) > 1:
        return CorrelationResult(None, CorrelationConfidence.UNKNOWN)

    nearby_open: list[SessionCandidate] = []
    for candidate in model_matches:
        if candidate.ended_at:
            continue
        start = _dt(candidate.started_at)
        if start and 0 <= (timestamp - start).total_seconds() <= 300:
            nearby_open.append(candidate)
    if len(nearby_open) == 1:
        return CorrelationResult(nearby_open[0].external_session_id, CorrelationConfidence.MEDIUM)

    return CorrelationResult(None, CorrelationConfidence.UNKNOWN)
