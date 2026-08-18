from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from agentscope.domain.models import (
    AgentEvidence,
    NormalizedMessage,
    NormalizedSession,
    NormalizedTokenUsage,
    NormalizedToolCall,
    NormalizedTurn,
    SkillEvidence,
    SkillUsageType,
)

_ATTACHMENT_RE = re.compile(r"[A-Za-z]:[\\/][^\s\"']*?\.codex[\\/]attachments[\\/][^\s\"']+")
_SKILL_LINE_RE = re.compile(r"^\s*-\s+([A-Za-z0-9_.:-]+):", re.MULTILINE)
_ROOT_RE = re.compile(r"You are\s+[`']?/root[`']?", re.IGNORECASE)


@dataclass(slots=True)
class CodexCollectedSession:
    session: NormalizedSession
    turns: list[NormalizedTurn] = field(default_factory=list)
    messages: list[NormalizedMessage] = field(default_factory=list)
    tool_calls: list[NormalizedToolCall] = field(default_factory=list)
    token_usage: list[NormalizedTokenUsage] = field(default_factory=list)
    agent_evidence: list[AgentEvidence] = field(default_factory=list)
    skill_evidence: list[SkillEvidence] = field(default_factory=list)
    attachments: list[str] = field(default_factory=list)
    encrypted_reasoning_count: int = 0
    parse_errors: list[tuple[int, str]] = field(default_factory=list)


def _content_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for item in content:
        if isinstance(item, dict):
            text = item.get("text")
            if isinstance(text, str):
                parts.append(text)
    return "\n".join(parts)


def _output_text(output: Any) -> str:
    return _content_text(output)


def _skill_loaded_from_text(text: str, available_names: set[str]) -> set[str]:
    normalized = text.replace("/", "\\").lower()
    loaded: set[str] = set()
    for name in available_names:
        path_form = name.replace(":", "\\").lower()
        if path_form in normalized and "skill.md" in normalized:
            loaded.add(name)
    return loaded


def _spawned_agent(input_text: str) -> str | None:
    try:
        value = json.loads(input_text)
        if isinstance(value, dict) and isinstance(value.get("name"), str):
            return value["name"]
    except (json.JSONDecodeError, TypeError):
        pass
    match = re.search(r'"name"\s*:\s*"([^"]+)"', input_text)
    return match.group(1) if match else None


def collect_codex_rollout(path: Path) -> CodexCollectedSession:
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    session = NormalizedSession(
        external_session_id=path.stem,
        source="codex",
        raw_file_path=str(path),
    )
    result = CodexCollectedSession(session=session)
    current_turn: str | None = None
    current_model: str | None = None
    available_skills: set[str] = set()
    seen_skill: set[tuple[str, SkillUsageType, str]] = set()
    seen_agent: set[tuple[str, str, str | None]] = set()
    response_user_texts: set[str] = set()
    fallback_user_messages: list[NormalizedMessage] = []
    calls_by_id: dict[str, NormalizedToolCall] = {}

    def add_skill(name: str, usage: SkillUsageType, evidence: str, timestamp: str | None) -> None:
        key = (name, usage, evidence)
        if key in seen_skill:
            return
        seen_skill.add(key)
        result.skill_evidence.append(
            SkillEvidence(
                name=name,
                usage_type=usage,
                evidence_type=evidence,
                timestamp=timestamp,
                session_external_id=session.external_session_id,
            )
        )

    def add_agent(name: str, agent_type: str, parent: str | None, evidence: str, timestamp: str | None) -> None:
        key = (name, agent_type, parent)
        if key in seen_agent:
            return
        seen_agent.add(key)
        result.agent_evidence.append(
            AgentEvidence(
                name=name,
                agent_type=agent_type,
                parent_name=parent,
                evidence_type=evidence,
                timestamp=timestamp,
                session_external_id=session.external_session_id,
            )
        )

    for line_number, raw in enumerate(lines, start=1):
        if not raw.strip():
            continue
        try:
            event = json.loads(raw)
        except json.JSONDecodeError as exc:
            if line_number == len(lines):
                continue
            result.parse_errors.append((line_number, str(exc)))
            continue

        timestamp = str(event.get("timestamp") or "")
        event_type = event.get("type")
        payload = event.get("payload") or {}

        if event_type == "session_meta" and isinstance(payload, dict):
            external_id = payload.get("session_id") or payload.get("id")
            if external_id:
                session.external_session_id = str(external_id)
            session.started_at = payload.get("timestamp") or timestamp
            session.project_path = payload.get("cwd")
            session.originator = payload.get("originator")
            session.cli_version = payload.get("cli_version")
            session.provider = payload.get("model_provider")
            session.metadata.update(
                {
                    "source": payload.get("source"),
                    "thread_source": payload.get("thread_source"),
                }
            )
            continue

        if event_type == "turn_context" and isinstance(payload, dict):
            turn_id = payload.get("turn_id")
            if turn_id:
                current_turn = str(turn_id)
                current_model = payload.get("model") or current_model
                session.model = current_model or session.model
                result.turns.append(
                    NormalizedTurn(
                        external_turn_id=current_turn,
                        session_external_id=session.external_session_id,
                        started_at=timestamp,
                        model=current_model,
                        metadata={
                            "cwd": payload.get("cwd"),
                            "effort": payload.get("effort"),
                            "timezone": payload.get("timezone"),
                        },
                    )
                )
            continue

        if event_type == "response_item" and isinstance(payload, dict):
            payload_type = payload.get("type")
            if payload_type == "reasoning":
                if payload.get("encrypted_content"):
                    result.encrypted_reasoning_count += 1
                continue

            if payload_type == "message":
                role = str(payload.get("role") or "unknown")
                text = _content_text(payload.get("content"))
                message = NormalizedMessage(
                    role=role,
                    timestamp=timestamp,
                    content=text or None,
                    phase=payload.get("phase"),
                    session_external_id=session.external_session_id,
                    turn_external_id=current_turn,
                    source_file=str(path),
                    source_line=line_number,
                )
                result.messages.append(message)
                if role == "user" and text:
                    response_user_texts.add(text)
                for attachment in _ATTACHMENT_RE.findall(text):
                    if attachment not in result.attachments:
                        result.attachments.append(attachment)
                names = set(_SKILL_LINE_RE.findall(text))
                if names:
                    available_skills.update(names)
                    for name in names:
                        add_skill(name, SkillUsageType.AVAILABLE, "skills_catalog", timestamp)
                if _ROOT_RE.search(text):
                    add_agent("root", "root", None, "developer_instruction", timestamp)
                if role == "assistant":
                    lower = text.lower()
                    if "using" in lower or "usar" in lower or "usando" in lower:
                        for name in available_skills:
                            if name.lower() in lower:
                                add_skill(name, SkillUsageType.INVOKED, "assistant_announcement", timestamp)
                continue

            if payload_type == "custom_tool_call":
                call_id = payload.get("call_id") or payload.get("id")
                input_text = str(payload.get("input") or "")
                tool_call = NormalizedToolCall(
                    name=str(payload.get("name") or "unknown"),
                    timestamp=timestamp,
                    external_call_id=str(call_id) if call_id else None,
                    session_external_id=session.external_session_id,
                    turn_external_id=current_turn,
                    status=payload.get("status"),
                    input_size=len(input_text),
                    source_file=str(path),
                    source_line=line_number,
                )
                result.tool_calls.append(tool_call)
                if call_id:
                    calls_by_id[str(call_id)] = tool_call
                for name in _skill_loaded_from_text(input_text, available_skills):
                    add_skill(name, SkillUsageType.LOADED, "skill_file_read", timestamp)
                if tool_call.name == "spawn_agent":
                    agent_name = _spawned_agent(input_text)
                    if agent_name:
                        add_agent(agent_name, "subagent", "root", "spawn_agent", timestamp)
                continue

            if payload_type == "custom_tool_call_output":
                call_id = payload.get("call_id")
                if call_id and str(call_id) in calls_by_id:
                    calls_by_id[str(call_id)].output_size = len(_output_text(payload.get("output")))
                continue

        if event_type == "event_msg" and isinstance(payload, dict):
            if payload.get("type") == "token_count":
                info = payload.get("info") or {}
                usage = info.get("last_token_usage") or {}
                if usage:
                    result.token_usage.append(
                        NormalizedTokenUsage(
                            timestamp=timestamp,
                            session_external_id=session.external_session_id,
                            turn_external_id=current_turn,
                            model=current_model or session.model,
                            input_tokens=usage.get("input_tokens"),
                            cached_input_tokens=usage.get("cached_input_tokens"),
                            cache_write_input_tokens=usage.get("cache_write_input_tokens"),
                            output_tokens=usage.get("output_tokens"),
                            reasoning_output_tokens=usage.get("reasoning_output_tokens"),
                            total_tokens=usage.get("total_tokens"),
                            context_window=info.get("model_context_window"),
                            source_file=str(path),
                            source_line=line_number,
                        )
                    )
            elif payload.get("type") == "user_message":
                text = payload.get("message")
                if isinstance(text, str) and text not in response_user_texts:
                    fallback_user_messages.append(
                        NormalizedMessage(
                            role="user",
                            timestamp=timestamp,
                            content=text,
                            session_external_id=session.external_session_id,
                            turn_external_id=current_turn,
                            source_file=str(path),
                            source_line=line_number,
                            metadata={"fallback_event_msg": True},
                        )
                    )
                    for attachment in _ATTACHMENT_RE.findall(text):
                        if attachment not in result.attachments:
                            result.attachments.append(attachment)

    result.messages.extend(fallback_user_messages)
    return result
