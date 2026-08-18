# AgentScope

AgentScope is a local-first observability and analytics tool for agent execution histories.

The V1 ingests OpenAI Codex session history and Headroom optimization metrics, normalizes them into SQLite, and produces safe CSV, JSON, and HTML analytics. The core model is provider-neutral so additional agent runtimes, tools, and optimizers can be added later without redefining the analytics layer.

## What it analyzes

- sessions and projects;
- models and token usage;
- cached input usage;
- agents and subagents when explicit evidence exists;
- skill availability, loading, and invocation as separate states;
- tool and MCP calls;
- Headroom compression and cache savings;
- source-reported and estimated costs without presenting estimates as billing facts;
- trends by day, project, and model.

Headroom is modeled as an **Optimizer**, not an Agent.

## Privacy

AgentScope is local-first and treats Codex and Headroom source files as read-only.

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

## CLI

Collect new or changed local data:

```powershell
agentscope collect
```

Inspect source and database status:

```powershell
agentscope status
```

Show the current aggregate analytics:

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

Explicitly export full message content:

```powershell
agentscope export --full-content
```

Custom paths are supported:

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
python -m pytest
```

The test fixtures are synthetic and sanitized. Personal Codex histories are not committed.

## Project documentation

The V1 specifications are in [`docs/specs`](docs/specs/README.md). The implementation plan is in [`docs/superpowers/plans`](docs/superpowers/plans/2026-08-18-agentscope-v1.md).

## V1 boundaries

The current release is analytics-only. It does not:

- route prompts;
- select agents or models;
- recommend models;
- modify Codex or Headroom;
- expose an HTTP API;
- provide a VS Code extension yet.

A future VS Code extension can consume the SQLite/JSON/CLI outputs without changing the V1 ingestion model.
