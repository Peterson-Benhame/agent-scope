# AgentScope V1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Build a local-first analytics CLI that ingests Codex and Headroom histories, normalizes them into SQLite, analyzes tokens/costs/agents/skills/tools/optimizations, and exports CSV/JSON/HTML reports.

**Architecture:** Provider-specific collectors parse local read-only sources into generic domain records. A SQLite repository persists reconstructable normalized data. Analytics query the normalized store and reporting exports safe metadata by default.

**Tech Stack:** Python 3.11+, standard library (`sqlite3`, `json`, `csv`, `html`) plus Typer and pytest.

**Spec:** `docs/specs/SPEC-000-master-v1.md` and `docs/specs/SPEC-001` through `SPEC-017`.

## Global Constraints

- Sources are read-only.
- SQLite is reconstructable from original sources.
- Unknown monetary values are NULL, never zero.
- Skill availability, loading and invocation are distinct states.
- Headroom is an Optimizer, not an Agent.
- Correlation confidence is explicit: exact/high/medium/unknown.
- Safe metadata reporting is the default.
- No HTTP server, VS Code extension, routing, recommendation or model selection in V1.
- Tests use synthetic sanitized fixtures only.

---

### Task 1: Project skeleton and domain model

**Files:** `pyproject.toml`, `src/agentscope/__init__.py`, `src/agentscope/domain/models.py`, `tests/unit/test_domain_models.py`.

- [x] Write failing tests for normalized domain defaults and enum values.
- [x] Run targeted tests and verify RED.
- [x] Implement minimal dataclasses/enums.
- [x] Re-run and verify GREEN.

### Task 2: Codex collector

**Files:** `src/agentscope/collectors/codex.py`, `tests/fixtures/codex/rollout.jsonl`, `tests/unit/test_codex_collector.py`.

- [x] Test `session_meta`, `turn_context`, messages, tool calls, token counts, encrypted reasoning metadata, attachments, skills and agents.
- [x] Verify RED.
- [x] Implement line-by-line parser with malformed-final-line tolerance.
- [x] Verify GREEN.

### Task 3: Headroom collector

**Files:** `src/agentscope/collectors/headroom.py`, Headroom fixtures and `tests/unit/test_headroom_collector.py`.

- [x] Test lifetime metrics, cumulative-history deltas, per-request savings and optional-file absence.
- [x] Verify RED.
- [x] Implement collector without double counting aggregates.
- [x] Verify GREEN.

### Task 4: SQLite schema, repository and import state

**Files:** `src/agentscope/storage/database.py`, `src/agentscope/storage/repository.py`, `tests/unit/test_storage.py`.

- [x] Test schema, idempotency and NULL costs.
- [x] Verify RED.
- [x] Implement schema migration v1, foreign keys, unique constraints and repository methods.
- [x] Verify GREEN.

### Task 5: Import pipeline, incremental behavior and correlation

**Files:** `src/agentscope/importer.py`, `src/agentscope/correlation.py`, importer/correlation tests.

- [x] Test double import, growing files, provenance and correlation confidence.
- [x] Verify RED.
- [x] Implement import-state/hash/offset logic and correlation rules.
- [x] Verify GREEN.

### Task 6: Analytics

**Files:** `src/agentscope/analytics/service.py`, `tests/unit/test_analytics.py`.

- [x] Test tokens, cache, Headroom savings, costs, project/model grouping and agent/skill/tool distinctions.
- [x] Verify RED.
- [x] Implement SQL-backed analytics.
- [x] Verify GREEN.

### Task 7: Configuration, CLI, safe exports and HTML report

**Files:** config, CLI, reporting modules and unit/integration tests.

- [x] Test paths, CLI workflow, safe reporting, CSV/JSON and HTML output.
- [x] Verify RED.
- [x] Implement configuration, Typer CLI and reporting.
- [x] Verify GREEN.

### Task 8: Documentation and release verification

- [x] Run full test suite.
- [x] Run CLI against synthetic fixtures with a fresh database and report.
- [x] Verify second import creates no logical duplication.
- [x] Inspect safe report for prompt/tool-output leakage.
- [x] Package docs/specs and README.
- [x] Perform fresh `python -m pytest -q` before publication.
