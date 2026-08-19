# AgentScope Source Adapter Framework Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace hard-coded source orchestration with a provider-neutral adapter registry while preserving Codex/Headroom behavior, progress, idempotency, and read-only semantics.

**Architecture:** Provider parsers stay isolated. A `SourceAdapter` protocol exposes discovery, capabilities, and collection. `SourceRegistry` orchestrates enabled adapters and `collect_sources` becomes a thin compatibility façade over the registry.

**Tech Stack:** Python 3.11+, Protocol/dataclasses, pathlib, sqlite3, Typer, pytest.

**Spec:** `docs/superpowers/specs/2026-08-18-multi-source-team-analytics-design.md` — Increment C.

## Global Constraints

- Existing Codex and Headroom normalized data and import keys must remain compatible.
- Progress events stay provider-neutral.
- One adapter failure must not corrupt successful imports from other adapters.
- Source files remain read-only.
- Disabled adapters are not discovered or collected.
- TDD is required.

---

### Task 1: Define adapter contracts

**Files:**
- Create: `src/agentscope/sources/base.py`
- Create: `src/agentscope/sources/__init__.py`
- Create: `tests/unit/test_source_contracts.py`

**Interfaces:**
- `SourceCapabilities(sessions: bool=False, messages: bool=False, tokens: bool=False, cache: bool=False, costs: bool=False, tools: bool=False, agents: bool=False, skills: bool=False, optimizations: bool=False, user_identity: bool=False)`
- `SourceDiscovery(source: str, detected: bool, roots: tuple[Path, ...]=(), format_version: str|None=None, artifacts: tuple[Path, ...]=(), diagnostic: str|None=None)`
- `DiscoveryContext(user_home: Path, overrides: dict[str, Path])`
- `CollectRequest(repository: Repository, discovery: SourceDiscovery, full_rescan: bool=False, progress: ProgressCallback|None=None)`
- `SourceAdapter` protocol with `source_name`, `discover`, `capabilities`, `collect`.

- [ ] Write import/contract RED tests.
- [ ] Implement frozen/slots dataclasses and protocol.
- [ ] Run `python -m pytest tests/unit/test_source_contracts.py -q` and verify GREEN.
- [ ] Commit.

### Task 2: Add SourceRegistry and enable/disable behavior

**Files:**
- Create: `src/agentscope/sources/registry.py`
- Modify: `src/agentscope/config.py`
- Modify: `tests/unit/test_config.py`
- Create: `tests/unit/test_source_registry.py`

**Interfaces:**
- `SourceRegistry(adapters: Iterable[SourceAdapter])`
- `discover(context, enabled_sources: set[str]|None=None) -> list[SourceDiscovery]`
- `collect(request_factory, enabled_sources=None) -> CollectionSummary`
- Config adds `enabled_sources: frozenset[str] | None` parsed from `AGENTSCOPE_SOURCES` comma-separated values; unset means all registered adapters enabled.

- [ ] Write RED tests for adapter ordering, disabled adapter not called, and unknown configured source producing clear error.
- [ ] Implement registry and config parsing.
- [ ] Verify tests and commit.

### Task 3: Wrap Codex collector as CodexAdapter

**Files:**
- Create: `src/agentscope/sources/codex.py`
- Modify: `src/agentscope/collectors/codex.py` only if extraction of reusable parse functions is required.
- Modify: `tests/unit/test_codex_collector.py`
- Create: `tests/unit/test_codex_adapter.py`

**Interfaces:**
- `CodexAdapter.source_name == "codex"`
- `discover()` finds `<codex_home>/sessions/**/*.jsonl` using override or default `~/.codex`.
- `capabilities()` declares current V1-supported capabilities only.
- `collect()` delegates to existing parser/repository persistence without changing event keys.

- [ ] Write RED adapter discovery/capability tests.
- [ ] Implement adapter wrapper.
- [ ] Run collector + adapter tests and verify totals unchanged.
- [ ] Commit.

### Task 4: Wrap Headroom collector as HeadroomAdapter

**Files:**
- Create: `src/agentscope/sources/headroom.py`
- Modify: `src/agentscope/collectors/headroom.py` only if reusable entry points are needed.
- Create: `tests/unit/test_headroom_adapter.py`
- Modify: `tests/unit/test_headroom_collector.py`

**Interfaces:**
- `HeadroomAdapter.source_name == "headroom"`
- Discovery includes known supported state files only.
- Capabilities include optimizations/cache/costs; `agents=False`.
- Lifetime snapshot replacement semantics remain unchanged.

- [ ] Write RED discovery/capability tests.
- [ ] Implement wrapper.
- [ ] Run Headroom regression tests, including snapshot replacement.
- [ ] Commit.

### Task 5: Refactor importer orchestration to registry

**Files:**
- Modify: `src/agentscope/importer.py`
- Modify: `tests/unit/test_importer.py`
- Modify: `tests/integration/test_cli_flow.py`

**Interfaces:**
- Preserve public `collect_sources(repo, codex_home=None, headroom_home=None, full_rescan=False, progress=None)` for backward compatibility.
- Add `collect_registered_sources(repo, config, registry=None, full_rescan=False, progress=None) -> CollectionSummary`.

- [ ] Write RED test with two fake adapters where one succeeds and one fails; assert successful data persists and aggregate errors increment.
- [ ] Implement registry-driven collection and progress stages: `discovering`, `source_detected`, `collecting`, `source_complete`, `source_failed`, `complete`.
- [ ] Make compatibility façade build a default config/registry for Codex+Headroom.
- [ ] Verify existing progress/idempotency tests remain GREEN.
- [ ] Commit.

### Task 6: CLI source discovery/status output

**Files:**
- Modify: `src/agentscope/cli.py`
- Modify: `tests/integration/test_cli_flow.py`

- [ ] Write RED integration assertion that `collect` reports detected Codex/Headroom sources without breaking existing progress assertions.
- [ ] Switch CLI collection to `collect_registered_sources`.
- [ ] Add `--sources codex,headroom` override or rely on config helper consistently; document exact behavior.
- [ ] Run integration tests and commit.

### Task 7: Full Increment C verification

- [ ] Run `python -m pytest -q`.
- [ ] Run first and second collection against synthetic fixtures; verify second run does not change logical totals.
- [ ] Verify Headroom is still reported as optimizer, never agent.
- [ ] Verify source files are untouched by comparing fixture hashes before/after smoke run.
- [ ] Commit docs/status updates.
