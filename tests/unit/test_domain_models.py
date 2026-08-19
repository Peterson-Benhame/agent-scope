from agentscope.domain.models import (
    AgentEvidence,
    CorrelationConfidence,
    NormalizedMessage,
    NormalizedSession,
    SkillEvidence,
    SkillUsageType,
)


def test_skill_usage_type_has_distinct_states():
    assert [x.value for x in SkillUsageType] == ["available", "loaded", "invoked"]


def test_correlation_confidence_has_explicit_levels():
    assert [x.value for x in CorrelationConfidence] == ["exact", "high", "medium", "unknown"]


def test_normalized_session_defaults_are_provider_neutral():
    session = NormalizedSession(external_session_id="s1", source="codex")
    assert session.project_path is None
    assert session.provider is None
    assert session.model is None
    assert session.metadata == {}


def test_message_keeps_provenance_without_requiring_content():
    message = NormalizedMessage(
        role="user",
        timestamp="2026-08-18T10:00:00Z",
        source_file="rollout.jsonl",
        source_line=7,
    )
    assert message.content is None
    assert message.content_type == "text"


def test_agent_and_skill_evidence_require_explicit_evidence_type():
    agent = AgentEvidence(name="root", agent_type="root", evidence_type="session_meta")
    skill = SkillEvidence(
        name="superpowers:brainstorming",
        usage_type=SkillUsageType.INVOKED,
        evidence_type="assistant_announcement",
    )
    assert agent.evidence_type == "session_meta"
    assert skill.usage_type is SkillUsageType.INVOKED
