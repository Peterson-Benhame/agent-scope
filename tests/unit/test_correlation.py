from agentscope.correlation import SessionCandidate, correlate_optimization
from agentscope.domain.models import CorrelationConfidence, NormalizedOptimization


def opt(session_id=None, timestamp="2026-08-18T22:45:48Z", model="gpt-5.6-terra"):
    return NormalizedOptimization(
        timestamp=timestamp,
        optimizer="headroom",
        session_external_id=session_id,
        model=model,
    )


def test_exact_session_id_wins():
    candidates = [
        SessionCandidate("s1", "2026-08-18T22:40:00Z", "2026-08-18T23:00:00Z", "gpt-5.6-terra"),
        SessionCandidate("s2", "2026-08-18T22:40:00Z", "2026-08-18T23:00:00Z", "gpt-5.6-terra"),
    ]
    result = correlate_optimization(opt(session_id="s2"), candidates)
    assert result.session_external_id == "s2"
    assert result.confidence is CorrelationConfidence.EXACT


def test_unique_time_and_model_match_is_high_confidence():
    candidates = [
        SessionCandidate("s1", "2026-08-18T22:40:00Z", "2026-08-18T22:50:00Z", "gpt-5.6-terra"),
        SessionCandidate("s2", "2026-08-18T21:00:00Z", "2026-08-18T21:30:00Z", "gpt-5.6-terra"),
    ]
    result = correlate_optimization(opt(), candidates)
    assert result.session_external_id == "s1"
    assert result.confidence is CorrelationConfidence.HIGH


def test_open_session_near_start_is_medium_confidence():
    candidates = [SessionCandidate("s1", "2026-08-18T22:44:00Z", None, "gpt-5.6-terra")]
    result = correlate_optimization(opt(), candidates)
    assert result.session_external_id == "s1"
    assert result.confidence is CorrelationConfidence.MEDIUM


def test_ambiguous_match_stays_unknown():
    candidates = [
        SessionCandidate("s1", "2026-08-18T22:40:00Z", "2026-08-18T22:50:00Z", "gpt-5.6-terra"),
        SessionCandidate("s2", "2026-08-18T22:41:00Z", "2026-08-18T22:49:00Z", "gpt-5.6-terra"),
    ]
    result = correlate_optimization(opt(), candidates)
    assert result.session_external_id is None
    assert result.confidence is CorrelationConfidence.UNKNOWN
