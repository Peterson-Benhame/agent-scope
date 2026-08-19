# AgentScope Provider Adapters Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add verified, isolated adapters for Claude Code, GitHub Copilot, Kimi, and Gemini without guessing unsupported local formats.

**Architecture:** Each provider adapter owns discovery, format/version validation, parsing, capabilities, and sanitized synthetic fixtures. Adapters emit only normalized records supported by explicit evidence. Unsupported versions return diagnostics and no guessed records.

**Tech Stack:** Python 3.11+, pathlib/json/sqlite3 as needed per verified provider format, SourceAdapter framework, pytest.

**Spec:** `docs/superpowers/specs/2026-08-18-multi-source-team-analytics-design.md` — Increment E.

## Global Constraints

- One adapter per reviewable commit/PR segment.
- Each parser requires a committed sanitized fixture representing a verified supported format/version.
- Unsupported/unknown format must return a diagnostic and import zero records.
- Missing metrics stay unavailable/NULL.
- Provider stores are opened read-only.
- No generic recursive JSON/SQLite ingestion.
- No prompts/responses/code are required for analytics capability; fixtures may include sentinel content only for privacy regression tests.
- TDD is required.

---

### Task 1: Shared provider-version validation helpers

**Files:**
- Create: `src/agentscope/sources/format_detection.py`
- Create: `tests/unit/test_format_detection.py`

**Interfaces:**
- `FormatSupport(supported: bool, version: str|None, diagnostic: str|None)`
- `require_known_version(observed: str|None, supported: set[str], source: str) -> FormatSupport`

- [ ] Write RED tests for supported, missing, and unsupported versions.
- [ ] Implement deterministic diagnostics such as `"claude_code unsupported format version: X"`.
- [ ] Run tests and commit.

### Task 2: Claude Code adapter

**Files:**
- Create: `src/agentscope/sources/claude_code.py`
- Create: `tests/fixtures/claude_code/session.jsonl`
- Create: `tests/unit/test_claude_code_adapter.py`

**Interfaces:**
- `ClaudeCodeAdapter.source_name == "claude_code"`.
- Discovery checks only documented/verified Claude Code local history roots resolved from user home or explicit override `AGENTSCOPE_CLAUDE_HOME`.
- Capabilities are set from fixture-backed evidence only.

- [ ] Before parser code, record the verified root/format/version as constants in the adapter test fixture metadata.
- [ ] Write RED discovery test against a temporary home containing the verified layout.
- [ ] Write RED parser test asserting only known fields become normalized sessions/models/tokens/tools/agents.
- [ ] Add unsupported-version test asserting diagnostic and zero normalized batches.
- [ ] Implement minimal parser for that fixture/version only.
- [ ] Run `python -m pytest tests/unit/test_claude_code_adapter.py -q` and commit.

### Task 3: GitHub Copilot adapter

**Files:**
- Create: `src/agentscope/sources/github_copilot.py`
- Create: `tests/fixtures/github_copilot/` with a sanitized copy/schema of the verified local store.
- Create: `tests/unit/test_github_copilot_adapter.py`

**Interfaces:**
- `GitHubCopilotAdapter.source_name == "github_copilot"`.
- If the supported source is SQLite, connect using URI read-only mode: `sqlite3.connect(f"file:{path}?mode=ro", uri=True)`.
- Discovery checks only verified Copilot CLI/session store locations or explicit `AGENTSCOPE_COPILOT_HOME`.

- [ ] Commit a minimal sanitized fixture generated from the verified schema, not a developer's real history.
- [ ] Write RED tests for discovery, read-only opening, sessions/models/tokens/tools/user identity fields actually present, and unavailable costs.
- [ ] Implement capability flags exactly matching fixture evidence.
- [ ] Add unsupported-schema test that produces diagnostic without writes.
- [ ] Run targeted tests and commit.

### Task 4: Kimi adapter

**Files:**
- Create: `src/agentscope/sources/kimi.py`
- Create: `tests/fixtures/kimi/session.jsonl`
- Create: `tests/unit/test_kimi_adapter.py`

**Interfaces:**
- `KimiAdapter.source_name == "kimi"`.
- Discovery uses only verified Kimi local data location or `AGENTSCOPE_KIMI_HOME`.
- Parser handles only verified JSONL record types.

- [ ] Write RED discovery/parser tests from sanitized fixture.
- [ ] Assert unknown JSONL record types are preserved only as safe diagnostic metadata or ignored; they must not be guessed into skills/models/agents.
- [ ] Implement minimal parser/capabilities.
- [ ] Add malformed-final-line tolerance only if verified Kimi storage is append-style JSONL and the fixture test demonstrates it.
- [ ] Run targeted tests and commit.

### Task 5: Gemini adapter

**Files:**
- Create: `src/agentscope/sources/gemini.py`
- Create: `tests/fixtures/gemini/` with sanitized verified session format.
- Create: `tests/unit/test_gemini_adapter.py`

**Interfaces:**
- `GeminiAdapter.source_name == "gemini"`.
- Discovery uses only verified Gemini CLI persisted-session roots or `AGENTSCOPE_GEMINI_HOME`.

- [ ] Write RED discovery/parser/version tests.
- [ ] Implement only fields backed by the verified session fixture.
- [ ] Keep unsupported/missing cost/cache/user data NULL and capabilities false.
- [ ] Run targeted tests and commit.

### Task 6: Register all new adapters and configuration overrides

**Files:**
- Modify: `src/agentscope/sources/registry.py`
- Modify: `src/agentscope/config.py`
- Modify: `tests/unit/test_source_registry.py`
- Modify: `tests/unit/test_config.py`

**Interfaces:**
- Default registry order: `codex`, `headroom`, `claude_code`, `github_copilot`, `kimi`, `gemini`.
- Add optional home overrides for each provider.

- [ ] Write RED registry test asserting all six names are registered and disabled sources are skipped.
- [ ] Add config path overrides without making directories automatically.
- [ ] Run tests and commit.

### Task 7: Multi-adapter collection integration

**Files:**
- Create: `tests/integration/test_multi_source_collection.py`
- Modify: `src/agentscope/importer.py` only if integration exposes orchestration gaps.

- [ ] Arrange temporary verified fixture roots for at least Codex, Headroom, and two new providers.
- [ ] Run one `collect` and assert sessions/usage are separated by source.
- [ ] Make one adapter unsupported and assert other sources still import, aggregate error/diagnostic is visible, and DB remains consistent.
- [ ] Run collection twice and assert no logical duplication.
- [ ] Commit.

### Task 8: Provider support documentation and full Increment E verification

**Files:**
- Modify: `README.md`
- Create: `docs/provider-support.md`

- [ ] Document each source, verified format/version, default/override path, supported capabilities, and known unavailable metrics.
- [ ] Run `python -m pytest -q`.
- [ ] Verify fixtures contain no real credentials/user content.
- [ ] Verify each unsupported-version test passes.
- [ ] Commit docs and fresh verification result.
