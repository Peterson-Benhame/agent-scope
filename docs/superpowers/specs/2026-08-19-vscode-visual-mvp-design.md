# AgentScope VS Code Visual MVP Design

Date: 2026-08-19
Status: Proposed design for implementation
Scope: TASK-001 through TASK-007 only. Visual local analytics inside VS Code backed by the existing AgentScope CLI and SQLite database.

## 1. Objective

Deliver a first AgentScope experience inside Visual Studio Code where the user can open an AgentScope view, point it at an existing AgentScope database, and inspect local analytics visually without duplicating Python analytics logic in TypeScript.

The MVP must make AgentScope visible inside VS Code and provide a working dashboard with filtering by period and existing analytics dimensions.

## 2. Scope

Included:

1. Stable JSON contract for extension consumption.
2. VS Code extension scaffold in TypeScript.
3. TypeScript client that invokes the AgentScope CLI.
4. VS Code configuration for executable/database/default period/refresh behavior.
5. AgentScope Activity Bar container and sidebar views.
6. Visual dashboard webview with executive cards.
7. Dashboard filters for date/project/model/source/user/machine.

Explicitly deferred:

- charts beyond the visual cards required by this MVP;
- Tree View details for every provider/project;
- `Collect now` button;
- auto-refresh timer implementation beyond configuration plumbing;
- team analytics UI;
- VSIX publication;
- marketplace publishing;
- central API/server;
- direct SQLite access from TypeScript;
- modification of provider histories.

## 3. Architecture

```text
VS Code Extension (TypeScript)
        |
        v
AgentScopeClient
        |
        | child process / CLI invocation
        v
agentscope extension snapshot --json
        |
        v
AnalyticsService / existing normalized services
        |
        v
AgentScope SQLite database
```

The extension does not query SQLite directly. Python remains the source of truth for analytics semantics, filtering, null handling, cost semantics, and data-quality rules.

## 4. Repository structure

```text
agent-scope/
├── src/agentscope/
│   └── extension/
│       ├── __init__.py
│       ├── snapshot.py
│       └── contracts.py
├── tests/
│   ├── unit/
│   └── integration/
├── vscode-extension/
│   ├── package.json
│   ├── tsconfig.json
│   ├── src/
│   │   ├── extension.ts
│   │   ├── client/
│   │   │   └── agentScopeClient.ts
│   │   ├── contracts/
│   │   │   └── snapshot.ts
│   │   ├── views/
│   │   │   ├── dashboardViewProvider.ts
│   │   │   ├── sourcesViewProvider.ts
│   │   │   └── projectsViewProvider.ts
│   │   └── config/
│   │       └── settings.ts
│   └── media/
│       ├── dashboard.js
│       └── dashboard.css
└── docs/
```

## 5. TASK-001 — Extension snapshot contract

### 5.1 Command

Add a read-only command:

```text
agentscope extension snapshot --json
```

Supported filters:

```text
--database
--from
--to
--period today|7d|30d|month
--project
--model
--source
--user
--machine
```

The command must reuse the same filter construction and analytics semantics already used by `analyze`, `report`, and `export`.

### 5.2 Contract

Schema identifier:

```json
{
  "schema": "agentscope-extension-snapshot",
  "version": 1
}
```

Required top-level shape:

```json
{
  "schema": "agentscope-extension-snapshot",
  "version": 1,
  "generated_at": "2026-08-19T14:00:00Z",
  "database": "...",
  "filters": {
    "from": null,
    "to": null,
    "period": "7d",
    "project": null,
    "model": null,
    "source": null,
    "user": null,
    "machine": null
  },
  "summary": {
    "sessions": 0,
    "total_tokens": 0,
    "tokens_saved": 0,
    "cache_ratio": null,
    "observed_cost_usd": null,
    "estimated_savings_usd": null
  },
  "dimensions": {
    "projects": [],
    "models": [],
    "sources": [],
    "users": [],
    "machines": []
  },
  "quality": {
    "import_errors": 0,
    "tokens_without_model": 0,
    "identity_confidence": {},
    "correlation_confidence": {}
  }
}
```

Unknown monetary values remain `null`, never `0`.

No message bodies, prompt content, source code, tool payloads, attachments, secrets, raw provider metadata, or full provider file paths may appear in the snapshot.

## 6. TASK-002 — VS Code extension scaffold

Create `vscode-extension/` as an independent TypeScript package.

Minimum extension contributions:

- AgentScope Activity Bar container;
- `agentscope.dashboard` view;
- `agentscope.sources` view;
- `agentscope.projects` view;
- command `agentscope.openDashboard`;
- command `agentscope.refreshDashboard`;
- command `agentscope.selectDatabase`.

The extension must activate when an AgentScope command/view is invoked, not eagerly on every VS Code startup.

## 7. TASK-003 — AgentScopeClient

`AgentScopeClient` is the only TypeScript component allowed to execute the Python CLI.

Responsibilities:

- resolve executable from configuration, defaulting to `agentscope` on PATH;
- resolve database path from configuration;
- execute `agentscope extension snapshot --json`;
- pass active filters as CLI arguments;
- use argument arrays rather than shell-concatenated command strings;
- parse stdout JSON;
- reject invalid schema/version;
- distinguish executable-not-found, database-not-found, timeout, non-zero process exit, invalid JSON, and unsupported snapshot version;
- never print prompt/message content into extension logs.

Default timeout: 15 seconds for snapshot retrieval.

## 8. TASK-004 — Extension configuration

VS Code settings:

```text
agentscope.executablePath
agentscope.databasePath
agentscope.defaultPeriod
agentscope.autoRefresh
agentscope.autoRefreshIntervalSeconds
```

Defaults:

```text
executablePath = "agentscope"
databasePath = ""
defaultPeriod = "7d"
autoRefresh = false
autoRefreshIntervalSeconds = 60
```

`databasePath = ""` means the extension lets the AgentScope CLI use its normal default database path.

The MVP stores no provider credentials.

## 9. TASK-005 — Activity Bar and sidebar

Create an AgentScope icon in the Activity Bar.

The AgentScope container contains:

```text
AgentScope
├── Dashboard
├── Fontes
└── Projetos
```

For this MVP:

- Dashboard is a Webview View.
- Fontes is a lightweight Tree View sourced from snapshot `dimensions.sources`.
- Projetos is a lightweight Tree View sourced from snapshot `dimensions.projects`.

Selecting a project sends a filter update to the dashboard.

Selecting a source sends a filter update to the dashboard.

## 10. TASK-006 — Dashboard Webview

The dashboard is a VS Code Webview View using VS Code theme variables. It must work in dark and light themes without hard-coded branding colors that reduce readability.

Executive cards:

```text
Sessões
Total de tokens
Tokens economizados
Taxa de cache
Custo observado
Economia estimada
```

Rules:

- use pt-BR formatting compatible with AgentScope reports;
- monetary values use `US$`;
- unavailable money displays `Não disponível`;
- loading state is visible;
- empty database state is visible;
- CLI/config errors are displayed with a clear remediation action;
- Webview does not execute arbitrary remote scripts;
- Content Security Policy must restrict script/style sources to extension-controlled resources.

The dashboard should show active filter context above the cards.

## 11. TASK-007 — Dashboard filters

Filter controls:

```text
Hoje
7 dias
30 dias
Mês
Personalizado
Projeto
Modelo
Fonte
Usuário
Máquina
```

Filter behavior:

- preset period selection maps directly to CLI `--period`;
- custom date range maps to `--from` and `--to`;
- explicit date range overrides preset period;
- dimension filters use values received from snapshot dimensions;
- changing a filter requests a new snapshot from Python;
- TypeScript must not recalculate analytics locally;
- clear/reset restores configured default period and removes dimension filters.

## 12. Data flow

Initial opening:

```text
Open AgentScope view
  -> read settings
  -> AgentScopeClient.snapshot(default filters)
  -> validate snapshot schema/version
  -> render cards + filter options + trees
```

Filter change:

```text
Webview/Tree selection
  -> extension host receives message
  -> update in-memory filter state
  -> AgentScopeClient.snapshot(filters)
  -> validate
  -> send sanitized snapshot to webview
  -> render
```

Database selection:

```text
AgentScope: Select Database
  -> vscode.window.showOpenDialog
  -> save agentscope.databasePath
  -> refresh snapshot
```

## 13. Error handling

The UI must distinguish at least:

```text
AGENTSCOPE_NOT_FOUND
DATABASE_NOT_FOUND
SNAPSHOT_TIMEOUT
SNAPSHOT_PROCESS_ERROR
SNAPSHOT_INVALID_JSON
SNAPSHOT_UNSUPPORTED_VERSION
SNAPSHOT_EMPTY
```

No Python traceback should be dumped directly into the Webview. Technical details may be written to an AgentScope output channel after sanitization.

## 14. Security and privacy

- extension never reads provider history directories directly;
- extension never reads SQLite directly;
- extension only receives snapshot allow-listed analytics metadata;
- no remote HTTP request is required for the MVP;
- no telemetry is sent outside the local machine by this feature;
- no secrets or message content enter Webview messages;
- CLI invocation uses argument arrays to avoid shell injection;
- Webview uses a restrictive CSP and extension-local assets.

## 15. Testing strategy

### Python

Unit tests:

- snapshot contract schema/version;
- null monetary semantics;
- filters propagated correctly;
- safe allow-list/no message content.

Integration tests:

- fixture DB -> `agentscope extension snapshot --json`;
- period/project/model/source/user/machine filters;
- invalid database path produces non-zero/clear error.

### TypeScript

Unit tests:

- snapshot contract parser;
- unsupported version rejection;
- CLI argument construction;
- process error mapping;
- filter state transitions.

Extension integration tests:

- activate extension;
- register views/commands;
- mock/fake CLI process boundary only at the process adapter layer;
- dashboard receives a valid synthetic snapshot.

Tests must not depend on real local Codex, Headroom, Claude, Copilot, Kimi, or Gemini installations.

## 16. Acceptance criteria

The MVP is complete when:

1. AgentScope appears as an Activity Bar entry in VS Code.
2. Opening AgentScope renders the dashboard inside VS Code.
3. Dashboard data comes from an existing AgentScope SQLite database through the AgentScope CLI.
4. Six executive cards render using the snapshot contract.
5. `today`, `7d`, `30d`, `month`, and custom date filtering work end-to-end.
6. Project/model/source/user/machine filtering works end-to-end where values exist.
7. Fontes and Projetos appear in sidebar views and can drive dashboard filters.
8. Extension configuration can select executable/database/default period.
9. Missing CLI/database and invalid snapshot errors are understandable in the UI.
10. No direct SQL exists in the extension package.
11. No prompt/response/source-code/tool-payload data is sent to the Webview.
12. Python tests remain green.
13. TypeScript build/tests remain green.

## 17. Implementation order

```text
TASK-001 snapshot contract
    ↓
TASK-002 extension scaffold
    ↓
TASK-003 AgentScopeClient
    ↓
TASK-004 settings
    ↓
TASK-005 Activity Bar/sidebar
    ↓
TASK-006 dashboard cards
    ↓
TASK-007 filters
```

TASK-002 can begin after the snapshot contract shape is stable. TASK-005 through TASK-007 depend on TASK-003.

## 18. Boundaries after MVP

The next increment may add charts, provider/project detail views, `Collect now`, auto-refresh execution, quality drill-down, team UI, VSIX packaging, and publishing. None of those are required for acceptance of this MVP.
