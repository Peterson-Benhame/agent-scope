# AgentScope User/Machine Identity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add separate user and machine identities, explicit confidence, session association, and analytics dimensions while preserving V1 databases.

**Architecture:** Additive SQLite migration introduces `users`, `machines`, and nullable foreign keys on `sessions`. A small identity resolver creates stable local keys and permits configured display overrides. Provider adapters may later replace inferred user identity with exact provider identity.

**Tech Stack:** Python 3.11+, sqlite3, dataclasses, hashlib/platform/getpass, pytest.

**Spec:** `docs/superpowers/specs/2026-08-18-multi-source-team-analytics-design.md` — Increment D.

## Global Constraints

- Existing V1 data must remain queryable after migration.
- Machine identity is never used as user identity.
- Display names are labels, never uniqueness keys.
- Identity confidence values: `exact`, `inferred`, `unknown`.
- Email is optional and not required for identity.
- TDD is required.

---

### Task 1: Add identity domain types

**Files:**
- Modify: `src/agentscope/domain/models.py`
- Modify: `tests/unit/test_domain_models.py`

**Interfaces:**
- Add `IdentityConfidence(str, Enum)` with `EXACT`, `INFERRED`, `UNKNOWN`.
- Add `NormalizedUser(stable_key: str, display_name: str|None=None, provider_user_id: str|None=None, provider: str|None=None, confidence: IdentityConfidence=UNKNOWN, metadata: dict=...)`.
- Add `NormalizedMachine(stable_key: str, display_name: str|None=None, os: str|None=None, metadata: dict=...)`.

- [ ] Write RED enum/dataclass tests.
- [ ] Implement types.
- [ ] Run `python -m pytest tests/unit/test_domain_models.py -q` and commit.

### Task 2: Add additive schema migration

**Files:**
- Modify: `src/agentscope/storage/database.py`
- Modify: `tests/unit/test_storage.py`

**Interfaces:**
- Migration version 2 creates `users`, `machines` and adds nullable `user_id`, `machine_id` to `sessions`.
- Add indexes on `sessions(user_id)`, `sessions(machine_id)`, and date/source dimensions where absent.

- [ ] Write RED migration test starting from literal V1 schema with one session/token row.
- [ ] Call `Database.initialize()` and assert V1 data remains and migration version 2 is recorded.
- [ ] Implement ordered migration helper that checks `PRAGMA table_info(sessions)` before `ALTER TABLE` so repeated initialization is safe.
- [ ] Run storage tests and commit.

### Task 3: Repository upsert/association methods

**Files:**
- Modify: `src/agentscope/storage/repository.py`
- Modify: `tests/unit/test_storage.py`

**Interfaces:**
- `upsert_user(user: NormalizedUser) -> int`
- `upsert_machine(machine: NormalizedMachine) -> int`
- `associate_session_identity(session_id: int, user_id: int|None, machine_id: int|None) -> None`

- [ ] Write RED idempotency tests for same stable keys with changed display labels.
- [ ] Implement UPSERT by stable key.
- [ ] Ensure provider_user_id/display_name updates do not merge distinct stable keys.
- [ ] Run tests and commit.

### Task 4: Local identity resolver

**Files:**
- Create: `src/agentscope/identity.py`
- Modify: `src/agentscope/config.py`
- Modify: `tests/unit/test_config.py`
- Create: `tests/unit/test_identity.py`

**Interfaces:**
- Config adds `user_display_name: str|None`, `machine_display_name: str|None` from `AGENTSCOPE_USER_NAME` and `AGENTSCOPE_MACHINE_NAME`.
- `resolve_local_identity(config) -> tuple[NormalizedUser, NormalizedMachine]`.
- Local user stable key hashes normalized OS username plus a namespace marker; confidence=`inferred`.
- Machine stable key hashes stable host/machine inputs but is kept separate from user key.

- [ ] Write RED tests with monkeypatched username/hostname/platform.
- [ ] Implement deterministic hashing with `sha256` and no raw password/token/environment capture.
- [ ] Verify configured display overrides affect labels only, not stable keys.
- [ ] Run tests and commit.

### Task 5: Attach identity during collection

**Files:**
- Modify: `src/agentscope/importer.py`
- Modify: `src/agentscope/sources/base.py`
- Modify: `tests/unit/test_importer.py`

**Interfaces:**
- Collection request carries optional resolved local user/machine.
- After session upsert, importer associates identity unless adapter supplied exact provider user evidence for that session.

- [ ] Write RED test collecting same fixture on two synthetic machines and assert two machine rows but one configured/inferred user when stable user input matches.
- [ ] Implement association without changing existing session uniqueness.
- [ ] Run importer tests and commit.

### Task 6: User/machine analytics dimensions

**Files:**
- Modify: `src/agentscope/analytics/service.py`
- Modify: `tests/unit/test_analytics.py`

**Interfaces:**
- Add `by_user()` and `by_machine()` returning sessions/input/cached/output/total tokens and nullable costs where attributable.
- Existing `AnalyticsFilter.user` and `.machine` become active predicates.

- [ ] Write RED tests with two users/machines.
- [ ] Implement bound-parameter filters and grouping.
- [ ] Preserve unavailable cost as `None`, not zero.
- [ ] Run tests and commit.

### Task 7: Report/export identity dimensions

**Files:**
- Modify: `src/agentscope/reporting/html_report.py`
- Modify: `src/agentscope/reporting/export.py`
- Modify: `src/agentscope/cli.py`
- Modify: `tests/unit/test_reporting.py`
- Modify: `tests/integration/test_cli_flow.py`

- [ ] Write RED assertions for `Usuários` and `Máquinas` report sections and CLI `--user`/`--machine` filters.
- [ ] Render confidence labels where relevant.
- [ ] Include safe identity labels/stable keys in safe exports; do not export raw environment/user-home paths.
- [ ] Run reporting/integration tests and commit.

### Task 8: Full Increment D verification

- [ ] Run `python -m pytest -q`.
- [ ] Open a V1 fixture DB through current code and confirm migration is additive/idempotent.
- [ ] Collect twice and verify no duplicate user/machine rows.
- [ ] Generate filtered user/machine report.
- [ ] Commit docs/status updates.
