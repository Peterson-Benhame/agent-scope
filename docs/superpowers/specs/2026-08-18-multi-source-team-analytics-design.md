# AgentScope V2 — Multi-source adapters and team analytics

Date: 2026-08-18
Status: Proposed design for implementation
Scope: local multi-source collection, filtered analytics, sanitized team export/import, and team reporting. No central server in this phase.

## 1. Context

AgentScope V1 collects local Codex and Headroom history, normalizes it into SQLite, and generates local analytics/reports. The next evolution must support additional AI development tools, improve report quality, associate usage with a person/machine, and consolidate multiple developers without sending source code, prompts, responses, or tool payloads to a central service.

The chosen approach is an adapter architecture plus offline sanitized team bundles. Each machine remains local-first. Team consolidation happens by exporting safe metadata from each machine and importing those bundles into a separate AgentScope database. A network server/API is explicitly deferred.

## 2. Goals

1. Filter all analytics and reports by period, project, model, source, user, and machine.
2. Standardize report terminology and pt-BR numeric/money formatting.
3. Reduce false-positive skills/models/agents and expose data-confidence semantics.
4. Replace hard-coded source collection with a provider-neutral SourceAdapter contract and registry.
5. Support Codex, Headroom, Claude Code, GitHub Copilot, Kimi, and Gemini through separate adapters.
6. Detect available sources automatically while allowing each source to be disabled.
7. Add user and machine identity with explicit confidence (`exact`, `inferred`, `unknown`).
8. Export a sanitized, versioned team telemetry bundle containing metadata only.
9. Import bundles idempotently into a team analytics database.
10. Generate team reports by user, machine, project, source, model, date, cost, savings, cache, tools, and agents.
11. Preserve backward compatibility with existing AgentScope SQLite databases through migrations.
12. Preserve local-first/privacy guarantees.

## 3. Non-goals

The following are out of scope for this phase:

- hosted AgentScope server;
- HTTP API;
- authentication/authorization service;
- real-time streaming telemetry;
- VS Code extension;
- centralized remote database;
- prompt/response/code collection for team analytics;
- automatic decryption of any provider data;
- billing-provider reconciliation beyond source-reported or explicitly estimated cost;
- productivity scoring or employee ranking from token consumption alone.

## 4. Architectural principles

### 4.1 Local-first

Raw provider history remains on the developer machine. Adapters read source data in read-only mode. AgentScope never edits provider files.

### 4.2 Explicit adapters, no generic log guessing

Each provider has a dedicated adapter. AgentScope must not recursively ingest arbitrary JSON/JSONL/SQLite files and guess their meaning. This prevents the false positives currently visible in skills/model detection.

### 4.3 Normalized model, source-specific evidence

Provider-specific formats are converted into shared domain entities. The normalized entity preserves source metadata/evidence needed for auditability.

### 4.4 Unknown is not zero

If a provider does not expose cost, agent, skill, token, cache, or other data, the normalized value is unavailable/null. Reports must never convert missing information into zero.

### 4.5 Confidence is first-class data

Inferred user identity, model mapping, agent correlation, optimization correlation, and other uncertain mappings carry explicit confidence.

### 4.6 Privacy by default

Team exports exclude message bodies, prompt contents, assistant responses, tool inputs/outputs, code, attachments, environment variables, credentials, secrets, and raw provider files.

## 5. High-level architecture

```text
Codex -----------\
Claude Code ------\
GitHub Copilot ----> SourceRegistry -> SourceAdapter -> normalized domain -> SQLite
Kimi -------------/
Gemini -----------/
Headroom --------/
                                           |
                                           +-> filtered local analytics/report
                                           |
                                           +-> sanitized TeamBundle export
                                                        |
                                                        v
                                               team import database
                                                        |
                                                        v
                                                team analytics/report
```

## 6. SourceAdapter framework

Introduce a provider-neutral interface. Exact Python names may vary during implementation, but the responsibilities are fixed.

```python
class SourceAdapter(Protocol):
    source_name: str

    def discover(self, context: DiscoveryContext) -> SourceDiscovery: ...
    def capabilities(self) -> SourceCapabilities: ...
    def collect(self, request: CollectRequest) -> Iterable[NormalizedBatch]: ...
```

### 6.1 SourceDiscovery

Contains:

- source name;
- detected/not detected;
- source root paths;
- format/version when discoverable;
- discovered artifacts count;
- diagnostic message when unsupported/unreadable.

### 6.2 SourceCapabilities

Capabilities are explicit nullable-data contracts:

```text
sessions
messages
tokens
cache
costs
tools
agents
skills
optimizations
user_identity
```

A capability indicates that an adapter can potentially provide the metric. It does not imply that every session contains it.

### 6.3 SourceRegistry

`SourceRegistry` owns adapter registration and discovery order. `agentscope collect` asks the registry to discover all enabled adapters and then collects detected sources.

Default enabled adapters after this phase:

- Codex;
- Headroom;
- Claude Code;
- GitHub Copilot;
- Kimi;
- Gemini.

A configuration entry can disable individual sources without uninstalling support.

### 6.4 Migration of existing collectors

Current Codex and Headroom parsing logic is retained but wrapped behind the adapter contract. Existing normalization and idempotency semantics must remain compatible with current databases.

## 7. Provider adapters

### 7.1 CodexAdapter

Responsibilities:

- discover existing Codex session roots;
- parse rollout/session artifacts already supported by V1;
- normalize sessions, turns, messages, token usage, tools, agents/skills evidence when explicit;
- preserve encrypted reasoning content as opaque metadata only; never decrypt it;
- infer local user identity only when no exact provider identity is available.

### 7.2 HeadroomAdapter

Responsibilities:

- discover Headroom state root;
- import proxy/lifetime snapshot data with replace/upsert semantics rather than accumulation;
- import session stats/savings events without duplication;
- normalize optimizer/savings/cost evidence;
- preserve correlation confidence.

Headroom remains an optimizer/source of optimization evidence, not an AI agent.

### 7.3 ClaudeCodeAdapter

Responsibilities:

- discover supported local Claude Code history locations;
- detect supported format/version before parsing;
- parse only known supported records;
- normalize available sessions/messages/models/tokens/tools/agents/user evidence;
- record unsupported-version diagnostics instead of guessing.

### 7.4 GitHubCopilotAdapter

Responsibilities:

- discover supported local Copilot CLI/session stores;
- read supported SQLite/files in read-only mode;
- normalize session/model/token/tool/user metadata when exposed;
- keep unavailable cost/billing values null unless source data explicitly supports them.

### 7.5 KimiAdapter

Responsibilities:

- discover Kimi local session/context storage;
- parse only documented/verified formats;
- normalize available session/message/model/token/tool metadata;
- preserve unknown fields as source metadata only when safe.

### 7.6 GeminiAdapter

Responsibilities:

- discover Gemini CLI persisted sessions;
- parse supported local session records;
- normalize session/message/model/token/tool/user evidence where available;
- use the same unsupported-version behavior as other adapters.

### 7.7 Future adapters

The contract must allow later addition of Cursor, Windsurf, other CLI agents, and provider-specific optimizers without schema redesign.

## 8. User and machine identity

Add normalized user and machine concepts.

### 8.1 User

Suggested fields:

```text
id
stable_key
display_name
provider_user_id (nullable)
provider/source (nullable)
identity_confidence
metadata_json
```

Identity confidence:

- `exact`: provider supplies an account/user identifier that is safe to persist;
- `inferred`: derived from local OS user or configured identity;
- `unknown`: no reliable identity available.

Email must not be required. If an email-like identifier is ever exported to a team bundle, default behavior should hash or omit it unless explicitly enabled.

### 8.2 Machine

Suggested fields:

```text
id
stable_machine_key
display_name
os
metadata_json
```

A user can own/use multiple machines. A machine is not a user identity.

### 8.3 Session association

Each session may reference `user_id` and `machine_id`. Existing sessions migrate with nullable values. Subsequent collection resolves local machine/user once per run and attaches them to imported sessions.

## 9. Filtered analytics

Introduce `AnalyticsFilter` shared by CLI, HTML report, exports, and later UI integrations.

Suggested fields:

```text
from_date/to_date
project
model
source
user
machine
```

Date semantics:

- timestamps are compared using normalized ISO timestamps;
- user CLI dates are interpreted in local timezone and converted consistently;
- date-only `to` means through the end of that local day;
- all report sections use the same filter object;
- empty filters preserve V1 all-history behavior.

CLI examples:

```text
agentscope report --from 2026-08-01 --to 2026-08-18
agentscope report --period today
agentscope report --period 7d
agentscope report --period month
agentscope analyze --project BN.S584.PerfilInvestidor --period 30d
```

Initial period aliases:

- `today`;
- `7d`;
- `30d`;
- `month`.

Custom `--from/--to` overrides aliases.

## 10. Report V2

### 10.1 Formatting

Use centralized formatting helpers.

pt-BR display conventions:

```text
integer:      1.465.312.344
percentage:   94,63%
USD summary:  US$ 13,78
USD detail:   precision may be higher when technically useful
```

Terminology changes:

- `Fichas` -> `Tokens`;
- `Fichas salvas` -> `Tokens economizados`;
- `Poupança` -> `Economia`;
- `Total savings` -> `Economia estimada` when derived/estimated;
- source-reported values remain explicitly labeled `observado/reportado pela fonte`.

### 10.2 Executive summary

Show at least:

- selected period;
- sessions;
- total tokens;
- tokens saved;
- cache ratio;
- observed/source-reported cost;
- estimated savings;
- comparison with previous equivalent period when applicable.

### 10.3 Dimensions

Report sections support the shared filter and include:

- by day;
- by project;
- by source/provider;
- by model;
- by user;
- by machine;
- agents;
- skills;
- tools/MCPs;
- optimizers;
- cost and savings.

### 10.4 Data quality

Add a visible data-quality section:

- import errors;
- unsupported provider versions;
- unknown model share;
- identity confidence distribution;
- optimization correlation confidence;
- adapter capability coverage.

## 11. Data quality corrections

### 11.1 Skills

A normalized skill may only be created from explicit provider evidence or a provider-specific pattern with tests. Arbitrary filenames, identifiers, source-code names, and natural-language words must not be classified as skills.

Statuses remain:

- `available`;
- `loaded`;
- `invoked`.

An adapter must not infer `invoked` from mere availability.

### 11.2 Models

Model normalization uses explicit provider fields first. Non-model labels such as review modes or workflow names must not become model records. Unknown model remains `unknown` with source evidence available for debugging.

### 11.3 Agents

Agent/subagent evidence must be explicit or provider-specific with confidence. Generic root labels should not be used to fabricate agent identities.

## 12. Database migrations

Introduce schema migration version 2 (or subsequent ordered migrations if implementation is split).

Expected additions:

- `users`;
- `machines`;
- nullable `sessions.user_id`;
- nullable `sessions.machine_id`;
- optional normalized/source capability metadata;
- team import state/bundle provenance tables;
- indexes for date/user/machine/source filtering.

Migrations must be additive where possible. Existing `agentscope.db` databases must open and migrate without deleting V1 data.

Migration tests must start from a representative V1 database schema and verify data remains queryable after migration.

## 13. Team telemetry bundle

### 13.1 Command

```text
agentscope team export --output <file>
```

The export is deterministic, versioned, and safe by default.

### 13.2 Bundle envelope

Suggested envelope:

```json
{
  "schema": "agentscope-team-bundle",
  "version": 1,
  "bundle_id": "...",
  "generated_at": "...",
  "organization": null,
  "team": null,
  "user": {...},
  "machine": {...},
  "records": {...}
}
```

The implementation may use JSON or compressed JSON, but the schema/version contract is mandatory.

### 13.3 Allowed data

Allowed by default:

- user stable identifier/display label;
- machine stable identifier/display label;
- project normalized name/key (not full source-code content);
- session stable ID;
- date/time;
- source/provider;
- model;
- token counts;
- cache counts/ratio inputs;
- observed/estimated cost fields with semantics;
- savings fields;
- tool names/categories/counts;
- agent names/types when already safe metadata;
- optimizer metrics;
- confidence/capability metadata.

### 13.4 Forbidden data

The bundle must not contain by default:

- prompts;
- assistant responses;
- message bodies;
- source code;
- tool request/response payloads;
- tool output content;
- attachments;
- raw file contents;
- environment variables;
- credentials/tokens/secrets;
- full filesystem paths when a normalized project label is sufficient.

A test must scan serialized bundles for fixture secrets/prompt/code markers and fail if any leak.

## 14. Team import

Command:

```text
agentscope team import <bundle>
```

Requirements:

- validate schema/version before writes;
- reject unsupported/invalid bundles with a clear error;
- import within transaction boundaries;
- use stable event/bundle keys for idempotency;
- importing the same bundle twice must not double counts;
- importing regenerated bundles containing already-seen events must not double counts;
- preserve provenance: originating bundle, user, machine, and source;
- never merge distinct users/machines solely by display name.

## 15. Team analytics and report

The team database uses the same normalized analytics layer. New dimensions include user and machine.

Required team metrics:

- developers/users count;
- machines count;
- sessions;
- total/input/cached/output tokens;
- cache ratio;
- observed/source-reported cost;
- estimated cost where available;
- compression/cache/total savings with semantics;
- cost by user;
- tokens by user;
- savings by user;
- cost/tokens by project;
- cost/tokens by source;
- cost/tokens by model;
- daily trends;
- data-quality coverage.

Optional-but-in-scope if underlying cost data is available:

- configured monthly team budget;
- budget consumption percentage;
- simple end-of-period projection based on elapsed-period average.

The report must not label token volume as developer productivity or performance.

## 16. Configuration

Extend local configuration with:

- enabled/disabled source adapters;
- optional local user display identity override;
- optional machine display name override;
- optional team/organization labels for bundle metadata;
- optional monthly budget;
- privacy/export options that remain safe-by-default.

Provider paths remain auto-detected by default with explicit overrides available for tests and unusual installations.

## 17. Progress and failure behavior

The existing progress callback remains provider-neutral and should be moved/extended so SourceRegistry can report:

```text
discovering sources
source detected/not detected
collecting source artifact N/M
source completed
source failed
overall complete
```

A failure in one adapter must be recorded and reported without corrupting successful imports from other adapters. Whether the CLI exits non-zero follows current aggregate error semantics.

## 18. Idempotency

Idempotency is required at three layers:

1. local source import;
2. normalized event persistence;
3. team bundle import.

Stable source/event keys must include enough source provenance to avoid collisions across providers, machines, and sessions. Snapshot-style metrics (for example Headroom lifetime snapshots) retain replacement/upsert semantics instead of cumulative append semantics.

Interrupted collection may re-read an incomplete source artifact; uniqueness/upsert rules must prevent duplicate normalized events.

## 19. Testing strategy

All implementation work follows TDD.

### 19.1 Unit tests

- source discovery per adapter;
- capabilities per adapter;
- parser fixtures per supported format/version;
- unsupported-version behavior;
- user/machine identity confidence;
- date filter boundaries/timezone behavior;
- pt-BR formatting;
- skill/model/agent classification rules;
- team bundle sanitization;
- team bundle schema validation;
- idempotent team import.

### 19.2 Integration tests

- collect from multiple adapters in one run;
- one failing adapter does not corrupt successful adapters;
- V1 database migrates to V2 without data loss;
- filtered analytics match fixture expectations;
- report all-history remains backward compatible;
- team export from one DB -> import into another -> analytics totals match safe source metrics;
- reimport same/regenerated bundle produces identical totals.

### 19.3 Privacy regression test

Fixtures include sentinel prompt/code/secret values. Team bundle serialization must be asserted not to contain any sentinel value.

### 19.4 CI

GitHub Actions runs supported Python versions and the complete pytest suite. Provider fixtures are synthetic/sanitized and committed to the repository; tests must not depend on a developer's real local history.

## 20. Delivery decomposition

Implementation is split into ordered, independently verifiable increments.

### Increment A — Analytics/report foundation

- AnalyticsFilter and date aliases;
- all analytics methods respect filter;
- CLI report/analyze/export filters;
- centralized pt-BR formatting;
- report terminology/summary improvements;
- period comparison;
- tests.

### Increment B — Data quality hardening

- skill false-positive correction;
- model normalization correction;
- agent evidence correction;
- confidence/data-quality metrics;
- tests.

### Increment C — Adapter framework

- SourceAdapter contract;
- SourceCapabilities;
- SourceRegistry;
- migrate Codex and Headroom behind adapters;
- preserve collect progress/idempotency;
- tests.

### Increment D — User/machine model

- schema migration;
- identity resolution/confidence;
- session association;
- analytics by user/machine;
- tests.

### Increment E — New provider adapters

Implement and test, one adapter per reviewable change:

1. Claude Code;
2. GitHub Copilot;
3. Kimi;
4. Gemini.

Each adapter requires verified fixtures/format evidence before declaring a capability supported.

### Increment F — Team bundle

- versioned sanitized export;
- privacy regression tests;
- schema validation;
- idempotent import;
- provenance;
- tests.

### Increment G — Team analytics/report

- user/machine/team dimensions;
- costs/savings/tokens by dimension;
- budget configuration and simple projection when applicable;
- data-quality section;
- end-to-end export/import/report test.

## 21. Acceptance criteria

The phase is complete when all of the following are true:

1. Existing V1 database migrates without deleting or duplicating existing records.
2. `agentscope collect` automatically detects enabled supported sources and still works with only Codex/Headroom installed.
3. Codex and Headroom behavior remains compatible with V1 semantics.
4. Claude Code, GitHub Copilot, Kimi, and Gemini have separate tested adapters for verified supported local formats.
5. Unsupported provider versions are reported, not guessed.
6. Reports can filter by date range and the implemented dimensions.
7. Report money uses pt-BR display conventions and clear observed/estimated semantics.
8. Skills no longer classify arbitrary filenames/words as skills in regression fixtures.
9. User and machine identities are separate and carry confidence.
10. Team export contains no prompt/response/code/tool payload/secret sentinel values.
11. Importing a team bundle repeatedly does not change totals after the first successful import.
12. Team report can aggregate tokens/cost/savings by user, project, source, model, machine, and period where those fields are available.
13. Missing provider data displays as unavailable, not zero.
14. All tests and GitHub Actions checks pass.
15. README/docs describe local collection, source support, filters, privacy semantics, team export/import, and limitations.

## 22. Risks and mitigations

### Provider local formats change

Mitigation: adapters are version-aware, fixtures cover known formats, unsupported versions fail explicitly, and provider-specific parsing is isolated.

### False confidence in cost values

Mitigation: preserve `observed/source-reported`, `estimated`, and `unavailable` semantics separately. Never combine values silently when methodologies differ.

### Sensitive information leaks into team exports

Mitigation: allow-list bundle fields rather than deny-list fields; privacy sentinel tests; normalized project labels instead of full paths by default.

### Identity collisions

Mitigation: stable keys plus source/machine context; display names are labels, never uniqueness keys.

### Scope expansion into a SaaS/server product

Mitigation: no network service in this phase. Team aggregation is file-based export/import only.

## 23. Future phase

After offline team analytics proves useful, a separate design may introduce `AgentScope Team Server` using the same TeamBundle/normalized contracts for authenticated ingestion, centralized storage, dashboards, budgets, and alerts. That future server must not be required for the functionality defined in this specification.
