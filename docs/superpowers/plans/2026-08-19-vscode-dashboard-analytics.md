# AgentScope VS Code Dashboard Analytics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the local VS Code dashboard reliable for historical user/machine filtering, explicit observed/estimated monetary metrics, responsive presentation, and filter-aware trend/breakdown charts.

**Architecture:** Python remains the source of truth for identity maintenance and analytics. A versioned privacy-safe snapshot v2 carries summary, availability, daily series, and breakdown data to the TypeScript extension; the webview only formats and renders that contract and never queries SQLite directly.

**Tech Stack:** Python 3.11+, Typer, SQLite, pytest, TypeScript 5.x, VS Code Extension API, vanilla HTML/CSS/JavaScript, local SVG chart rendering, Mocha, `@vscode/test-cli`, `@vscode/test-electron`.

**Spec:** `docs/superpowers/specs/2026-08-19-vscode-dashboard-analytics-design.md`

## Global Constraints

- Python remains the source of truth; TypeScript must not query SQLite directly.
- No Team UI, central/shared API, cross-machine synchronization, Marketplace/VSIX work, or developer productivity scoring in this increment.
- Unknown monetary values remain `null`, never `0`.
- `observed_cost_usd`, `estimated_cost_usd`, and `estimated_savings_usd` are distinct concepts and must be labeled accordingly.
- Snapshot schema remains `agentscope-extension-snapshot` and version becomes `2`.
- No prompt bodies, assistant responses, source code, raw provider payloads, secrets, attachments, or full provider paths may enter the extension snapshot or webview messages.
- Existing filters remain: `today`, `7d`, `30d`, `month`, custom dates, project, model, source, user, and machine.
- All chart data must honor the same active filters as summary metrics.
- Empty filtered results are valid results, not exceptions.
- Webview CSP remains restrictive; no CDN or remote scripts.
- TDD is required for every task.
- Before completion run `python -m pytest -q`, `npm run compile`, `npm run test:unit`, and `npm test`.

---

## File map

### Python identity maintenance

- `src/agentscope/identity_backfill.py` — new orchestration service for idempotent historical identity repair and result counts.
- `src/agentscope/cli.py` — registers `agentscope identity backfill` and maps CLI options to the service.
- `tests/unit/test_identity_backfill.py` — service-level backfill tests.
- `tests/integration/test_identity_cli.py` — CLI-level backfill and filter regression tests.

### Python analytics/snapshot

- `src/agentscope/analytics/service.py` — adds/normalizes filter-aware daily metrics, source breakdown, and total-token fields used by the dashboard.
- `src/agentscope/extension/contracts.py` — snapshot v2 dataclasses and availability/series/breakdown types.
- `src/agentscope/extension/snapshot.py` — maps AnalyticsService outputs into privacy-safe snapshot v2 and availability reason codes.
- `tests/unit/test_analytics.py` — daily/breakdown/cost semantics tests.
- `tests/unit/test_extension_snapshot.py` — snapshot v2, null semantics, filter, and privacy tests.
- `tests/integration/test_extension_cli.py` — machine-readable CLI contract v2 regression.

### VS Code extension

- `vscode-extension/src/contracts/snapshot.ts` — TypeScript snapshot v2 types and runtime validator.
- `vscode-extension/src/views/dashboardViewModel.ts` — formatting, availability copy, and chart-safe view model transformation.
- `vscode-extension/src/views/dashboardViewProvider.ts` — dashboard semantic regions and webview bridge.
- `vscode-extension/media/dashboard.js` — DOM rendering, valid filter submission, empty/loading/error states, and local SVG charts.
- `vscode-extension/media/dashboard.css` — modern responsive grid, cards, filters, states, and chart styling.
- `vscode-extension/src/test/unit/snapshot.test.ts` — parser v2 and null preservation tests.
- `vscode-extension/src/test/unit/dashboardViewModel.test.ts` — monetary labels, reason copy, chart conversion, and empty-state tests.
- `vscode-extension/src/test/unit/filterState.test.ts` — user/machine filter transition regression.
- `vscode-extension/src/test/suite/extension.test.ts` — activation/contribution smoke regression.
- `README.md` — documents identity backfill and dashboard v2 semantics.

---

### Task 1: Identity backfill service and CLI

**Files:**
- Create: `src/agentscope/identity_backfill.py`
- Modify: `src/agentscope/cli.py`
- Create: `tests/unit/test_identity_backfill.py`
- Modify: `tests/integration/test_identity_cli.py`

**Interfaces:**
- Consumes: `AgentScopeConfig`, `Repository`, `collect_registered_sources(..., full_rescan=True)`.
- Produces: `IdentityBackfillSummary(sessions_scanned: int, sessions_updated: int, sessions_without_user: int, sessions_without_machine: int, errors: int)`.
- Produces: `backfill_local_identity(repository: Repository, config: AgentScopeConfig, *, sources: frozenset[str] | None = None) -> IdentityBackfillSummary`.
- Produces CLI: `agentscope identity backfill [--database PATH] [--source NAME] [--user-name NAME] [--machine-name NAME]`.

- [ ] **Step 1: Write the failing service test for historical sessions**

Create `tests/unit/test_identity_backfill.py` using a temporary Codex fixture. First import the fixture without attaching identity by calling the current collector/import path directly or by nulling the imported session identity in the test database, then invoke the new service:

```python
summary = backfill_local_identity(
    repo,
    AgentScopeConfig.from_env(
        codex_home=codex_home,
        database_path=db.path,
        enabled_sources={"codex"},
        user_display_name="Dev A",
        machine_display_name="Notebook A",
    ),
    sources=frozenset({"codex"}),
)

assert summary.sessions_scanned == 1
assert summary.sessions_updated == 1
assert summary.sessions_without_user == 0
assert summary.sessions_without_machine == 0
assert summary.errors == 0

with repo.database.connect() as conn:
    row = conn.execute(
        """
        SELECT COALESCE(u.display_name, u.stable_key) AS user_name,
               COALESCE(m.display_name, m.stable_key) AS machine_name
        FROM sessions s
        LEFT JOIN users u ON u.id=s.user_id
        LEFT JOIN machines m ON m.id=s.machine_id
        """
    ).fetchone()
assert row["user_name"] == "Dev A"
assert row["machine_name"] == "Notebook A"
```

- [ ] **Step 2: Run the service test to verify RED**

Run:

```bash
python -m pytest tests/unit/test_identity_backfill.py -q
```

Expected: FAIL because `agentscope.identity_backfill` does not exist.

- [ ] **Step 3: Implement the backfill summary and scoped identity counts**

Create `src/agentscope/identity_backfill.py` with:

```python
from __future__ import annotations

from dataclasses import dataclass, replace

from agentscope.config import AgentScopeConfig
from agentscope.importer import collect_registered_sources
from agentscope.storage.repository import Repository


@dataclass(frozen=True, slots=True)
class IdentityBackfillSummary:
    sessions_scanned: int
    sessions_updated: int
    sessions_without_user: int
    sessions_without_machine: int
    errors: int


def _identity_counts(
    repository: Repository,
    sources: frozenset[str] | None,
) -> tuple[int, int, int, int]:
    clauses: list[str] = []
    params: list[object] = []
    if sources:
        placeholders = ",".join("?" for _ in sources)
        clauses.append(f"src.name IN ({placeholders})")
        params.extend(sorted(sources))
    where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
    with repository.database.connect() as conn:
        row = conn.execute(
            """
            SELECT COUNT(*) AS total,
                   SUM(CASE WHEN s.user_id IS NULL THEN 1 ELSE 0 END) AS no_user,
                   SUM(CASE WHEN s.machine_id IS NULL THEN 1 ELSE 0 END) AS no_machine,
                   SUM(CASE WHEN s.user_id IS NULL OR s.machine_id IS NULL THEN 1 ELSE 0 END) AS incomplete
            FROM sessions s
            JOIN sources src ON src.id=s.source_id
            """ + where,
            params,
        ).fetchone()
    return (
        int(row["total"] or 0),
        int(row["no_user"] or 0),
        int(row["no_machine"] or 0),
        int(row["incomplete"] or 0),
    )


def backfill_local_identity(
    repository: Repository,
    config: AgentScopeConfig,
    *,
    sources: frozenset[str] | None = None,
) -> IdentityBackfillSummary:
    active_sources = sources if sources is not None else config.enabled_sources
    before_total, _, _, before_incomplete = _identity_counts(repository, active_sources)
    scoped_config = replace(config, enabled_sources=active_sources)
    collected = collect_registered_sources(
        repository,
        scoped_config,
        full_rescan=True,
        progress=None,
    )
    _, after_no_user, after_no_machine, after_incomplete = _identity_counts(
        repository,
        active_sources,
    )
    return IdentityBackfillSummary(
        sessions_scanned=before_total,
        sessions_updated=max(0, before_incomplete - after_incomplete),
        sessions_without_user=after_no_user,
        sessions_without_machine=after_no_machine,
        errors=collected.errors,
    )
```

Keep this service limited to orchestration/counting; do not duplicate adapter import logic.

- [ ] **Step 4: Run the service test to verify GREEN**

Run:

```bash
python -m pytest tests/unit/test_identity_backfill.py -q
```

Expected: PASS.

- [ ] **Step 5: Add the idempotency test**

Append:

```python
first = backfill_local_identity(repo, config, sources=frozenset({"codex"}))
second = backfill_local_identity(repo, config, sources=frozenset({"codex"}))

assert first.sessions_updated == 1
assert second.sessions_updated == 0
with repo.database.connect() as conn:
    assert conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM machines").fetchone()[0] == 1
```

- [ ] **Step 6: Register the `identity` Typer sub-app and command**

Modify `src/agentscope/cli.py`:

```python
from agentscope.identity_backfill import backfill_local_identity

identity_app = typer.Typer(help="Identity maintenance commands.")
app.add_typer(identity_app, name="identity")


@identity_app.command("backfill")
def identity_backfill(
    database: Optional[Path] = typer.Option(None, "--database"),
    source: Optional[str] = typer.Option(None, "--source"),
    user_name: Optional[str] = typer.Option(None, "--user-name"),
    machine_name: Optional[str] = typer.Option(None, "--machine-name"),
) -> None:
    config = AgentScopeConfig.from_env(
        database_path=database,
        enabled_sources={source} if source else None,
        user_display_name=user_name,
        machine_display_name=machine_name,
    )
    repo = _repository(config.database_path)
    summary = backfill_local_identity(
        repo,
        config,
        sources=frozenset({source}) if source else None,
    )
    typer.echo(
        f"sessions_scanned={summary.sessions_scanned} "
        f"sessions_updated={summary.sessions_updated} "
        f"sessions_without_user={summary.sessions_without_user} "
        f"sessions_without_machine={summary.sessions_without_machine} "
        f"errors={summary.errors}"
    )
    if summary.errors:
        raise typer.Exit(code=1)
```

- [ ] **Step 7: Add CLI integration coverage**

Extend `tests/integration/test_identity_cli.py` with a test that creates a historical Codex session with null identity, invokes:

```python
result = runner.invoke(
    app,
    [
        "identity", "backfill",
        "--database", str(db),
        "--source", "codex",
        "--user-name", "Dev A",
        "--machine-name", "Notebook A",
    ],
    env={"AGENTSCOPE_CODEX_HOME": str(codex_home)},
)
```

Assert exit code `0`, output contains `sessions_updated=1`, and subsequent `analyze --user "Dev A" --machine "Notebook A"` reports non-zero tokens.

- [ ] **Step 8: Run identity regression tests**

Run:

```bash
python -m pytest tests/unit/test_identity_backfill.py tests/integration/test_identity_cli.py tests/unit/test_identity.py tests/unit/test_identity_repository.py tests/unit/test_identity_analytics.py -q
```

Expected: PASS.

- [ ] **Step 9: Commit Task 1**

```bash
git add src/agentscope/identity_backfill.py src/agentscope/cli.py tests/unit/test_identity_backfill.py tests/integration/test_identity_cli.py
git commit -m "feat: add historical identity backfill"
```

---

### Task 2: Analytics primitives for dashboard trends and breakdowns

**Files:**
- Modify: `src/agentscope/analytics/service.py`
- Modify: `tests/unit/test_analytics.py`

**Interfaces:**
- Consumes: existing `AnalyticsFilter` and current normalized tables.
- Produces: `AnalyticsService.by_day() -> list[dict[str, Any]]` with `date`, `sessions`, `total_tokens`, `cache_ratio`, `observed_cost_usd`, `estimated_cost_usd`, `estimated_savings_usd`.
- Produces: `AnalyticsService.by_source() -> list[dict[str, Any]]` with `source`, `sessions`, `total_tokens`.
- Extends: `by_project()` and `by_model()` rows with `total_tokens` while preserving existing fields.

- [ ] **Step 1: Write failing daily-series tests**

In `tests/unit/test_analytics.py`, insert synthetic sessions/token/cost rows across two dates and assert:

```python
rows = AnalyticsService(repo, AnalyticsFilter()).by_day()
assert rows == [
    {
        "date": "2026-08-18",
        "sessions": 1,
        "total_tokens": 150,
        "cache_ratio": 0.8,
        "observed_cost_usd": 0.12,
        "estimated_cost_usd": 0.20,
        "estimated_savings_usd": 0.08,
    },
    {
        "date": "2026-08-19",
        "sessions": 1,
        "total_tokens": 300,
        "cache_ratio": 0.5,
        "observed_cost_usd": None,
        "estimated_cost_usd": None,
        "estimated_savings_usd": None,
    },
]
```

Use values where cached/input ratio is unambiguous. The implementation must not convert missing monetary rows to zero.

- [ ] **Step 2: Write failing filter tests for daily and breakdown data**

Add data for two projects/sources/models/users/machines, then assert a combined filter returns only the matching date rows and breakdown entries:

```python
filters = AnalyticsFilter(
    from_date=date(2026, 8, 18),
    to_date=date(2026, 8, 18),
    project="Project A",
    model="gpt-5.6-sol",
    source="codex",
    user="Dev A",
    machine="Notebook A",
)
analytics = AnalyticsService(repo, filters)
assert {row["source"] for row in analytics.by_source()} == {"codex"}
assert {row["project"] for row in analytics.by_project()} == {"Project A"}
assert {row["model"] for row in analytics.by_model()} == {"gpt-5.6-sol"}
assert all(row["date"] == "2026-08-18" for row in analytics.by_day())
```

- [ ] **Step 3: Run targeted analytics tests to verify RED**

Run:

```bash
python -m pytest tests/unit/test_analytics.py -q
```

Expected: FAIL on missing/incorrect daily/source fields.

- [ ] **Step 4: Implement `total_tokens` in project/model breakdowns and `by_source()`**

Modify the existing aggregation SQL to include:

```sql
COALESCE(SUM(tu.total_tokens), 0) AS total_tokens
```

Implement `by_source()` using the same `_usage_dimension_where("tu.timestamp")` filter path and grouping by `src.name`.

- [ ] **Step 5: Implement `by_day()` with independent usage and monetary aggregation merged by date**

Do not join `token_usage` directly to `costs`, because that multiplies rows. Query usage and monetary aggregates separately and merge by ISO date in Python. Use `AnalyticsService._where(...)` for every query so project/model/source/user/machine/date semantics remain aligned.

The final row shape must be:

```python
{
    "date": day,
    "sessions": sessions,
    "total_tokens": total_tokens,
    "cache_ratio": (cached_input_tokens / input_tokens) if input_tokens else None,
    "observed_cost_usd": observed_cost,
    "estimated_cost_usd": estimated_raw_cost,
    "estimated_savings_usd": total_savings,
}
```

For savings, treat `NULL` as unavailable unless there is explicit savings evidence in `costs` or `optimizations` for that day. Do not infer `0.0` from absence.

- [ ] **Step 6: Run analytics tests to verify GREEN**

Run:

```bash
python -m pytest tests/unit/test_analytics.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit Task 2**

```bash
git add src/agentscope/analytics/service.py tests/unit/test_analytics.py
git commit -m "feat: add dashboard trend analytics"
```

---

### Task 3: Snapshot contract v2 and monetary availability semantics

**Files:**
- Modify: `src/agentscope/extension/contracts.py`
- Modify: `src/agentscope/extension/snapshot.py`
- Modify: `tests/unit/test_extension_snapshot.py`
- Modify: `tests/integration/test_extension_cli.py`

**Interfaces:**
- Consumes: `AnalyticsService.summary()`, `.by_day()`, `.by_project()`, `.by_model()`, `.by_source()`.
- Produces snapshot schema `agentscope-extension-snapshot`, version `2`.
- Produces `summary.estimated_cost_usd` in addition to existing fields.
- Produces `availability`, `series.daily`, and `breakdowns.projects/models/sources`.

- [ ] **Step 1: Write failing snapshot v2 contract assertions**

Update `tests/unit/test_extension_snapshot.py` to assert:

```python
snapshot = build_extension_snapshot(repo, AnalyticsFilter(), period=None, database_path=db.path)
assert snapshot["version"] == 2
assert snapshot["summary"]["estimated_cost_usd"] == 0.20
assert snapshot["availability"]["observed_cost"] == {"available": True, "reason": None}
assert snapshot["availability"]["estimated_cost"] == {"available": True, "reason": None}
assert snapshot["availability"]["estimated_savings"] == {"available": True, "reason": None}
assert snapshot["series"]["daily"][0]["date"] == "2026-08-18"
assert snapshot["breakdowns"]["projects"][0]["total_tokens"] > 0
```

- [ ] **Step 2: Add null/reason-code cases**

Create three filtered snapshots with no relevant monetary evidence and assert reason codes:

```python
assert snapshot["summary"]["observed_cost_usd"] is None
assert snapshot["availability"]["observed_cost"]["reason"] == "source_does_not_report_cost"
assert snapshot["summary"]["estimated_cost_usd"] is None
assert snapshot["availability"]["estimated_cost"]["reason"] == "insufficient_pricing_data"
assert snapshot["summary"]["estimated_savings_usd"] is None
assert snapshot["availability"]["estimated_savings"]["reason"] == "no_optimization_data"
```

- [ ] **Step 3: Preserve and extend privacy regression**

Keep the existing `PRIVATE_PROMPT_SENTINEL` and provider-path assertions and additionally serialize `series` and `breakdowns` as part of the whole snapshot:

```python
serialized = json.dumps(snapshot, ensure_ascii=False)
assert "PRIVATE_PROMPT_SENTINEL" not in serialized
assert "private\\provider" not in serialized
```

- [ ] **Step 4: Run snapshot tests to verify RED**

Run:

```bash
python -m pytest tests/unit/test_extension_snapshot.py tests/integration/test_extension_cli.py -q
```

Expected: FAIL because contract version is still `1` and new sections do not exist.

- [ ] **Step 5: Extend Python contract dataclasses**

Modify `src/agentscope/extension/contracts.py`:

```python
SNAPSHOT_VERSION = 2

@dataclass(frozen=True, slots=True)
class SnapshotSummary:
    sessions: int
    total_tokens: int
    tokens_saved: int
    cache_ratio: float | None
    observed_cost_usd: float | None
    estimated_cost_usd: float | None
    estimated_savings_usd: float | None

@dataclass(frozen=True, slots=True)
class AvailabilityItem:
    available: bool
    reason: str | None

@dataclass(frozen=True, slots=True)
class SnapshotAvailability:
    observed_cost: AvailabilityItem
    estimated_cost: AvailabilityItem
    estimated_savings: AvailabilityItem
```

Daily rows and breakdown rows may remain dictionaries produced by AnalyticsService; do not introduce dataclasses that duplicate analytics row structures unless validation needs them.

- [ ] **Step 6: Implement snapshot v2 mapping and reason helpers**

In `src/agentscope/extension/snapshot.py`, map:

```python
estimated_cost = summary.estimated_raw_cost_usd
observed_cost = summary.observed_cost_usd
estimated_savings = summary.total_savings_usd if _has_savings_evidence(repository, filters) else None
```

Build availability through a small helper:

```python
def _availability(value: float | None, reason: str) -> dict[str, object]:
    return {"available": value is not None, "reason": None if value is not None else reason}
```

Return:

```python
"availability": {
    "observed_cost": _availability(observed_cost, "source_does_not_report_cost"),
    "estimated_cost": _availability(estimated_cost, "insufficient_pricing_data"),
    "estimated_savings": _availability(estimated_savings, "no_optimization_data"),
},
"series": {"daily": analytics.by_day()},
"breakdowns": {
    "projects": analytics.by_project(),
    "models": analytics.by_model(),
    "sources": analytics.by_source(),
},
```

Keep dimensions allow-listed and do not add paths or raw provider metadata.

- [ ] **Step 7: Update CLI integration expectations**

In `tests/integration/test_extension_cli.py`, assert JSON version `2`, new sections exist, filters still work, and a missing project returns `summary.sessions == 0` with empty chart arrays rather than an exception.

- [ ] **Step 8: Run snapshot + CLI regression tests**

Run:

```bash
python -m pytest tests/unit/test_extension_snapshot.py tests/integration/test_extension_cli.py tests/integration/test_cli_flow.py -q
```

Expected: PASS.

- [ ] **Step 9: Commit Task 3**

```bash
git add src/agentscope/extension/contracts.py src/agentscope/extension/snapshot.py tests/unit/test_extension_snapshot.py tests/integration/test_extension_cli.py
git commit -m "feat: expose dashboard snapshot v2"
```

---

### Task 4: TypeScript snapshot v2 parser and dashboard view model

**Files:**
- Modify: `vscode-extension/src/contracts/snapshot.ts`
- Modify: `vscode-extension/src/views/dashboardViewModel.ts`
- Modify: `vscode-extension/src/test/unit/snapshot.test.ts`
- Modify: `vscode-extension/src/test/unit/dashboardViewModel.test.ts`

**Interfaces:**
- Consumes: Python snapshot v2 JSON.
- Produces: strongly typed `ExtensionSnapshot` version `2`.
- Produces: `DashboardViewModel` containing formatted cards, availability messages, daily chart points, and breakdown chart data.

- [ ] **Step 1: Update unit fixtures to version 2 and write failing parser assertions**

In `snapshot.test.ts`, use a full v2 fixture containing:

```ts
summary: {
  sessions: 17,
  total_tokens: 477728693,
  tokens_saved: 2118257,
  cache_ratio: 0.9473,
  observed_cost_usd: 15.35,
  estimated_cost_usd: 21.03,
  estimated_savings_usd: 5.68,
},
availability: {
  observed_cost: { available: true, reason: null },
  estimated_cost: { available: true, reason: null },
  estimated_savings: { available: true, reason: null },
},
series: {
  daily: [{
    date: '2026-08-19', sessions: 2, total_tokens: 1200, cache_ratio: 0.8,
    observed_cost_usd: null, estimated_cost_usd: 0.03, estimated_savings_usd: null,
  }],
},
breakdowns: {
  projects: [{ project: 'S584', sessions: 2, total_tokens: 1200 }],
  models: [{ model: 'gpt-5.6-sol', sessions: 2, total_tokens: 1200 }],
  sources: [{ source: 'codex', sessions: 2, total_tokens: 1200 }],
},
```

Assert null monetary values remain `null` after parsing.

- [ ] **Step 2: Run TypeScript unit tests to verify RED**

Run:

```bash
cd vscode-extension
npm run compile
npm run test:unit
```

Expected: FAIL because parser only accepts version `1` and old fields.

- [ ] **Step 3: Implement v2 TypeScript types and runtime validation**

Add:

```ts
export type AvailabilityReason =
  | 'source_does_not_report_cost'
  | 'insufficient_pricing_data'
  | 'no_optimization_data';

export interface AvailabilityItem {
  available: boolean;
  reason: AvailabilityReason | null;
}

export interface DailySeriesPoint {
  date: string;
  sessions: number;
  total_tokens: number;
  cache_ratio: number | null;
  observed_cost_usd: number | null;
  estimated_cost_usd: number | null;
  estimated_savings_usd: number | null;
}
```

Set `ExtensionSnapshot.version` to literal `2`, require `availability`, `series`, and `breakdowns`, and validate every numeric-or-null field with `isNumberOrNull`. Reject version `1` with `SNAPSHOT_UNSUPPORTED_VERSION`.

- [ ] **Step 4: Extend the view model and reason-copy mapping**

Modify `dashboardViewModel.ts` so `DashboardCards` includes `estimatedCost`. Add subtitles/reasons separately from display values:

```ts
export interface DashboardMetric {
  value: string;
  subtitle?: string;
}
```

Map reason codes:

```ts
const availabilityCopy = {
  source_does_not_report_cost: 'A fonte selecionada não informa custo monetário observado.',
  insufficient_pricing_data: 'Não há dados de preço suficientes para esta seleção.',
  no_optimization_data: 'Não há dados de otimização suficientes para esta seleção.',
} as const;
```

Do not call `formatUsd(0)` for unavailable metrics; preserve the `Não disponível` display.

- [ ] **Step 5: Add chart-safe transformation tests**

In `dashboardViewModel.test.ts`, assert:

```ts
const vm = toDashboardViewModel(snapshot, { period: '7d' });
assert.strictEqual(vm.cards.estimatedCost.value, 'US$ 21,03');
assert.strictEqual(vm.series.daily[0].observedCostUsd, null);
assert.strictEqual(vm.breakdowns.projects[0].label, 'S584');
assert.strictEqual(vm.breakdowns.projects[0].totalTokens, 1200);
```

For unavailable values assert both `Não disponível` and the expected explanatory subtitle.

- [ ] **Step 6: Run TypeScript unit tests to verify GREEN**

Run:

```bash
npm run compile
npm run test:unit
```

Expected: PASS.

- [ ] **Step 7: Commit Task 4**

```bash
git add vscode-extension/src/contracts/snapshot.ts vscode-extension/src/views/dashboardViewModel.ts vscode-extension/src/test/unit/snapshot.test.ts vscode-extension/src/test/unit/dashboardViewModel.test.ts
git commit -m "feat: consume dashboard snapshot v2"
```

---

### Task 5: Valid filter behavior and explicit UI states

**Files:**
- Modify: `vscode-extension/src/state/filterState.ts`
- Modify: `vscode-extension/src/services/dashboardCoordinator.ts`
- Modify: `vscode-extension/src/test/unit/filterState.test.ts`
- Modify: `vscode-extension/src/views/dashboardViewProvider.ts`

**Interfaces:**
- Consumes: current snapshot dimensions and filter state.
- Produces: user/machine filter values only from current snapshot dimension lists.
- Produces UI message states: `loading`, `snapshot`, `error` with empty result handled inside the snapshot view model.

- [ ] **Step 1: Write regression tests for user/machine transitions**

Extend `filterState.test.ts` to verify:

```ts
state.patch({ user: 'Dev A', machine: 'Notebook A' });
assert.strictEqual(state.current.user, 'Dev A');
assert.strictEqual(state.current.machine, 'Notebook A');
state.patch({ user: null });
assert.strictEqual(state.current.user, null);
assert.strictEqual(state.current.machine, 'Notebook A');
```

Also test that applying a new snapshot whose dimensions no longer contain the selected user/machine clears those stale selections before the next CLI refresh.

- [ ] **Step 2: Run unit tests to verify RED for stale-dimension handling**

Run:

```bash
cd vscode-extension
npm run compile
npm run test:unit
```

Expected: FAIL on the new stale-dimension behavior.

- [ ] **Step 3: Add a dimension reconciliation helper**

Implement a pure helper, either in `filterState.ts` or a focused sibling file, with this behavior:

```ts
export function reconcileDimensionFilters(
  filters: SnapshotFilters,
  dimensions: SnapshotDimensions,
): SnapshotFilters {
  return {
    ...filters,
    project: filters.project && dimensions.projects.includes(filters.project) ? filters.project : null,
    model: filters.model && dimensions.models.includes(filters.model) ? filters.model : null,
    source: filters.source && dimensions.sources.includes(filters.source) ? filters.source : null,
    user: filters.user && dimensions.users.includes(filters.user) ? filters.user : null,
    machine: filters.machine && dimensions.machines.includes(filters.machine) ? filters.machine : null,
  };
}
```

Use this only after a successful snapshot. Do not invent dimension values client-side.

- [ ] **Step 4: Make provider markup expose explicit regions**

Modify `dashboardViewProvider.ts` HTML to include semantic containers:

```html
<section id="filters" class="filters" aria-label="Filtros"></section>
<section id="status" class="status" aria-live="polite"></section>
<section id="cards" class="cards" aria-label="Indicadores"></section>
<section id="trends" class="chart-grid" aria-label="Tendências"></section>
<section id="breakdowns" class="chart-grid" aria-label="Distribuições"></section>
<section id="notes" class="notes" aria-label="Disponibilidade dos dados"></section>
```

CSP remains unchanged except for local extension resources already allowed.

- [ ] **Step 5: Run TypeScript tests**

Run:

```bash
npm run compile
npm run test:unit
```

Expected: PASS.

- [ ] **Step 6: Commit Task 5**

```bash
git add vscode-extension/src/state/filterState.ts vscode-extension/src/services/dashboardCoordinator.ts vscode-extension/src/test/unit/filterState.test.ts vscode-extension/src/views/dashboardViewProvider.ts
git commit -m "fix: keep dashboard filters aligned with snapshot dimensions"
```

---

### Task 6: Responsive dashboard redesign and local SVG charts

**Files:**
- Modify: `vscode-extension/media/dashboard.js`
- Modify: `vscode-extension/media/dashboard.css`
- Modify: `vscode-extension/src/views/dashboardViewProvider.ts`
- Modify: `vscode-extension/src/test/unit/dashboardViewModel.test.ts`

**Interfaces:**
- Consumes: `DashboardViewModel` only.
- Produces: responsive KPI/filter/chart DOM with no analytics calculations beyond visual scaling.
- Produces seven required charts: sessions/day, tokens/day, observed cost vs estimated savings/day, cache ratio trend, usage by project, usage by model, usage by source.

- [ ] **Step 1: Add render-ready chart assertions in the view-model test**

Ensure the view model exposes data in stable display shapes:

```ts
assert.deepStrictEqual(vm.series.daily[0], {
  date: '2026-08-19',
  sessions: 2,
  totalTokens: 1200,
  cacheRatio: 0.8,
  observedCostUsd: null,
  estimatedCostUsd: 0.03,
  estimatedSavingsUsd: null,
});
assert.deepStrictEqual(vm.breakdowns.sources[0], {
  label: 'codex',
  sessions: 2,
  totalTokens: 1200,
});
```

- [ ] **Step 2: Implement modern responsive CSS grid**

Replace the fixed/simple styling with theme-native responsive rules. Use no hardcoded colors; use VS Code variables:

```css
body {
  margin: 0;
  padding: clamp(12px, 2vw, 24px);
  color: var(--vscode-editor-foreground);
  background: var(--vscode-editor-background);
}

.toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 16px;
}

.dimension-grid,
.cards,
.chart-grid {
  display: grid;
  gap: 12px;
}

.dimension-grid {
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
}

.cards {
  grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
}

.chart-grid {
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 320px), 1fr));
  margin-top: 16px;
}

@media (max-width: 520px) {
  body { padding: 10px; }
  .toolbar-actions, .period-row, .date-row { width: 100%; }
  .date-row > input, .date-row > button { flex: 1 1 100%; }
  .cards, .chart-grid, .dimension-grid { grid-template-columns: 1fr; }
}
```

Cards/charts must use `var(--vscode-panel-border)`, `var(--vscode-sideBarSectionHeader-background)`, `var(--vscode-descriptionForeground)`, and `var(--vscode-focusBorder)` so light/dark/high-contrast themes remain usable.

- [ ] **Step 3: Render seven KPI cards with value/subtitle separation**

In `dashboard.js`, change card definitions to include `estimatedCost`, and render subtitles only when present. Required labels:

```js
[
  ['sessions', 'Sessões'],
  ['totalTokens', 'Total de tokens'],
  ['tokensSaved', 'Tokens economizados'],
  ['cacheRatio', 'Taxa de cache'],
  ['observedCost', 'Custo observado'],
  ['estimatedCost', 'Custo estimado'],
  ['estimatedSavings', 'Economia estimada'],
]
```

- [ ] **Step 4: Add a small local SVG line-chart renderer**

Implement in `dashboard.js` without remote dependencies:

```js
function renderLineChart(title, points, seriesDefs) {
  const article = document.createElement('article');
  article.className = 'chart-card';
  // Build an SVG with viewBox="0 0 640 240".
  // Use CSS classes for strokes/fills so colors come from VS Code theme variables.
  // Skip null values instead of converting them to zero.
  // Show an empty-state paragraph when no plottable values exist.
  return article;
}
```

The renderer may compute pixel positions for presentation only. It must not compute business aggregates.

- [ ] **Step 5: Add a local horizontal breakdown chart renderer**

Implement:

```js
function renderBreakdownChart(title, rows) {
  const top = rows.slice(0, 8);
  const max = Math.max(...top.map((row) => row.totalTokens), 0);
  // Render label, formatted total token count, and proportional bar.
  // If max === 0, render an empty-state paragraph.
}
```

Use the top eight entries to keep the panel readable; the underlying snapshot retains the full filtered breakdown.

- [ ] **Step 6: Render required trend charts**

Use the daily series to render:

```text
Sessões por dia
Tokens por dia
Custo observado × economia estimada
Taxa de cache
```

The monetary chart must skip `null` values. The cache chart displays ratios as percentages in labels/tooltips/accessible text.

- [ ] **Step 7: Render required breakdown charts**

Use:

```text
Uso por projeto
Uso por modelo
Uso por fonte
```

Measure: `totalTokens` only, clearly labeled `tokens` in the chart copy.

- [ ] **Step 8: Implement loading, error, empty, and availability states**

For messages:

```js
if (message.type === 'loading') {
  status.textContent = 'Carregando dados do AgentScope...';
  cards.replaceChildren();
  trends.replaceChildren();
  breakdowns.replaceChildren();
}
```

For empty snapshots show:

```text
Nenhum dado encontrado para os filtros selecionados.
```

For monetary unavailability, keep the card in place and show its reason subtitle; do not hide the card.

- [ ] **Step 9: Run extension checks**

Run:

```bash
cd vscode-extension
npm run compile
npm run test:unit
npm test
```

Expected: PASS.

- [ ] **Step 10: Commit Task 6**

```bash
git add vscode-extension/media/dashboard.js vscode-extension/media/dashboard.css vscode-extension/src/views/dashboardViewProvider.ts vscode-extension/src/views/dashboardViewModel.ts vscode-extension/src/test/unit/dashboardViewModel.test.ts
git commit -m "feat: redesign responsive analytics dashboard"
```

---

### Task 7: End-to-end regression, docs, and acceptance verification

**Files:**
- Modify: `README.md`
- Modify only if tests reveal a defect: files from Tasks 1–6.

**Interfaces:**
- Consumes all previous task outputs.
- Produces documented operational workflow and verified release candidate for this increment.

- [ ] **Step 1: Document backfill workflow**

Add to `README.md`:

```powershell
agentscope identity backfill `
  --source codex `
  --user-name "Peterson Benhame" `
  --machine-name "Brain-Storm"
```

Document that `collect --full-rescan` remains valid, while `identity backfill` exists specifically to repair historical identity associations.

- [ ] **Step 2: Document monetary semantics**

State explicitly:

```text
Custo observado = explicit source-reported monetary cost when available.
Custo estimado = theoretical pricing-table calculation, not provider billing.
Economia estimada = supported cache/optimization savings estimate.
Unknown values remain unavailable rather than zero.
```

- [ ] **Step 3: Document snapshot v2/dashboard charts**

Update the VS Code section to mention version `2`, the seven KPI cards, the seven required charts, and responsive behavior. Keep Team UI/API marked as deferred.

- [ ] **Step 4: Run the full Python regression suite**

Run:

```bash
python -m pytest -q
```

Expected: all tests PASS.

- [ ] **Step 5: Run the full extension verification**

Run:

```bash
cd vscode-extension
npm run compile
npm run test:unit
npm test
```

Expected: all commands exit `0`.

- [ ] **Step 6: Run a real local backfill smoke test**

From the repository root, with a backup of the real local database already created by the operator, run:

```powershell
.\.venv\Scripts\agentscope.exe identity backfill `
  --source codex `
  --user-name "Peterson Benhame" `
  --machine-name "Brain-Storm"
```

Then validate:

```powershell
.\.venv\Scripts\agentscope.exe extension snapshot --json --user "Peterson Benhame" --machine "Brain-Storm" --period 7d
```

Acceptance: snapshot version `2`, matching filtered sessions/tokens, and no CLI error.

- [ ] **Step 7: Verify identity completeness against the local database**

Run:

```powershell
python -c "import sqlite3; c=sqlite3.connect(r'data\agentscope.db'); print(c.execute('SELECT COUNT(*) AS total, SUM(user_id IS NOT NULL) AS com_usuario, SUM(machine_id IS NOT NULL) AS com_maquina FROM sessions').fetchone())"
```

Record the result in the task/PR notes. Do not require all providers to have identity if a provider format cannot produce/import a session; the relevant requirement is that reprocessed supported historical sessions receive current local identity.

- [ ] **Step 8: Manual VS Code visual acceptance**

Press `F5`, open AgentScope, and verify at minimum these widths by resizing the side panel:

```text
~400 px: one-column filters/cards/charts without horizontal overflow
~700 px: mixed two-column cards/charts
>1000 px: multi-column KPI/filter layout
```

Verify user/machine filtering, date filtering, null cost cards, all seven charts, loading state, empty state, and refresh.

- [ ] **Step 9: Commit documentation/final adjustments**

```bash
git add README.md
git commit -m "docs: document dashboard analytics and identity backfill"
```

---

## Final acceptance checklist

- [ ] Historical supported sessions can receive user/machine identity without duplicate sessions.
- [ ] Running identity backfill twice is idempotent.
- [ ] User and machine filters return correct analytics after backfill.
- [ ] Snapshot version is `2` and the TypeScript parser rejects unsupported versions.
- [ ] Observed cost, estimated cost, and estimated savings remain separate.
- [ ] Missing monetary values remain `null` end-to-end.
- [ ] Availability reason codes render explanatory UI copy.
- [ ] Daily series honors all active filters.
- [ ] Project/model/source breakdowns honor all active filters.
- [ ] Dashboard provides all seven KPI cards.
- [ ] Dashboard provides all seven required charts.
- [ ] Narrow and wide VS Code layouts do not horizontally overflow.
- [ ] Empty/loading/error states remain explicit.
- [ ] Privacy sentinel tests pass.
- [ ] No Team UI or central API is introduced.
- [ ] `python -m pytest -q` passes.
- [ ] `npm run compile` passes.
- [ ] `npm run test:unit` passes.
- [ ] `npm test` passes.
