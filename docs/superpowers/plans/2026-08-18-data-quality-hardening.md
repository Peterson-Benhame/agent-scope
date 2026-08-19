# AgentScope Data Quality Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove false-positive skills/models/agents and expose explicit data-quality metrics without changing valid V1 evidence semantics.

**Architecture:** Classification stays provider-specific. Parsers emit evidence only from explicit supported patterns, while analytics reports confidence/unknown coverage separately. No generic filename/word guessing is allowed.

**Tech Stack:** Python 3.11+, sqlite3, dataclasses, pytest.

**Spec:** `docs/superpowers/specs/2026-08-18-multi-source-team-analytics-design.md` — Increment B.

## Global Constraints

- `available`, `loaded`, `invoked` remain distinct.
- `invoked` must never be inferred from mere availability.
- Arbitrary filenames, code symbols, natural-language words, workflow labels, and review labels must not become skills/models/agents.
- Unknown remains explicit, not silently remapped.
- TDD is required.

---

### Task 1: Lock current false positives in regression fixtures

**Files:**
- Modify: `tests/fixtures/codex/rollout.jsonl`
- Modify: `tests/unit/test_codex_collector.py`

- [ ] Add synthetic lines containing filenames and generic words such as `.env.local`, `App.tsx`, `SaldoRepository.cs`, `Clareza`, `Estrutura`, and `revisão automática do codex` alongside valid skill/model evidence.
- [ ] Assert collector output contains valid `superpowers:brainstorming` evidence but none of the false-positive labels.
- [ ] Run `python -m pytest tests/unit/test_codex_collector.py -q` and verify RED.
- [ ] Commit test-only regression fixture changes.

### Task 2: Tighten Codex skill evidence extraction

**Files:**
- Modify: `src/agentscope/collectors/codex.py`
- Modify: `tests/unit/test_codex_collector.py`

**Interfaces:**
- Produce helper `_extract_skill_evidence(text: str, timestamp: str | None, session_id: str | None) -> list[SkillEvidence]`.
- Evidence is accepted only from explicit skills instruction blocks, explicit skill-loading paths, or explicit invocation statements covered by tests.

- [ ] Implement helper using allow-listed patterns for skill names like `namespace:name` or explicit skill file context.
- [ ] Remove broad token/filename scanning that emits arbitrary names.
- [ ] Preserve `available`, `loaded`, `invoked` distinctions.
- [ ] Run collector tests and verify GREEN.
- [ ] Commit `fix: harden codex skill detection`.

### Task 3: Harden model normalization

**Files:**
- Create: `src/agentscope/domain/model_normalization.py`
- Modify: `src/agentscope/collectors/codex.py`
- Modify: `tests/unit/test_domain_models.py`
- Modify: `tests/unit/test_codex_collector.py`

**Interfaces:**
- Produce `normalize_model_name(value: str | None) -> str | None`.
- Return `None` for empty/non-model labels known from fixtures; preserve provider model identifiers verbatim except whitespace/case normalization needed for stable identity.

- [ ] Write RED tests for valid `gpt-5.6-terra`, `gpt-5.5`, and invalid `revisão automática do codex`.
- [ ] Implement minimal normalization and apply it only to explicit model fields.
- [ ] Verify no fallback from workflow/originator text creates a model.
- [ ] Run targeted tests and commit.

### Task 4: Harden agent evidence extraction

**Files:**
- Modify: `src/agentscope/collectors/codex.py`
- Modify: `tests/unit/test_codex_collector.py`

**Interfaces:**
- Agent evidence may come from explicit root marker or explicit subagent/tool payload such as `spawn_agent`.
- Generic words like `Agente`, `Arquiteto`, `QA`, `root` in ordinary prose do not create agents unless matched by provider-specific explicit syntax.

- [ ] Add RED tests with explicit `spawn_agent` reviewer plus ordinary prose containing agent-like words.
- [ ] Refactor extraction to explicit patterns only.
- [ ] Preserve parent-child evidence when available.
- [ ] Run tests and commit.

### Task 5: Add data-quality analytics

**Files:**
- Modify: `src/agentscope/analytics/service.py`
- Modify: `tests/unit/test_analytics.py`

**Interfaces:**
- Produce `data_quality() -> dict[str, object]` containing at least:
  - `import_errors`
  - `unknown_model_sessions`
  - `unknown_model_token_share`
  - `optimization_confidence`
  - `skill_evidence_rows`
  - `agent_evidence_rows`

- [ ] Write RED test using synthetic fixtures.
- [ ] Implement SQL queries with nullable/unknown semantics.
- [ ] Ensure unknown share is ratio of token usage with `model_id IS NULL` over total input tokens, returning `None` when denominator is zero.
- [ ] Run analytics tests and commit.

### Task 6: Surface quality metrics in report

**Files:**
- Modify: `src/agentscope/reporting/html_report.py`
- Modify: `tests/unit/test_reporting.py`

- [ ] Write RED assertions for `Qualidade dos dados`, `Modelos desconhecidos`, and correlation confidence.
- [ ] Render metrics from `analytics.data_quality()` without implying inferred evidence is exact.
- [ ] Keep privacy assertions unchanged.
- [ ] Run reporting tests and commit.

### Task 7: Full Increment B verification

- [ ] Run `python -m pytest -q`.
- [ ] Generate a report from synthetic fixtures.
- [ ] Confirm false-positive labels are absent from Skills/Models/Agents.
- [ ] Confirm valid evidence remains present.
- [ ] Commit documentation/status updates if needed.
