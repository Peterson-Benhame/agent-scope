# AgentScope Team Analytics

AgentScope Team consolidates sanitized telemetry exported from individual developer machines into a separate SQLite database. It is an offline analytics workflow; there is no central AgentScope server in the current architecture.

## Workflow

```text
Developer A                    Developer B
agentscope collect             agentscope collect
      ↓                              ↓
local agentscope.db            local agentscope.db
      ↓                              ↓
team export                    team export
      └──── sanitized bundles ──────┘
                    ↓
             consolidated team.db
                    ↓
          agentscope team report
```

Example:

```powershell
# on each developer machine
agentscope collect
agentscope team export `
  --database .\data\agentscope.db `
  --output .\team-bundle.json `
  --organization "Minha Empresa" `
  --team "Backend"

# on the machine that consolidates the team
agentscope team import .\dev-a.json --database .\data\team.db
agentscope team import .\dev-b.json --database .\data\team.db
agentscope team report --database .\data\team.db --output .\reports\team.html
```

## Filters

The team report uses the same filter contract as local analytics:

```text
--from YYYY-MM-DD
--to YYYY-MM-DD
--period today|7d|30d|month
--project
--model
--source
--user
--machine
```

Custom `--from`/`--to` values are inclusive and override `--period`.

Examples:

```powershell
agentscope team report --database .\data\team.db --period 30d
agentscope team report --database .\data\team.db --user "Dev A" --period month
agentscope team report --database .\data\team.db --project "Projeto A" --from 2026-08-01 --to 2026-08-31
```

## Team metrics

The report includes:

- developer, machine and session counts;
- total/input/output/cached token usage;
- cache ratio;
- observed/source-reported USD cost when present;
- estimated raw USD cost when present;
- estimated savings from normalized cost/optimizer data;
- usage, cost and savings attribution by user, project, source and model;
- daily usage trend;
- data-quality indicators.

Token volume is an operational usage metric. AgentScope does not label token volume as productivity, performance, code quality or developer effectiveness.

## Cost semantics

Monetary fields remain separate:

```text
Observed/source-reported cost
Estimated raw cost
Estimated savings
```

A missing cost remains `NULL`/`Não disponível`; it is not converted to zero. Provider credits or multipliers that are not verified USD billing values are not presented as USD spend.

When a normalized `costs.total_savings_usd` value exists for a session, team savings attribution uses it. Optimizer compression/cache savings are used as fallback for sessions without that normalized cost-savings value, preventing the same savings from being counted twice.

## Budget

Budget tracking is optional.

Environment configuration:

```powershell
$env:AGENTSCOPE_MONTHLY_BUDGET_USD = "1000"
agentscope team report --database .\data\team.db
```

Per-command override:

```powershell
agentscope team report `
  --database .\data\team.db `
  --monthly-budget-usd 1000
```

The budget section uses observed spend only. If observed cost is unavailable, consumed ratio and projection remain unavailable.

Projection formula:

```text
observed spend / elapsed days × days in month
```

It is a simple projection, not a billing forecast or invoice. Negative budgets are rejected.

## Data quality

The team report exposes:

- identity-confidence distribution;
- share of tokens without a known model;
- observed token/cache/cost coverage by source;
- import-error count;
- optimizer/session correlation-confidence distribution.

`source_coverage` means data observed in the consolidated database. It is not the same as the adapter's declared capabilities.

Unsupported-provider discovery diagnostics are not carried by Team Bundle version 1. The team report therefore marks that diagnostic field as unavailable instead of inventing or inferring a value. Provider diagnostics remain available locally through `agentscope status` and `agentscope collect`.

## Privacy

The consolidated team database is built from `agentscope-team-bundle` version 1. Team bundles exclude prompt bodies, assistant responses, source code, tool payloads/results, raw provider metadata, attachments, environment variables, secrets, source file paths and local full project paths.

Team reports are generated only from the sanitized normalized team database. They must not contain the local privacy sentinels used in tests.

Even sanitized telemetry is internal operational data: user labels, project names, models, timestamps, token counts and costs can be sensitive in a company context.

## Idempotency

Importing the same bundle repeatedly does not increase totals. Importing a newer overlapping bundle inserts only records whose stable namespaced event keys are new.

This allows teams to exchange periodic snapshots without needing a central synchronization service.

## Current boundary

AgentScope Team currently provides offline consolidation and reporting. It does not provide:

- central HTTP ingestion;
- authentication/authorization server;
- real-time dashboards;
- developer performance scoring;
- provider billing reconciliation;
- automatic model routing or prompt modification.
