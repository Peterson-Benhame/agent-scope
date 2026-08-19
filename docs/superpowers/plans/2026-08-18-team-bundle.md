# AgentScope Team Bundle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Export deterministic sanitized team telemetry bundles and import them idempotently into another AgentScope database with provenance and privacy guarantees.

**Architecture:** Team export is allow-list based and serializes only safe normalized metadata. Import validates schema/version before one transaction, maps stable user/machine/source/session/event keys into normalized tables, and records bundle provenance to prevent duplicate totals.

**Tech Stack:** Python 3.11+, json/hashlib/sqlite3, Typer, pytest.

**Spec:** `docs/superpowers/specs/2026-08-18-multi-source-team-analytics-design.md` — Increment F.

## Global Constraints

- No prompt, response, message body, source code, tool payload, attachment, raw source file, environment variable, secret, or unnecessary full path in bundle output.
- Bundle schema: `agentscope-team-bundle`, version `1`.
- Export must be deterministic for identical normalized data except `generated_at`; `bundle_id` derives from canonical safe payload, not random UUID.
- Importing same or regenerated overlapping bundles must not double totals.
- Distinct users/machines must never merge by display name alone.
- TDD is required.

---

### Task 1: Define bundle schema models and canonical serialization

**Files:**
- Create: `src/agentscope/team/bundle.py`
- Create: `src/agentscope/team/__init__.py`
- Create: `tests/unit/test_team_bundle.py`

**Interfaces:**
- Constants `TEAM_BUNDLE_SCHEMA = "agentscope-team-bundle"`, `TEAM_BUNDLE_VERSION = 1`.
- `build_team_bundle(repository: Repository, analytics_filter: AnalyticsFilter|None=None, organization: str|None=None, team: str|None=None) -> dict`.
- `canonical_bundle_payload(bundle: dict) -> bytes` excludes `generated_at` and `bundle_id` before hashing.
- `compute_bundle_id(payload: bytes) -> str` uses SHA-256.

- [ ] Write RED test asserting schema/version/envelope and stable bundle ID for identical safe fixture data.
- [ ] Implement canonical JSON with `sort_keys=True`, compact separators, UTF-8.
- [ ] Run tests and commit.

### Task 2: Implement allow-listed safe record export

**Files:**
- Modify: `src/agentscope/team/bundle.py`
- Modify: `tests/unit/test_team_bundle.py`
- Modify: `tests/fixtures/codex/rollout.jsonl` only if additional sentinels are needed.

**Interfaces:**
- Allowed record groups: users, machines, sessions, token_usage, costs, tools aggregate/calls metadata, agents metadata, optimizations, capability/confidence metadata.
- Project export uses normalized project name/key, not raw full path.

- [ ] Add sentinel values `PROMPT_SECRET`, `SOURCE_CODE_SECRET`, `TOOL_OUTPUT_SECRET`, `ENV_SECRET` to synthetic raw data where appropriate.
- [ ] Write RED test serializing bundle and asserting none of those sentinels nor `C:\\work\\demo` appears.
- [ ] Implement explicit SELECT/field mapping allow lists; do not serialize `metadata_json` wholesale.
- [ ] Verify safe source/model/project/session keys and numeric metrics are present.
- [ ] Run tests and commit.

### Task 3: Add bundle validation

**Files:**
- Create: `src/agentscope/team/validation.py`
- Create: `tests/unit/test_team_validation.py`

**Interfaces:**
- `validate_team_bundle(bundle: dict) -> None` raising `TeamBundleValidationError`.
- Validate schema, version, required envelope keys, record group types, stable identifiers, numeric metric types, and forbidden top-level/message-content fields.

- [ ] Write RED tests for wrong schema, unsupported version, missing stable user/machine key, malformed records, and forbidden `content` field.
- [ ] Implement strict validation with clear error messages.
- [ ] Run tests and commit.

### Task 4: Add team provenance schema migration

**Files:**
- Modify: `src/agentscope/storage/database.py`
- Modify: `tests/unit/test_storage.py`

**Interfaces:**
- Migration creates `team_bundles(bundle_id TEXT UNIQUE, schema_version INTEGER, imported_at TEXT, organization TEXT, team TEXT, metadata_json TEXT)`.
- Create `team_event_provenance(event_key TEXT, bundle_id TEXT, source TEXT, user_key TEXT, machine_key TEXT, PRIMARY KEY(event_key, bundle_id))` or equivalent normalized provenance relation.

- [ ] Write RED migration/idempotency tests.
- [ ] Implement additive migration.
- [ ] Run storage tests and commit.

### Task 5: Implement idempotent team importer

**Files:**
- Create: `src/agentscope/team/importer.py`
- Modify: `tests/unit/test_team_bundle.py`
- Create: `tests/unit/test_team_importer.py`

**Interfaces:**
- `import_team_bundle(repository: Repository, bundle: dict) -> TeamImportSummary`.
- Summary fields: `bundle_id`, `sessions_imported`, `events_imported`, `events_skipped`, `errors`.

- [ ] Write RED test export from source DB -> import to fresh DB -> assert safe totals match.
- [ ] Write RED same-bundle reimport test asserting zero logical count change.
- [ ] Write RED regenerated-overlap test where bundle ID changes because new data was added but old event keys remain; assert only new events increase totals.
- [ ] Validate before transaction.
- [ ] Use stable source/user/machine/session/event keys and existing repository UPSERT/unique constraints.
- [ ] Record provenance only after successful normalized writes within the same transaction boundary.
- [ ] Run tests and commit.

### Task 6: Add `agentscope team export/import` CLI

**Files:**
- Modify: `src/agentscope/cli.py`
- Modify: `tests/integration/test_cli_flow.py`

**Interfaces:**
- Typer sub-app `team`.
- `agentscope team export --output <file> [analytics filters] [--organization X] [--team Y]`.
- `agentscope team import <bundle> --database <db>`.

- [ ] Write RED CLI tests for export file creation and import summary.
- [ ] Implement command handlers using bundle/validation/importer services only.
- [ ] Invalid bundle exits non-zero and leaves database unchanged.
- [ ] Run integration tests and commit.

### Task 7: End-to-end privacy and idempotency verification

**Files:**
- Create: `tests/integration/test_team_bundle_flow.py`

- [ ] Collect synthetic source DB.
- [ ] Export team bundle.
- [ ] Scan raw serialized bytes for all privacy sentinels and full source path; assert absent.
- [ ] Import into fresh team DB.
- [ ] Record analytics totals.
- [ ] Import same bundle again and assert totals unchanged.
- [ ] Export source again after one new safe event, import, and assert only new metrics increase.
- [ ] Run `python -m pytest tests/integration/test_team_bundle_flow.py -q` and commit.

### Task 8: Full Increment F verification and docs

**Files:**
- Modify: `README.md`
- Create: `docs/team-bundle.md`

- [ ] Document schema/version, allowed/forbidden data, export/import commands, idempotency, and privacy guarantees.
- [ ] Run `python -m pytest -q`.
- [ ] Manually inspect one synthetic bundle for no sensitive content.
- [ ] Commit docs and fresh verification.
