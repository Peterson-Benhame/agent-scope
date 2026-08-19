# AgentScope

AgentScope is a local-first observability and analytics tool for agent execution histories.

The current implementation ingests OpenAI Codex session history and Headroom optimization metrics, normalizes them into SQLite, and produces safe CSV, JSON, and HTML analytics. Source collection is provider-neutral through a `SourceAdapter` registry so additional agent runtimes, tools, and optimizers can be added without redefining the analytics layer.

## What it analyzes

- sessions and projects;
- models and token usage;
- cached input usage;
- agents and subagents when explicit evidence exists;
- skill availability, loading, and invocation as separate states;
- tool and MCP calls;
- Headroom compression and cache savings;
- source-reported and estimated costs without presenting estimates as billing facts;
- trends by day, project, and model;
- filtered periods with comparison against the previous equivalent period.

Headroom is modeled as an **Optimizer**, not an Agent.

## Privacy

AgentScope is local-first and treats provider source files as read-only.

Safe metadata reporting is the default. Standard reports and exports do not include complete prompt bodies, assistant messages, tool inputs, or tool outputs. Full message export requires the explicit `--full-content` option.

The local SQLite database can contain message content imported from source histories. Treat `data/agentscope.db` as sensitive data.

## Requirements

- Python 3.11+

## Installation

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

## Default sources on Windows

```text
%USERPROFILE%\.codex\sessions\**\rollout-*.jsonl
%USERPROFILE%\.codex\session_index.jsonl
%USERPROFILE%\.codex\attachments\**
%USERPROFILE%\.headroom\proxy_savings.json
%USERPROFILE%\.headroom\*.jsonl
```

AgentScope never modifies these source files.

### Source adapters

`agentscope collect` discovers enabled source adapters before collection. The current implemented adapters are:

- `codex` — sessions, messages, tokens/cache, tools, agents and skills when explicit evidence exists;
- `headroom` — optimizer events, cache metrics and source-reported cost/savings data.

All registered sources are enabled by default. To restrict collection, set the comma-separated `AGENTSCOPE_SOURCES` environment variable:

```powershell
$env:AGENTSCOPE_SOURCES = "codex"
agentscope collect
```

Or enable both current sources explicitly:

```powershell
$env:AGENTSCOPE_SOURCES = "codex,headroom"
agentscope collect
```

A disabled adapter is not discovered or collected. `agentscope status` reports whether each enabled source was detected and how many supported artifacts were found.

## CLI

Collect new or changed local data:

```powershell
agentscope collect
```

During collection, AgentScope reports detected sources and shows an overall progress bar until it reaches 100%.

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

### Filter analytics by period

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

Filters can also restrict project, model, and source:

```powershell
agentscope analyze --project BN.S584.PerfilInvestidor --period 30d
agentscope export --model gpt-5.6-terra --period month
agentscope report --source codex --from 2026-08-01 --to 2026-08-18
```

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

Custom source/database paths are supported:

```powershell
agentscope collect `
  --codex-home "C:\Users\me\.codex" `
  --headroom-home "C:\Users\me\.headroom" `
  --database "D:\AgentScope\agentscope.db"
```

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
├── usage_by_day.csv
├── datasets.json
└── report.html
```

## Cost semantics

AgentScope deliberately separates different monetary concepts:

- **Estimated raw cost** — theoretical cost from a known pricing table, when configured and supported;
- **Observed/source-reported cost** — value explicitly present in an imported source;
- **Compression savings** — savings reported or derived from optimizer compression data;
- **Cache savings** — savings reported by cache-aware optimizer data;
- **Total savings** — aggregate of known savings categories.

Unknown cost is stored as `NULL`, never as zero.

Headroom cost/savings fields are labeled as source-reported optimizer metrics. They are not automatically treated as the final amount charged by OpenAI or another provider.

## Data confidence

AgentScope does not pretend inferred correlation is exact. Optimizer-to-session correlation is classified as:

```text
exact
high
medium
unknown
```

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

The test fixtures are synthetic and sanitized. Personal Codex histories are not committed.

## Project documentation

The V1 specifications are in [`docs/specs`](docs/specs/README.md).

The V2 multi-source/team design and ordered implementation plans are in:

```text
docs/superpowers/specs/2026-08-18-multi-source-team-analytics-design.md
docs/superpowers/plans/2026-08-18-agentscope-v2-roadmap.md
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

The approved V2 roadmap adds more provider adapters and offline sanitized team export/import before any central server is considered.
