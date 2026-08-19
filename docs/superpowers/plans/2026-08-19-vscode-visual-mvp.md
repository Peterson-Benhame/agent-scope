# AgentScope VS Code Visual MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver TASK-001 through TASK-007 so AgentScope appears inside VS Code and renders filtered analytics from an existing AgentScope SQLite database through the Python CLI.

**Architecture:** Python remains the source of truth for analytics and exposes a versioned, allow-listed JSON snapshot command. The VS Code extension is a desktop Node/TypeScript extension that invokes the CLI with argument arrays, validates the snapshot, and renders a Webview View plus lightweight Source/Project Tree Views; it never queries SQLite directly.

**Tech Stack:** Python 3.11+, Typer, SQLite, pytest, TypeScript 5.x, VS Code Extension API, Node.js child_process, vanilla HTML/CSS/JavaScript Webview, Mocha, `@vscode/test-cli`, `@vscode/test-electron`.

**Spec:** `docs/superpowers/specs/2026-08-19-vscode-visual-mvp-design.md`

## Global Constraints

- Scope is TASK-001 through TASK-007 only.
- No direct SQLite access from TypeScript.
- No provider-history access from TypeScript.
- No prompt, response, source-code, tool-payload, attachment, secret, raw provider metadata, or full provider file path in the extension snapshot or Webview messages.
- Unknown monetary values remain `null`, never coerced to zero.
- Snapshot schema is `agentscope-extension-snapshot`, version `1`.
- Python analytics/filter semantics remain the source of truth.
- CLI subprocess arguments are passed as arrays; no shell-concatenated command strings.
- Snapshot timeout is 15 seconds.
- Webview assets are extension-local and guarded by a restrictive Content Security Policy.
- Dashboard supports `today`, `7d`, `30d`, `month`, custom dates, project, model, source, user, and machine filters.
- Extension tests must not depend on real local Codex, Headroom, Claude Code, GitHub Copilot, Kimi, or Gemini installations.
- VS Code Activity Bar is implemented as a View Container; the dashboard is a Webview View inside that container, consistent with current official VS Code UX guidance.
- Extension integration tests use the current official VS Code testing path with `@vscode/test-cli` and `@vscode/test-electron`.

---

## File map

### Python backend

- `src/agentscope/extension/__init__.py` — package marker.
- `src/agentscope/extension/contracts.py` — snapshot dataclasses/serialization-only contract.
- `src/agentscope/extension/snapshot.py` — builds the allow-listed snapshot from Repository + AnalyticsService.
- `src/agentscope/cli.py` — registers `agentscope extension snapshot` and reuses the shared filter builder.
- `tests/unit/test_extension_snapshot.py` — contract, null semantics, dimension lists, privacy.
- `tests/integration/test_extension_cli.py` — CLI JSON contract and filtering against synthetic fixtures.

### VS Code extension

- `vscode-extension/package.json` — extension manifest, commands, views, settings, scripts/dependencies.
- `vscode-extension/tsconfig.json` — TypeScript compilation.
- `vscode-extension/.vscode-test.mjs` — VS Code integration-test configuration.
- `vscode-extension/src/extension.ts` — activation/composition root only.
- `vscode-extension/src/contracts/snapshot.ts` — TypeScript snapshot interfaces and parser/validator.
- `vscode-extension/src/client/agentScopeClient.ts` — process boundary and CLI argument construction.
- `vscode-extension/src/config/settings.ts` — typed VS Code settings access/update.
- `vscode-extension/src/state/filterState.ts` — in-memory filter transitions used by dashboard/tree views.
- `vscode-extension/src/views/dashboardViewProvider.ts` — Webview View provider and host↔webview messaging.
- `vscode-extension/src/views/sourcesViewProvider.ts` — TreeDataProvider for source dimension values.
- `vscode-extension/src/views/projectsViewProvider.ts` — TreeDataProvider for project dimension values.
- `vscode-extension/src/services/dashboardCoordinator.ts` — owns current filters, snapshot refresh, and view synchronization.
- `vscode-extension/media/dashboard.js` — DOM-only rendering/message handling; no analytics calculations.
- `vscode-extension/media/dashboard.css` — VS Code-theme-compatible dashboard styles.
- `vscode-extension/media/agentscope.svg` — monochrome Activity Bar icon.
- `vscode-extension/src/test/unit/snapshot.test.ts` — contract parser tests.
- `vscode-extension/src/test/unit/agentScopeClient.test.ts` — CLI arg/error tests through injected process runner.
- `vscode-extension/src/test/unit/filterState.test.ts` — filter transition tests.
- `vscode-extension/src/test/suite/extension.test.ts` — activation/contribution smoke test.

---

### Task 1: TASK-001 — Python extension snapshot contract

**Files:**
- Create: `src/agentscope/extension/__init__.py`
- Create: `src/agentscope/extension/contracts.py`
- Create: `src/agentscope/extension/snapshot.py`
- Modify: `src/agentscope/cli.py`
- Test: `tests/unit/test_extension_snapshot.py`
- Test: `tests/integration/test_extension_cli.py`

**Interfaces:**
- Consumes: `Repository`, `AnalyticsService(repository, filters)`, `AnalyticsFilter`, current CLI `_analytics_filter(...)`.
- Produces: `build_extension_snapshot(repository: Repository, filters: AnalyticsFilter, *, period: str | None, database_path: Path) -> dict[str, object]`.
- Produces CLI: `agentscope extension snapshot --json [shared filters]`.
- Produces schema: `agentscope-extension-snapshot`, version `1`.

- [ ] **Step 1: Write the failing unit contract test**

Create `tests/unit/test_extension_snapshot.py` with a synthetic repository fixture using `Database(tmp_path / "agentscope.db")` and insert one source/project/model/user/machine/session/token/cost record. Assert:

```python
snapshot = build_extension_snapshot(
    repo,
    AnalyticsFilter(),
    period=None,
    database_path=db.path,
)

assert snapshot["schema"] == "agentscope-extension-snapshot"
assert snapshot["version"] == 1
assert snapshot["summary"]["sessions"] == 1
assert snapshot["summary"]["total_tokens"] == 150
assert snapshot["summary"]["observed_cost_usd"] == 0.12
assert snapshot["dimensions"]["projects"] == ["example-project"]
assert snapshot["dimensions"]["sources"] == ["codex"]
```

Also insert a second session with no cost and assert a filtered snapshot for that session returns `observed_cost_usd is None`, not `0`.

- [ ] **Step 2: Write the privacy regression test**

In the same file, insert a message containing `PRIVATE_PROMPT_SENTINEL` and session `raw_file_path` containing `C:\\private\\provider\\rollout.jsonl`; serialize the snapshot and assert both sentinels are absent:

```python
serialized = json.dumps(snapshot, ensure_ascii=False)
assert "PRIVATE_PROMPT_SENTINEL" not in serialized
assert "C:\\\\private\\provider\\rollout.jsonl" not in serialized
```

- [ ] **Step 3: Run the unit test to verify RED**

Run:

```bash
python -m pytest tests/unit/test_extension_snapshot.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'agentscope.extension'`.

- [ ] **Step 4: Implement the snapshot contract dataclasses**

Create `src/agentscope/extension/contracts.py`:

```python
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


SNAPSHOT_SCHEMA = "agentscope-extension-snapshot"
SNAPSHOT_VERSION = 1


@dataclass(frozen=True, slots=True)
class SnapshotSummary:
    sessions: int
    total_tokens: int
    tokens_saved: int
    cache_ratio: float | None
    observed_cost_usd: float | None
    estimated_savings_usd: float | None


@dataclass(frozen=True, slots=True)
class SnapshotDimensions:
    projects: list[str]
    models: list[str]
    sources: list[str]
    users: list[str]
    machines: list[str]


@dataclass(frozen=True, slots=True)
class SnapshotQuality:
    import_errors: int
    tokens_without_model: int
    identity_confidence: dict[str, int]
    correlation_confidence: dict[str, int]


def to_dict(value: Any) -> dict[str, Any]:
    return asdict(value)
```

Create an empty `src/agentscope/extension/__init__.py`.

- [ ] **Step 5: Implement allow-listed dimension and quality queries**

Create `src/agentscope/extension/snapshot.py` with private helpers that query only normalized labels/counts. Dimension helpers must return sorted unique strings and apply the active date/dimension filters by constructing an `AnalyticsService` for summary semantics and explicit parameterized normalized-table queries for filter-option discovery. Do not read `messages.content`, `metadata_json`, `raw_file_path`, `source_file`, or tool payloads.

Use these public semantics:

```python
def build_extension_snapshot(
    repository: Repository,
    filters: AnalyticsFilter,
    *,
    period: str | None,
    database_path: Path,
) -> dict[str, object]:
    analytics = AnalyticsService(repository, filters)
    summary = analytics.summary()
    quality = analytics.data_quality()
    return {
        "schema": SNAPSHOT_SCHEMA,
        "version": SNAPSHOT_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "database": str(database_path),
        "filters": {
            "from": filters.from_date.isoformat() if filters.from_date else None,
            "to": filters.to_date.isoformat() if filters.to_date else None,
            "period": period,
            "project": filters.project,
            "model": filters.model,
            "source": filters.source,
            "user": filters.user,
            "machine": filters.machine,
        },
        "summary": to_dict(SnapshotSummary(
            sessions=summary.sessions,
            total_tokens=summary.total_tokens,
            tokens_saved=summary.tokens_saved,
            cache_ratio=summary.cache_ratio if summary.input_tokens else None,
            observed_cost_usd=summary.observed_cost_usd,
            estimated_savings_usd=summary.total_savings_usd,
        )),
        "dimensions": to_dict(_dimensions(repository, filters)),
        "quality": to_dict(_quality(repository, analytics, quality)),
    }
```

`_quality(...)` maps only fields actually present in current `AnalyticsService.data_quality()` plus parameterized counts required by the contract. If a quality distribution is unavailable from current normalized data, return `{}` rather than inventing values.

- [ ] **Step 6: Run the unit tests to verify GREEN**

Run:

```bash
python -m pytest tests/unit/test_extension_snapshot.py -q
```

Expected: PASS.

- [ ] **Step 7: Write the failing CLI integration test**

Create `tests/integration/test_extension_cli.py` using the existing synthetic fixture approach and an isolated environment `AGENTSCOPE_SOURCES=codex,headroom`. Invoke:

```python
result = runner.invoke(app, [
    "extension", "snapshot",
    "--database", str(db),
    "--period", "30d",
    "--json",
], env=FIXTURE_ENV)
```

Assert `result.exit_code == 0`, parse `json.loads(result.output)`, and assert schema/version, `summary.sessions == 1`, and that `dimensions.projects` is a list. Add a filtered invocation with `--project missing-project` and assert `summary.sessions == 0`.

- [ ] **Step 8: Run the CLI integration test to verify RED**

Run:

```bash
python -m pytest tests/integration/test_extension_cli.py -q
```

Expected: FAIL because the `extension` command group does not exist.

- [ ] **Step 9: Register the Typer extension command group**

Modify `src/agentscope/cli.py`:

```python
extension_app = typer.Typer(help="Machine-readable integration commands.")
app.add_typer(extension_app, name="extension")


@extension_app.command("snapshot")
def extension_snapshot(
    json_output: bool = typer.Option(False, "--json"),
    database: Optional[Path] = typer.Option(None, "--database"),
    from_value: Optional[str] = typer.Option(None, "--from"),
    to_value: Optional[str] = typer.Option(None, "--to"),
    period: Optional[str] = typer.Option(None, "--period"),
    project: Optional[str] = typer.Option(None, "--project"),
    model: Optional[str] = typer.Option(None, "--model"),
    source: Optional[str] = typer.Option(None, "--source"),
    user: Optional[str] = typer.Option(None, "--user"),
    machine: Optional[str] = typer.Option(None, "--machine"),
) -> None:
    if not json_output:
        raise typer.BadParameter("Use --json for the extension snapshot contract.")
    config = AgentScopeConfig.from_env(database_path=database)
    if not config.database_path.exists():
        typer.echo(f"database not found: {config.database_path}", err=True)
        raise typer.Exit(code=2)
    repo = _repository(config.database_path)
    filters = _analytics_filter(
        period=period,
        from_value=from_value,
        to_value=to_value,
        project=project,
        model=model,
        source=source,
        user=user,
        machine=machine,
    )
    payload = build_extension_snapshot(
        repo,
        filters,
        period=period,
        database_path=config.database_path,
    )
    typer.echo(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
```

The JSON command must emit only JSON to stdout on success; diagnostics/errors go to stderr.

- [ ] **Step 10: Run Python targeted + regression tests**

Run:

```bash
python -m pytest tests/unit/test_extension_snapshot.py tests/integration/test_extension_cli.py tests/integration/test_cli_flow.py -q
```

Expected: PASS.

- [ ] **Step 11: Commit TASK-001**

```bash
git add src/agentscope/extension src/agentscope/cli.py tests/unit/test_extension_snapshot.py tests/integration/test_extension_cli.py
git commit -m "feat: expose vscode extension snapshot contract"
```

---

### Task 2: TASK-002 — VS Code extension scaffold

**Files:**
- Create: `vscode-extension/package.json`
- Create: `vscode-extension/tsconfig.json`
- Create: `vscode-extension/.vscode-test.mjs`
- Create: `vscode-extension/src/extension.ts`
- Create: `vscode-extension/src/test/suite/extension.test.ts`
- Create: `vscode-extension/media/agentscope.svg`

**Interfaces:**
- Consumes: VS Code Extension API.
- Produces extension ID: `peterson-benhame.agentscope` in local development naming.
- Produces commands: `agentscope.openDashboard`, `agentscope.refreshDashboard`, `agentscope.selectDatabase`.
- Produces views: `agentscope.dashboard`, `agentscope.sources`, `agentscope.projects` inside Activity Bar container `agentscope`.

- [ ] **Step 1: Write the failing extension activation test**

Create `vscode-extension/src/test/suite/extension.test.ts`:

```ts
import * as assert from 'assert';
import * as vscode from 'vscode';

suite('AgentScope extension', () => {
  test('registers the MVP commands', async () => {
    const commands = await vscode.commands.getCommands(true);
    assert.ok(commands.includes('agentscope.openDashboard'));
    assert.ok(commands.includes('agentscope.refreshDashboard'));
    assert.ok(commands.includes('agentscope.selectDatabase'));
  });
});
```

- [ ] **Step 2: Create the minimal package manifest and TypeScript config**

`vscode-extension/package.json` must contain:

```json
{
  "name": "agentscope",
  "displayName": "AgentScope",
  "description": "Local-first AI coding analytics inside VS Code",
  "version": "0.1.0",
  "publisher": "peterson-benhame",
  "engines": { "vscode": "^1.104.0" },
  "categories": ["Visualization", "Other"],
  "main": "./out/extension.js",
  "activationEvents": [
    "onView:agentscope.dashboard",
    "onCommand:agentscope.openDashboard",
    "onCommand:agentscope.refreshDashboard",
    "onCommand:agentscope.selectDatabase"
  ],
  "contributes": {
    "commands": [
      { "command": "agentscope.openDashboard", "title": "AgentScope: Open Dashboard" },
      { "command": "agentscope.refreshDashboard", "title": "AgentScope: Refresh Dashboard" },
      { "command": "agentscope.selectDatabase", "title": "AgentScope: Select Database" }
    ],
    "viewsContainers": {
      "activitybar": [
        { "id": "agentscope", "title": "AgentScope", "icon": "media/agentscope.svg" }
      ]
    },
    "views": {
      "agentscope": [
        { "id": "agentscope.dashboard", "name": "Dashboard", "type": "webview" },
        { "id": "agentscope.sources", "name": "Fontes" },
        { "id": "agentscope.projects", "name": "Projetos" }
      ]
    }
  },
  "scripts": {
    "compile": "tsc -p .",
    "pretest": "npm run compile",
    "test": "vscode-test",
    "test:unit": "mocha \"out/test/unit/**/*.test.js\""
  },
  "devDependencies": {
    "@types/mocha": "^10.0.10",
    "@types/node": "^22.0.0",
    "@types/vscode": "^1.104.0",
    "@vscode/test-cli": "^0.0.11",
    "@vscode/test-electron": "^2.5.2",
    "mocha": "^11.0.0",
    "typescript": "^5.8.0"
  }
}
```

Before implementation, resolve the exact compatible package versions with `npm view`; if a listed minimum is unavailable, use the latest non-prerelease version that supports Node/VS Code requirements without changing interfaces.

`tsconfig.json` compiles `src/**/*.ts` to `out/`, with `target: ES2022`, `module: CommonJS`, `strict: true`, `sourceMap: true`, `esModuleInterop: true`, and excludes `node_modules`.

`.vscode-test.mjs` uses `defineConfig` from `@vscode/test-cli` and runs `out/test/suite/**/*.test.js` with `--disable-extensions`.

- [ ] **Step 3: Create the minimal activation root**

Implement `src/extension.ts` registering three commands with no business logic yet:

```ts
import * as vscode from 'vscode';

export function activate(context: vscode.ExtensionContext): void {
  context.subscriptions.push(
    vscode.commands.registerCommand('agentscope.openDashboard', async () => {
      await vscode.commands.executeCommand('agentscope.dashboard.focus');
    }),
    vscode.commands.registerCommand('agentscope.refreshDashboard', () => undefined),
    vscode.commands.registerCommand('agentscope.selectDatabase', () => undefined),
  );
}

export function deactivate(): void {}
```

- [ ] **Step 4: Install dependencies and run the integration test**

Run from `vscode-extension/`:

```bash
npm install
npm test
```

Expected: PASS and extension commands visible in Extension Development Host.

- [ ] **Step 5: Commit TASK-002**

```bash
git add vscode-extension
git commit -m "feat: scaffold agentscope vscode extension"
```

---

### Task 3: TASK-003 — Snapshot parser and AgentScopeClient

**Files:**
- Create: `vscode-extension/src/contracts/snapshot.ts`
- Create: `vscode-extension/src/client/agentScopeClient.ts`
- Test: `vscode-extension/src/test/unit/snapshot.test.ts`
- Test: `vscode-extension/src/test/unit/agentScopeClient.test.ts`

**Interfaces:**
- Produces `ExtensionSnapshot` matching schema version 1.
- Produces `parseExtensionSnapshot(value: unknown): ExtensionSnapshot`.
- Produces `AgentScopeClient.snapshot(filters: SnapshotFilters): Promise<ExtensionSnapshot>`.
- Produces `SnapshotClientError` with codes `AGENTSCOPE_NOT_FOUND | DATABASE_NOT_FOUND | SNAPSHOT_TIMEOUT | SNAPSHOT_PROCESS_ERROR | SNAPSHOT_INVALID_JSON | SNAPSHOT_UNSUPPORTED_VERSION`.

- [ ] **Step 1: Write failing parser tests**

Create a valid fixture object in `snapshot.test.ts`; assert parse success. Add:

```ts
assert.throws(
  () => parseExtensionSnapshot({ schema: 'agentscope-extension-snapshot', version: 2 }),
  (error: unknown) => error instanceof SnapshotContractError && error.code === 'SNAPSHOT_UNSUPPORTED_VERSION',
);
```

Add invalid summary/dimensions shape test expecting `SNAPSHOT_INVALID_JSON`.

- [ ] **Step 2: Run parser tests to verify RED**

Run:

```bash
npm run compile && npx mocha "out/test/unit/snapshot.test.js"
```

Expected: FAIL because the snapshot contract module does not exist.

- [ ] **Step 3: Implement typed contract validation**

Define `SnapshotFilters`, `SnapshotSummary`, `SnapshotDimensions`, `SnapshotQuality`, and `ExtensionSnapshot`. Implement explicit object/array/string/number/null guards. Reject wrong schema as invalid JSON and wrong version as unsupported version. Do not add a runtime validation dependency.

- [ ] **Step 4: Run parser tests to verify GREEN**

Run the same parser test command. Expected: PASS.

- [ ] **Step 5: Write failing AgentScopeClient argument/error tests**

Define an injectable runner interface:

```ts
export interface ProcessRunner {
  run(executable: string, args: readonly string[], timeoutMs: number): Promise<{ stdout: string; stderr: string; exitCode: number }>;
}
```

Test that `client.snapshot({ period: '7d', project: 'example-project' })` calls:

```ts
['extension', 'snapshot', '--json', '--period', '7d', '--project', 'example-project']
```

When databasePath is configured, assert `--database <path>` is present. Test ENOENT mapping to `AGENTSCOPE_NOT_FOUND`, timeout mapping to `SNAPSHOT_TIMEOUT`, stderr containing `database not found:` with non-zero exit to `DATABASE_NOT_FOUND`, and invalid stdout JSON to `SNAPSHOT_INVALID_JSON`.

- [ ] **Step 6: Run client tests to verify RED**

Run:

```bash
npm run compile && npx mocha "out/test/unit/agentScopeClient.test.js"
```

Expected: FAIL because `AgentScopeClient` does not exist.

- [ ] **Step 7: Implement the process runner and client**

Use `child_process.execFile` via `promisify` or an explicit Promise wrapper with `shell: false`, UTF-8 decoding, `maxBuffer` bounded to 2 MiB, and timeout 15,000 ms. Build CLI args with a pure `buildSnapshotArgs(filters, databasePath)` function so tests never spawn real providers.

- [ ] **Step 8: Run TypeScript unit tests**

Run:

```bash
npm run compile
npm run test:unit
```

Expected: PASS.

- [ ] **Step 9: Commit TASK-003**

```bash
git add vscode-extension/src/contracts vscode-extension/src/client vscode-extension/src/test/unit
git commit -m "feat: connect vscode extension to agentscope cli"
```

---

### Task 4: TASK-004 — VS Code settings and database selection

**Files:**
- Modify: `vscode-extension/package.json`
- Create: `vscode-extension/src/config/settings.ts`
- Modify: `vscode-extension/src/extension.ts`
- Test: `vscode-extension/src/test/unit/settings.test.ts`

**Interfaces:**
- Produces `AgentScopeSettings` with `executablePath`, `databasePath`, `defaultPeriod`, `autoRefresh`, `autoRefreshIntervalSeconds`.
- Produces `readSettings(): AgentScopeSettings`.
- Produces `setDatabasePath(path: string): Promise<void>`.

- [ ] **Step 1: Write failing settings tests**

Use a tiny injected configuration-reader abstraction around VS Code configuration for pure unit tests. Assert defaults:

```ts
{
  executablePath: 'agentscope',
  databasePath: '',
  defaultPeriod: '7d',
  autoRefresh: false,
  autoRefreshIntervalSeconds: 60,
}
```

Assert invalid `defaultPeriod` falls back to `7d` and interval values below 10 clamp to 10.

- [ ] **Step 2: Run RED**

Run compile + settings unit test. Expected: FAIL because settings module does not exist.

- [ ] **Step 3: Add configuration contributions**

In `package.json`, add `contributes.configuration` properties:

```text
agentscope.executablePath: string, default "agentscope"
agentscope.databasePath: string, default ""
agentscope.defaultPeriod: enum ["today","7d","30d","month"], default "7d"
agentscope.autoRefresh: boolean, default false
agentscope.autoRefreshIntervalSeconds: number, default 60, minimum 10
```

- [ ] **Step 4: Implement typed settings access**

Use `vscode.workspace.getConfiguration('agentscope')`; update database path with `ConfigurationTarget.Global` for MVP consistency across workspaces.

- [ ] **Step 5: Implement Select Database command**

Replace the stub in `extension.ts` with `vscode.window.showOpenDialog({ canSelectFiles: true, canSelectFolders: false, canSelectMany: false, filters: { 'SQLite database': ['db', 'sqlite', 'sqlite3'] } })`. On selection call `setDatabasePath(uri.fsPath)` and execute `agentscope.refreshDashboard`.

- [ ] **Step 6: Run unit + extension tests**

Run:

```bash
npm run compile
npm run test:unit
npm test
```

Expected: PASS.

- [ ] **Step 7: Commit TASK-004**

```bash
git add vscode-extension/package.json vscode-extension/src/config vscode-extension/src/extension.ts vscode-extension/src/test/unit/settings.test.ts
git commit -m "feat: configure agentscope vscode connection"
```

---

### Task 5: TASK-005 — Activity Bar, dashboard/source/project views, and coordinator

**Files:**
- Create: `vscode-extension/src/state/filterState.ts`
- Create: `vscode-extension/src/services/dashboardCoordinator.ts`
- Create: `vscode-extension/src/views/sourcesViewProvider.ts`
- Create: `vscode-extension/src/views/projectsViewProvider.ts`
- Create: `vscode-extension/src/views/dashboardViewProvider.ts`
- Modify: `vscode-extension/src/extension.ts`
- Test: `vscode-extension/src/test/unit/filterState.test.ts`
- Modify: `vscode-extension/src/test/suite/extension.test.ts`

**Interfaces:**
- Produces `DashboardCoordinator.refresh(): Promise<void>`.
- Produces `DashboardCoordinator.setFilter(patch: Partial<SnapshotFilters>): Promise<void>`.
- Produces `SourcesViewProvider.setItems(values: readonly string[]): void`.
- Produces `ProjectsViewProvider.setItems(values: readonly string[]): void`.
- Produces `DashboardViewProvider.update(snapshot: ExtensionSnapshot, filters: SnapshotFilters): void`.

- [ ] **Step 1: Write failing filter state tests**

Test `createDefaultFilterState('7d')`, `applyPeriod(state, 'month')`, `applyCustomRange(state, '2026-08-01', '2026-08-18')` clears `period`, and `resetFilters(state, '30d')` clears all dimensions while restoring `period='30d'`.

- [ ] **Step 2: Run RED**

Run the filter-state unit test. Expected: FAIL because module does not exist.

- [ ] **Step 3: Implement immutable filter state helpers**

`SnapshotFilters` uses nullable/optional strings exactly matching CLI filters. All transitions return new objects; no analytics math occurs here.

- [ ] **Step 4: Implement Source and Project TreeDataProviders**

Each provider exposes one level of `TreeItem`s. `SourcesViewProvider` uses command `agentscope.filterBySource` with the source label argument. `ProjectsViewProvider` uses command `agentscope.filterByProject` with the project label argument. Register these internal commands in `extension.ts` even though they need not be contributed to the Command Palette.

- [ ] **Step 5: Implement DashboardCoordinator**

Constructor dependencies: `AgentScopeClient`, settings reader, dashboard provider, sources provider, projects provider, and output channel. `refresh()` reads settings, requests a snapshot, updates all three views, and maps `SnapshotClientError` to a sanitized UI error model. No Python traceback is sent to the Webview.

- [ ] **Step 6: Implement DashboardViewProvider shell**

Register with `vscode.window.registerWebviewViewProvider('agentscope.dashboard', provider)`. On `resolveWebviewView`, set `enableScripts = true`, `localResourceRoots = [context.extensionUri]`, set CSP-aware HTML, and immediately request coordinator refresh.

- [ ] **Step 7: Wire activation composition**

`extension.ts` creates one OutputChannel `AgentScope`, one client, providers, and coordinator. Register TreeDataProviders, WebviewViewProvider, open/refresh/select/filter commands, and dispose everything through `context.subscriptions`.

- [ ] **Step 8: Extend extension integration test**

Assert extension activation succeeds and contributed views exist by executing `workbench.view.extension.agentscope` and focusing `agentscope.dashboard`. The test must not require a real CLI call; construct coordinator/client so process invocation is deferred until view resolve and surface an expected empty/error state rather than failing activation.

- [ ] **Step 9: Run unit + integration tests**

Run:

```bash
npm run compile
npm run test:unit
npm test
```

Expected: PASS.

- [ ] **Step 10: Commit TASK-005**

```bash
git add vscode-extension/src/state vscode-extension/src/services vscode-extension/src/views vscode-extension/src/extension.ts vscode-extension/src/test
git commit -m "feat: add agentscope activity bar views"
```

---

### Task 6: TASK-006 — Visual dashboard cards and secure Webview messaging

**Files:**
- Modify: `vscode-extension/src/views/dashboardViewProvider.ts`
- Create: `vscode-extension/media/dashboard.js`
- Create: `vscode-extension/media/dashboard.css`
- Test: `vscode-extension/src/test/unit/dashboardViewModel.test.ts`
- Create: `vscode-extension/src/views/dashboardViewModel.ts`

**Interfaces:**
- Produces `toDashboardViewModel(snapshot: ExtensionSnapshot, filters: SnapshotFilters): DashboardViewModel`.
- Webview host messages: `{ type: 'snapshot'; payload: DashboardViewModel }`, `{ type: 'loading' }`, `{ type: 'error'; code: string; message: string }`.
- Webview client messages: `{ type: 'refresh' }`, `{ type: 'selectDatabase' }`, `{ type: 'setFilter'; patch: Partial<SnapshotFilters> }`, `{ type: 'resetFilters' }`.

- [ ] **Step 1: Write failing dashboard view-model tests**

Assert:

```ts
const vm = toDashboardViewModel(snapshot, { period: '7d' });
assert.strictEqual(vm.cards.sessions, '77');
assert.strictEqual(vm.cards.totalTokens, '1.465.312.344');
assert.strictEqual(vm.cards.cacheRatio, '94,63%');
assert.strictEqual(vm.cards.observedCost, 'US$ 13,78');
assert.strictEqual(vm.cards.estimatedSavings, 'US$ 76,89');
```

Add `observed_cost_usd: null` => `Não disponível`. Use local pure formatters in the extension only for presentation, not analytics.

- [ ] **Step 2: Run RED**

Run dashboard view-model unit test. Expected: FAIL because module does not exist.

- [ ] **Step 3: Implement pt-BR presentation helpers and view model**

Use `Intl.NumberFormat('pt-BR')` for integer/decimal and a deterministic `US$ ` prefix for USD; do not recalculate token totals/cache ratios/savings.

- [ ] **Step 4: Implement secure Webview HTML**

`DashboardViewProvider` generates a cryptographically random nonce with Node `crypto`. CSP:

```text
default-src 'none'; img-src <webview.cspSource> data:; style-src <webview.cspSource>; script-src 'nonce-<nonce>';
```

Load only `media/dashboard.css` and `media/dashboard.js` via `webview.asWebviewUri(...)`. Do not use inline executable script without nonce and do not load CDN assets.

- [ ] **Step 5: Implement dashboard DOM rendering**

`dashboard.js` uses `acquireVsCodeApi()`, listens for `loading|snapshot|error`, renders six cards and active filter context, and sends `refresh`/`selectDatabase` messages from buttons. No `eval`, `innerHTML` with data-derived values, remote fetch, or analytics calculations. Use `textContent` for data.

- [ ] **Step 6: Implement CSS with VS Code theme variables**

Use `--vscode-editor-background`, `--vscode-editor-foreground`, `--vscode-sideBarSectionHeader-background`, `--vscode-input-background`, `--vscode-input-border`, `--vscode-focusBorder`, and layout grid. No fixed branding color is required for the MVP.

- [ ] **Step 7: Wire host message handling**

Dashboard provider forwards `refresh` to coordinator refresh and `selectDatabase` to `agentscope.selectDatabase`; filter messages are handled in Task 7. Ignore unknown message types.

- [ ] **Step 8: Run unit + integration tests**

Run compile, unit tests, and `npm test`. Expected: PASS.

- [ ] **Step 9: Commit TASK-006**

```bash
git add vscode-extension/src/views vscode-extension/media vscode-extension/src/test/unit/dashboardViewModel.test.ts
git commit -m "feat: render agentscope vscode dashboard"
```

---

### Task 7: TASK-007 — End-to-end dashboard filters

**Files:**
- Modify: `vscode-extension/src/views/dashboardViewProvider.ts`
- Modify: `vscode-extension/src/services/dashboardCoordinator.ts`
- Modify: `vscode-extension/media/dashboard.js`
- Modify: `vscode-extension/media/dashboard.css`
- Modify: `vscode-extension/src/test/unit/filterState.test.ts`
- Modify: `vscode-extension/src/test/unit/agentScopeClient.test.ts`
- Modify: `tests/integration/test_extension_cli.py`

**Interfaces:**
- Consumes all prior interfaces.
- Produces complete MVP filter flow: Webview/Tree → coordinator → CLI snapshot → synchronized Webview/Trees.

- [ ] **Step 1: Extend failing filter-state tests for all dimensions**

Assert project/model/source/user/machine patches preserve other filters. Assert custom range removes period and preset period removes custom dates. Assert reset restores settings default period.

- [ ] **Step 2: Extend failing AgentScopeClient argument tests**

For filters:

```ts
{
  from: '2026-08-01',
  to: '2026-08-18',
  project: 'example-project',
  model: 'gpt-example',
  source: 'codex',
  user: 'Dev A',
  machine: 'Notebook A'
}
```

assert args include each exact flag/value and do not include `--period`.

- [ ] **Step 3: Extend Python CLI integration coverage**

In `tests/integration/test_extension_cli.py`, add one test per dimension where fixture data supports it. Assert selected filters alter summary or return an empty summary for missing values. This proves TypeScript forwards filters to Python rather than filtering locally.

- [ ] **Step 4: Run the new tests to verify RED where behavior is missing**

Run targeted Python and TypeScript tests. Expected: failures only for missing Webview/coordinator filter wiring; existing backend filter semantics should already satisfy CLI dimensions.

- [ ] **Step 5: Implement coordinator filter transitions**

`setFilter(patch)` merges the patch through filter-state helpers and calls `refresh()`. Add explicit methods for `setPeriod`, `setCustomRange`, and `resetFilters` so conflicting date/period state cannot coexist.

- [ ] **Step 6: Implement Webview filter controls**

Render preset buttons/select; two `<input type="date">` fields for custom range; `<select>` controls for project/model/source/user/machine populated from snapshot dimensions. Send only primitive string/null values to the extension host.

- [ ] **Step 7: Synchronize Tree selections**

`agentscope.filterBySource` and `agentscope.filterByProject` call coordinator `setFilter`. After refresh, active values are reflected in the Webview filter controls. Tree views remain lists, not analytics engines.

- [ ] **Step 8: Handle loading/race behavior**

Coordinator increments a request sequence integer before each snapshot. Only the latest sequence may update the views; late responses from earlier filter requests are discarded. This prevents rapid filter changes from rendering stale data without introducing cancellation complexity.

- [ ] **Step 9: Run full MVP verification**

Python:

```bash
python -m pytest -q
```

VS Code extension:

```bash
cd vscode-extension
npm run compile
npm run test:unit
npm test
```

Expected: all commands exit 0.

- [ ] **Step 10: Manual Extension Development Host smoke test**

Launch the extension with F5 or the generated extension-host debug configuration. Configure a synthetic/local `agentscope.db`, open AgentScope Activity Bar, and verify:

```text
Dashboard visible
6 cards visible
7d default applied
Today / 7d / 30d / Month work
Custom dates work
Project/model/source/user/machine filter controls render
Source/Project Tree selection changes dashboard
Select Database refreshes dashboard
Missing database produces remediation UI
```

Do not use private provider message content for this smoke test; use a synthetic database or safe local analytics database.

- [ ] **Step 11: Update README for MVP development use**

Add a `VS Code Visual MVP` section documenting prerequisites, `cd vscode-extension && npm install`, F5 development launch, extension settings, and the fact that the extension calls `agentscope extension snapshot --json` rather than opening SQLite directly.

- [ ] **Step 12: Commit TASK-007**

```bash
git add tests/integration/test_extension_cli.py vscode-extension README.md
git commit -m "feat: add vscode dashboard filters"
```

- [ ] **Step 13: Fresh final verification before review**

Re-run the full Python suite and all extension compile/unit/integration tests after the documentation commit. Record exact pass/fail counts in the PR body; do not rely on prior runs.
