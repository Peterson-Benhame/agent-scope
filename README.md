# AgentScope

AgentScope is a local-first observability and analytics tool for AI coding and agent execution histories.

It ingests supported local histories, normalizes them into SQLite, and produces safe analytics for sessions, models, tokens, cache, tools, agents, skills, optimizer metrics, costs and savings. V2 also supports offline sanitized consolidation of multiple developer machines for team analytics.

## What it analyzes

- sessions and projects;
- models and token usage when exposed by the source;
- cached input usage when exposed by the source;
- agents/subagents when explicit evidence exists;
- skill availability, loading and invocation as separate states;
- tool/MCP calls when exposed by the source;
- Headroom compression and cache savings;
- observed/source-reported and estimated costs without presenting estimates as billing facts;
- trends by day, project, model, source, user and machine;
- filtered periods;
- offline team totals and per-user/project/source/model attribution.

Headroom is modeled as an **Optimizer**, not an Agent.

## Privacy

AgentScope is local-first and treats provider source files as read-only.

Safe reports and exports do not include complete prompt bodies, assistant responses, tool payloads or tool outputs. Full local message export requires the explicit `--full-content` option.

The local SQLite database can contain normalized message content imported from supported histories, so treat `data/agentscope.db` as sensitive. Team bundles are stricter and never export message bodies or raw provider payloads.

## Requirements

- Python 3.11+

## Installation

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

## Supported source adapters

Default roots on Windows:

```text
%USERPROFILE%\.codex\
%USERPROFILE%\.headroom\
%USERPROFILE%\.claude\
%USERPROFILE%\.copilot\
%USERPROFILE%\.kimi-code\
%USERPROFILE%\.gemini\
```

Registered adapters:

- `codex` — sessions, messages, tokens/cache, tools, agents and skills when explicitly evidenced;
- `headroom` — optimizer events, cache metrics and source-reported cost/savings;
- `claude_code` — verified JSONL sessions/messages/model/tokens/cache/tools;
- `github_copilot` — verified Copilot CLI session-state sessions/messages/model/tokens/cache/tools;
- `kimi` — documented session index + state metadata in this version;
- `gemini` — current JSONL session/messages/model/tokens/cache/tools.

See [`docs/provider-support.md`](docs/provider-support.md) for exact format contracts and limitations.

All registered sources are enabled by default. Restrict collection with:

```powershell
$env:AGENTSCOPE_SOURCES = "codex,claude_code,github_copilot"
agentscope collect
```

Provider root overrides:

```text
AGENTSCOPE_CODEX_HOME
AGENTSCOPE_HEADROOM_HOME
AGENTSCOPE_CLAUDE_HOME
AGENTSCOPE_COPILOT_HOME
AGENTSCOPE_KIMI_HOME
AGENTSCOPE_GEMINI_HOME
```

Unsupported local formats are reported as diagnostics and are not guessed.

## User and machine identity

Human user and machine are separate dimensions. Local collection creates stable keys from OS identity signals; display names are labels only and do not define uniqueness.

```powershell
$env:AGENTSCOPE_USER_NAME = "Dev A"
$env:AGENTSCOPE_MACHINE_NAME = "Notebook A"
agentscope collect
```

One user can therefore be associated with multiple machines without becoming multiple people in analytics.

## Local CLI

```powershell
agentscope collect
agentscope status
agentscope analyze
agentscope export
agentscope report
```

`analyze`, `export` and `report` share these filters:

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

Examples:

```powershell
agentscope report --period 7d
agentscope report --from 2026-08-01 --to 2026-08-18
agentscope analyze --project example-project --period 30d
agentscope report --user "Dev A" --machine "Notebook A" --period 30d
```

Custom `--from`/`--to` values are inclusive and override `--period`. Without period/date filters, all history is used.

Explicit full local message export:

```powershell
agentscope export --full-content
```

## Number and cost formatting

HTML reports use pt-BR presentation without changing SQLite precision:

```text
integer:      1.465.312.344
percentage:   94,63%
USD summary:  US$ 13,78
```

Observed/source-reported cost, estimated cost and savings remain separate. Unknown cost is `NULL`/`Não disponível`, never zero.

## Team workflow

The team architecture is offline and does not require a central server.

```text
Developer A                    Developer B
agentscope collect             agentscope collect
      ↓                              ↓
local agentscope.db            local agentscope.db
      ↓                              ↓
team export                    team export
      └──── sanitized bundles ──────┘
                    ↓
                 team.db
                    ↓
          agentscope team report
```

Export a sanitized bundle on each developer machine:

```powershell
agentscope team export `
  --database .\data\agentscope.db `
  --output .\team-bundle.json `
  --organization "Minha Empresa" `
  --team "Backend"
```

Import bundles into the consolidation database:

```powershell
agentscope team import .\dev-a.json --database .\data\team.db
agentscope team import .\dev-b.json --database .\data\team.db
```

Generate the consolidated report:

```powershell
agentscope team report `
  --database .\data\team.db `
  --output .\reports\team-report.html
```

The team report supports the same date/project/model/source/user/machine filters:

```powershell
agentscope team report --database .\data\team.db --period 30d
agentscope team report --database .\data\team.db --user "Dev A" --period month
```

It reports team totals plus usage, observed cost, estimated cost and estimated savings by user, project, source and model. Token volume is explicitly treated as usage, not productivity or developer performance.

### Team budget

Budget is optional:

```powershell
$env:AGENTSCOPE_MONTHLY_BUDGET_USD = "1000"
agentscope team report --database .\data\team.db
```

or per invocation:

```powershell
agentscope team report `
  --database .\data\team.db `
  --monthly-budget-usd 1000
```

Budget consumption uses observed cost only. Projection is a simple elapsed-month average and is labeled as a projection, not a billing forecast. Negative budgets are rejected.

### Team Bundle contract

The schema is `agentscope-team-bundle`, version `1`. `bundle_id` is a deterministic SHA-256 digest of the safe canonical payload.

Reimporting the same bundle does not duplicate totals. A newer overlapping bundle adds only events with new stable namespaced event keys.

Allowed telemetry can include stable user/machine keys, project name, session/source/model identifiers, token/cache metrics, normalized monetary fields, tool metadata, agent evidence and optimizer metrics.

The bundle excludes:

- prompt/user-message bodies;
- assistant response bodies;
- source code;
- tool arguments/payloads/results;
- attachments;
- environment variables and secrets;
- raw provider metadata;
- source file paths and local full project paths.

See [`docs/team-bundle.md`](docs/team-bundle.md) and [`docs/team-analytics.md`](docs/team-analytics.md).

## Data quality

Local and team reports expose quality/confidence indicators instead of pretending unknown values are zero.

Team quality includes identity confidence, tokens without a model, observed source coverage for token/cache/cost data, import errors and optimizer/session correlation confidence.

Unsupported-provider discovery diagnostics remain local in Team Bundle v1 and are therefore labeled unavailable in the team report instead of inferred.

## Default output

```text
data/agentscope.db
reports/
├── sessions.csv
├── token_usage.csv
├── costs.csv
├── agents.csv
├── skills.csv
├── tool_calls.csv
├── optimizations.csv
├── usage_by_project.csv
├── usage_by_model.csv
├── usage_by_user.csv
├── usage_by_machine.csv
├── usage_by_day.csv
├── datasets.json
└── report.html
```

Team outputs are chosen explicitly, for example:

```text
data/team.db
reports/team-report.html
```

## Cost semantics

AgentScope separates:

- **Estimated raw cost** — theoretical cost from a known pricing table when supported;
- **Observed/source-reported cost** — explicit monetary value present in a source and applicable as USD cost;
- **Compression savings** — optimizer compression savings;
- **Cache savings** — optimizer cache savings;
- **Total savings** — aggregate of known savings categories.

Headroom monetary fields remain source-reported optimizer metrics and are not automatically claimed as the final OpenAI/provider invoice. Non-USD provider credits or multipliers are not converted to USD spend.

## Development

Run the test suite:

```powershell
python -m pytest -q
```

Fixtures are synthetic and sanitized. Personal provider histories are not committed.

## Documentation

```text
docs/specs/README.md
docs/superpowers/specs/2026-08-18-multi-source-team-analytics-design.md
docs/superpowers/plans/2026-08-18-agentscope-v2-roadmap.md
docs/provider-support.md
docs/team-bundle.md
docs/team-analytics.md
```

## Current boundaries

AgentScope remains analytics-only. It does not route prompts, choose models/agents, modify provider histories, expose a central HTTP ingestion server, score developer performance, reconcile provider invoices, or provide a VS Code extension yet.
