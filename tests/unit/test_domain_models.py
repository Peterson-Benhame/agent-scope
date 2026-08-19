from agentscope.domain.model_normalization import normalize_model_name
from agentscope.domain.models import (
    AgentEvidence,
    CorrelationConfidence,
    IdentityConfidence,
    NormalizedMachine,
    NormalizedMessage,
    NormalizedSession,
    NormalizedUser,
    SkillEvidence,
    SkillUsageType,
)


def test_skill_usage_type_has_distinct_states():
    assert [x.value for x in SkillUsageType] == ["available", "loaded", "invoked"]


def test_correlation_confidence_has_explicit_levels():
    assert [x.value for x in CorrelationConfidence] == ["exact", "high", "medium", "unknown"]


def test_identity_confidence_has_explicit_levels():
    assert [x.value for x in IdentityConfidence] == ["exact", "inferred", "unknown"]


def test_normalized_user_defaults_to_unknown_confidence():
    user = NormalizedUser(stable_key="user-key")

    assert user.display_name is None
    assert user.provider_user_id is None
    assert user.provider is None
    assert user.confidence is IdentityConfidence.UNKNOWN
    assert user.metadata == {}


def test_normalized_machine_keeps_identity_separate_from_user():
    machine = NormalizedMachine(stable_key="machine-key", display_name="Notebook")

    assert machine.stable_key == "machine-key"
    assert machine.display_name == "Notebook"
    assert machine.os is None
    assert machine.metadata == {}


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


def test_model_normalization_preserves_explicit_model_identifiers():
    assert normalize_model_name(" gpt-5.6-terra ") == "gpt-5.6-terra"
    assert normalize_model_name("GPT-5.5") == "gpt-5.5"
    assert normalize_model_name("claude-sonnet-4") == "claude-sonnet-4"


def test_model_normalization_rejects_empty_and_review_labels():
    assert normalize_model_name(None) is None
    assert normalize_model_name("   ") is None
    assert normalize_model_name("revisão automática do codex") is None
    assert normalize_model_name("automatic codex review") is None
