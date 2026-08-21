# AgentScope VS Code Dashboard Analytics Design

## Goal

Evolve the current read-only VS Code Visual MVP into a reliable, responsive analytics dashboard focused on local usage, cost and efficiency. Team UI and shared API are explicitly deferred.

## Scope

This increment delivers four capabilities:

1. reliable user/machine filtering and historical identity backfill;
2. explicit cost semantics for observed cost, estimated cost and estimated savings;
3. responsive dashboard redesign;
4. trend and breakdown charts backed by Python analytics data.

## Out of scope

- Team UI.
- Central/shared API.
- Cross-machine synchronization.
- Marketplace/VSIX packaging.
- Developer productivity scoring.

## Architecture

Python remains the source of truth. The VS Code extension must not query SQLite directly.

```text
Provider histories
      ↓
AgentScope collectors/adapters
      ↓
SQLite
      ↓
AnalyticsService
      ↓
agentscope extension snapshot --json
      ↓
VS Code extension
      ↓
Dashboard + charts
```

The snapshot remains allow-listed and privacy-safe. No prompt bodies, assistant responses, source code, raw provider payloads, secrets or full local provider paths are exposed to the webview.

## Identity and historical backfill

### Current problem

Sessions imported before user/machine identity support may remain without `user_id` and/or `machine_id`. A normal incremental collection can skip unchanged source files, so those sessions may never receive identity associations.

### Design

Add an explicit operational command for identity backfill. The command reprocesses supported historical source artifacts with full-rescan semantics and re-associates existing sessions to the current resolved local user and machine.

The operation must be idempotent. Existing sessions are updated through the current unique session identity rather than duplicated.

Proposed CLI:

```powershell
agentscope identity backfill
```

Optional arguments:

```text
--database
--source
--user-name
--machine-name
```

The command should report:

```text
sessions_scanned
sessions_updated
sessions_without_user
sessions_without_machine
errors
```

The existing `collect --full-rescan` remains valid, but the explicit backfill command makes the intended maintenance operation discoverable and testable.

### Filter semantics

`AnalyticsFilter.user` and `AnalyticsFilter.machine` continue to filter by display labels exposed by analytics. Unknown filter values return zero results, not an error.

The extension should only offer values returned by the snapshot dimension lists, preventing placeholder or stale values from being submitted through the UI.

## Cost semantics

The dashboard must distinguish three monetary concepts:

- `observed_cost_usd`: monetary cost explicitly reported by a source and attributable to the active filter;
- `estimated_cost_usd`: theoretical cost calculated from known pricing data when enough information exists;
- `estimated_savings_usd`: estimated savings from supported optimization/cache semantics.

Unknown values remain `null`, never `0`.

The UI must label values explicitly as `Observado` or `Estimado`. Estimated values must never be presented as provider billing facts.

When a value is unavailable, the snapshot should include a short machine-readable reason code where possible, for example:

```text
source_does_not_report_cost
insufficient_pricing_data
no_optimization_data
```

The webview maps these codes to concise user-facing explanations.

## Snapshot contract v2

Bump the extension snapshot contract to version 2 because new fields are added.

The snapshot keeps the existing summary and dimensions, and adds:

```json
{
  "summary": {
    "sessions": 0,
    "total_tokens": 0,
    "tokens_saved": 0,
    "cache_ratio": null,
    "observed_cost_usd": null,
    "estimated_cost_usd": null,
    "estimated_savings_usd": null
  },
  "availability": {
    "observed_cost": {"available": false, "reason": "source_does_not_report_cost"},
    "estimated_cost": {"available": false, "reason": "insufficient_pricing_data"},
    "estimated_savings": {"available": false, "reason": "no_optimization_data"}
  },
  "series": {
    "daily": []
  },
  "breakdowns": {
    "projects": [],
    "models": [],
    "sources": []
  }
}
```

Each daily point can contain:

```text
date
sessions
total_tokens
cache_ratio
observed_cost_usd
estimated_cost_usd
estimated_savings_usd
```

Breakdown entries expose only safe labels and aggregate metrics.

## Dashboard redesign

### Layout

The dashboard uses CSS grid with responsive breakpoints rather than fixed horizontal rows.

Desktop/wide panel:

```text
Header / actions
Filters
KPI cards
Trend charts
Breakdown charts
Data quality / availability notes
```

Narrow panel:

```text
Header
Actions
Filters stacked
KPI cards 1–2 columns
Charts stacked
```

### KPI cards

Primary cards:

- Sessões
- Total de tokens
- Tokens economizados
- Taxa de cache
- Custo observado
- Custo estimado
- Economia estimada

Cards with unavailable values show `Não disponível` plus an explanatory subtitle instead of appearing broken.

### Filters

Keep:

- period shortcuts;
- custom date range;
- project;
- model;
- source;
- user;
- machine.

Filters wrap cleanly in narrow panels and remain synchronized through the existing dashboard coordinator/filter state architecture.

## Charts

Charts represent usage, cost and efficiency, not developer productivity.

Required charts:

1. Sessions by day.
2. Tokens by day.
3. Observed cost vs estimated savings by day.
4. Cache ratio trend.
5. Usage by project.
6. Usage by model.
7. Usage by source.

For breakdown charts, the default measure is total tokens, with clear labels.

Charts must handle empty data and nullable monetary values without coercing them to zero.

## UI implementation approach

Prefer a lightweight local chart renderer compatible with VS Code webviews. No remote scripts or CDN dependencies are allowed because the current restrictive Content Security Policy should remain intact.

If an external chart library is introduced, it must be bundled with the extension and covered by the existing build process. The preferred approach is a small bundled library or simple SVG/canvas rendering rather than adding a large framework.

## Error and loading states

The dashboard must explicitly handle:

- loading snapshot;
- database not found;
- CLI unavailable;
- timeout;
- invalid snapshot version;
- empty filtered result;
- unavailable monetary metrics.

An empty filtered result is not an exception. The UI should show zero usage metrics and a clear `Nenhum dado encontrado para os filtros selecionados` state.

## Testing

### Python

Add tests for:

- identity backfill idempotency;
- historical sessions receiving user/machine associations;
- user and machine filtering after backfill;
- snapshot v2 contract;
- nullable cost semantics;
- daily series filtering;
- breakdown filtering;
- privacy sentinels.

### TypeScript

Add tests for:

- parsing snapshot v2;
- unavailable-value reason rendering;
- filter transitions for user/machine;
- responsive rendering state helpers;
- empty/loading/error states;
- chart data conversion preserving `null`.

### Verification

```powershell
python -m pytest -q
cd vscode-extension
npm run compile
npm run test:unit
npm test
```

The increment is complete only when the existing regression suite and new tests pass.

## Acceptance criteria

- Existing historical sessions can be backfilled without duplicate sessions.
- User and machine filters produce correct analytics after backfill.
- The extension only submits valid user/machine dimension values from the snapshot.
- Observed cost, estimated cost and estimated savings are separate fields and labels.
- Unknown monetary values remain `null`.
- Daily series and project/model/source breakdowns honor all active filters.
- Dashboard adapts to narrow and wide VS Code panels.
- Required charts render from snapshot data and handle empty/null values safely.
- No Team UI or central API is introduced.
- Python and VS Code test suites pass.