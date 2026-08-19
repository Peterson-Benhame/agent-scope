from pathlib import Path

from agentscope.collectors.codex import collect_codex_rollout
from agentscope.domain.models import SkillUsageType


FIXTURE = Path("tests/fixtures/codex/rollout.jsonl")


def test_collects_session_and_turn_metadata():
    data = collect_codex_rollout(FIXTURE)
    assert data.session.external_session_id == "session-1"
    assert data.session.project_path == r"C:\work\demo"
    assert data.session.originator == "codex_vscode"
    assert data.session.provider == "headroom"
    assert data.session.model == "gpt-5.6-terra"
    assert data.turns[0].external_turn_id == "turn-1"


def test_collects_user_and_assistant_messages_without_event_duplicate():
    data = collect_codex_rollout(FIXTURE)
    roles = [m.role for m in data.messages]
    assert roles.count("user") == 1
    assert roles.count("assistant") == 1


def test_collects_tool_call_and_output_size():
    data = collect_codex_rollout(FIXTURE)
    exec_call = next(x for x in data.tool_calls if x.external_call_id == "call-1")
    assert exec_call.name == "exec"
    assert exec_call.status == "completed"
    assert exec_call.input_size > 0
    assert exec_call.output_size == len("TOOL_OUTPUT_SECRET")


def test_collects_last_token_usage_not_cumulative_total():
    data = collect_codex_rollout(FIXTURE)
    usage = data.token_usage[0]
    assert usage.input_tokens == 18019
    assert usage.cached_input_tokens == 17152
    assert usage.output_tokens == 223
    assert usage.reasoning_output_tokens == 39
    assert usage.context_window == 258400
    assert usage.model == "gpt-5.6-terra"


def test_tracks_encrypted_reasoning_without_exposing_content():
    data = collect_codex_rollout(FIXTURE)
    assert data.encrypted_reasoning_count == 1
    assert "encrypted-secret" not in repr(data)


def test_links_attachment_reference():
    data = collect_codex_rollout(FIXTURE)
    assert data.attachments == [r"C:\Users\me\.codex\attachments\abc\pasted-text.txt"]


def test_skill_evidence_distinguishes_available_loaded_and_invoked():
    data = collect_codex_rollout(FIXTURE)
    evidence = {(x.name, x.usage_type) for x in data.skill_evidence}
    assert ("superpowers:brainstorming", SkillUsageType.AVAILABLE) in evidence
    assert ("superpowers:brainstorming", SkillUsageType.LOADED) in evidence
    assert ("superpowers:brainstorming", SkillUsageType.INVOKED) in evidence
    assert ("tdd", SkillUsageType.AVAILABLE) in evidence


def test_agent_evidence_detects_root_and_spawned_agent():
    data = collect_codex_rollout(FIXTURE)
    agents = {(x.name, x.agent_type, x.parent_name) for x in data.agent_evidence}
    assert ("root", "root", None) in agents
    assert ("reviewer", "subagent", "root") in agents
