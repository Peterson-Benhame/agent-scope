# AgentScope

AgentScope is a local-first observability and analytics tool for agent execution histories.

The current implementation ingests local histories from multiple AI development tools, normalizes them into SQLite, and produces safe CSV, JSON, and HTML analytics. Source collection is provider-neutral through a `SourceAdapter` registry so additional agent runtimes, tools, and optimizers can be added without redefining the analytics layer.

## What it analyzes

- sessions and projects;
- models and token usage when exposed by the source;
- cached input usage when exposed by the source;
- agents and subagents when explicit evidence exists;
- skill availability, loading, and invocation as separate states;
- tool and MCP calls when exposed by the source;
- Headroom compression and cache savings;
- source-reported and estimated costs without presenting estimates as billing facts;
- trends by day, project, model, user, and machine;
- filtered periods with comparison against the previous equivalent period.

Headroom is modeled as an **Optimizer**, not an Agent.

## Privacy

AgentScope is local-first and treats provider source files as read-only.

Safe metadata reporting is the default. Standard reports and exports do not include complete prompt bodies, assistant messages, tool inputs, or tool outputs. Full message export requires the explicit `--full-content` option.

The local SQLite database can contain message content imported from supported source histories. Treat `data/agentscope.db` as sensitive data.

## Requirements

- Python 3.11+

## Installation

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

## Default source roots on Windows

```text
%USERPROFILE%\.codex\
%USERPROFILE%\.headroom\
%USERPROFILE%\.claude\
%USERPROFILE%\.copilot\
%USERPROFILE%\.kimi-code\
%USERPROFILE%\.gemini\
```

AgentScope never modifies these source files.

### Source adapters

`agentscope collect` discovers enabled source adapters before collection. The registered V2 adapters are:

- `codex` — sessions, messages, tokens/cache, tools, agents and skills when explicit evidence exists;
- `headroom` — optimizer events, cache metrics and source-reported cost/savings data;
- `claude_code` — verified JSONL sessions/messages/model/tokens/cache/tools;
- `github_copilot` — verified Copilot CLI session-state events with sessions/messages/model/tokens/cache/tools;
- `kimi` — documented session index + state metadata only in this version;
- `gemini` — current JSONL conversation sessions/messages/model/tokens/cache/tools.

Provider-specific details and limitations are documented in [`docs/provider-support.md`](docs/provider-support.md).

All registered sources are enabled by default. To restrict collection, set the comma-separated `AGENTSCOPE_SOURCES` environment variable:

```powershell
$env:AGENTSCOPE_SOURCES = "codex,claude_code,github_copilot"
agentscope collect
```

Supported source names are:

```text
codex
headroom
claude_code
github_copilot
kimi
gemini
```

A disabled adapter is not discovered or collected. `agentscope status` reports whether each enabled source was detected, how many supported artifacts were found and any unsupported-format diagnostic.

Provider root overrides are available through:

```text
AGENTSCOPE_CODEX_HOME
AGENTSCOPE_HEADROOM_HOME
AGENTSCOPE_CLAUDE_HOME
AGENTSCOPE_COPILOT_HOME
AGENTSCOPE_KIMI_HOME
AGENTSCOPE_GEMINI_HOME
```

### User and machine identity

AgentScope keeps the human user and the machine as separate dimensions. Local collection creates stable hashed keys from local OS identity signals and records the local user with confidence `inferred`; a provider identity may later be recorded as `exact` only when the provider exposes explicit safe evidence.

Display names are labels only and never uniqueness keys. They can be customized without changing stable identity:

```powershell
$env:AGENTSCOPE_USER_NAME = "Dev A"
$env:AGENTSCOPE_MACHINE_NAME = "Notebook A"
agentscope collect
```

A user can therefore be associated with multiple machines without being counted as a different person solely because the equipment changed.

## CLI

Collect new or changed local data:

```powershell
agentscope collect
```

During collection, AgentScope reports detected sources and shows an overall progress bar until it reaches 100%. Unsupported local formats are reported as diagnostics instead of being guessed.

Inspect source and database status:

```powershell
agentscope status
```

Show aggregate analytics:

```powershell
agentscope analyze
```

Generate safe CSV and JSON datasets:

```powershell
agentscope export
```

Generate the local HTML report:

```powershell
agentscope report
```

### Filter analytics

The `analyze`, `export`, and `report` commands share the same filters.

```powershell
agentscope report --period today
agentscope report --period 7d
agentscope report --period 30d
agentscope report --period month
```

Use an inclusive custom range:

```powershell
agentscope report --from 2026-08-01 --to 2026-08-18
```

Custom `--from`/`--to` values override `--period`. Dates use ISO `YYYY-MM-DD` and are inclusive. With no period/date filter, AgentScope preserves the all-history behavior.

Filters can restrict project, model, source, user, and machine:

```powershell
agentscope analyze --project BN.S584.PerfilInvestidor --period 30d
agentscope export --model gpt-5.6-terra --period month
agentscope report --source codex --from 2026-08-01 --to 2026-08-18
agentscope report --user "Dev A" --machine "Notebook A" --period 30d
```

User/machine filters accept the display label used in analytics. The safe session export also carries the corresponding stable keys so offline team consolidation can preserve identity without relying on display names.

The filtered HTML report displays the selected period and, for bounded periods, compares key metrics with the immediately preceding equivalent period.

### Report number and cost formatting

The HTML report uses pt-BR display conventions without changing numeric precision stored in SQLite:

```text
integer:      1.465.312.344
percentage:   94,63%
USD summary:  US$ 13,78
```

Detailed technical values may preserve additional decimal precision when useful. Observed/source-reported costs remain distinct from estimated values and estimated savings.

Explicitly export full message content:

```powershell
agentscope export --full-content
```

When filters are used with `--full-content`, the full-message export obeys the same selected filters.

Custom Codex/Headroom paths remain available as CLI options:

```powershell
agentscope collect `
  --codex-home "C:\Users\me\.codex" `
  --headroom-home "C:\Users\me\.headroom" `
  --database "D:\AgentScope\agentscope.db"
```

Use the environment overrides above for the additional provider roots.

## Team bundles

Each developer can keep collection local and export only sanitized telemetry for offline consolidation:

```powershell
agentscope team export `
  --database .\data\agentscope.db `
  --output .\team-bundle.json `
  --organization "Minha Empresa" `
  --team "Backend"
```

The bundle can use the same date, project, model, source, user and machine filters as local analytics. Its schema is `agentscope-team-bundle`, version `1`, with a deterministic SHA-256 `bundle_id` derived from the safe payload.

Import bundles from multiple developer machines into a separate team database:

```powershell
agentscope team import .\team-bundle-dev-a.json --database .\data\team.db
agentscope team import .\team-bundle-dev-b.json --database .\data\team.db
```

Reimporting the same bundle does not duplicate totals. A regenerated bundle that overlaps prior data inserts only events with new stable namespaced event keys.

Team bundles are allow-list based. They may include stable user/machine identifiers, project name, session identifiers, source/model names, token/cache metrics, monetary metrics already normalized by AgentScope, tool-call metadata, agent evidence and optimizer metrics. They do **not** include prompt bodies, assistant responses, source code, tool payloads/results, attachments, environment variables, secrets, raw provider metadata or source file paths.

See [`docs/team-bundle.md`](docs/team-bundle.md) for the exact privacy and idempotency contract.

## Output

Default database:

```text
data/agentscope.db
```

Default reports:

```text
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

## Cost semantics

AgentScope deliberately separates different monetary concepts:

- **Estimated raw cost** — theoretical cost from a known pricing table, when configured and supported;
- **Observed/source-reported cost** — value explicitly present in an imported source as an applicable monetary value;
- **Compression savings** — savings reported or derived from optimizer compression data;
- **Cache savings** — savings reported by cache-aware optimizer data;
- **Total savings** — aggregate of known savings categories.

Unknown cost is stored as `NULL`, never as zero.

Headroom cost/savings fields are labeled as source-reported optimizer metrics. They are not automatically treated as the final amount charged by OpenAI or another provider. Non-USD provider credits/multipliers are not written as USD cost.

## Data confidence

AgentScope does not pretend inferred correlation is exact. Optimizer-to-session correlation is classified as:

```text
exact
high
medium
unknown
```

Local user identity uses the same principle: inferred OS identity is marked `inferred`; an exact provider identity is only used when explicit provider evidence exists.

Likewise, a skill being available does not prove it was used. AgentScope records:

```text
available
loaded
invoked
```

separately.

## Development

Run the full test suite:

```powershell
python -m pytest -q
```

The test fixtures are synthetic and sanitized. Personal provider histories are not committed.

## Project documentation

The V1 specifications are in [`docs/specs`](docs/specs/README.md).

The V2 multi-source/team design and ordered implementation plans are in:

```text
docs/superpowers/specs/2026-08-18-multi-source-team-analytics-design.md
docs/superpowers/plans/2026-08-18-agentscope-v2-roadmap.md
docs/provider-support.md
docs/team-bundle.md
```

## Current boundaries

AgentScope remains analytics-only. It does not:

- route prompts;
- select agents or models;
- recommend models;
- modify provider histories;
- expose an HTTP API;
- provide a central team server;
- provide a VS Code extension yet.

The V2 team workflow consolidates sanitized bundles offline; a central server remains outside the current scope.
