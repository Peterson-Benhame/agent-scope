# AgentScope Team Bundle

`agentscope-team-bundle` is the offline interchange format used to consolidate safe AgentScope telemetry from multiple developer machines without copying provider history databases or conversation content.

## Schema

Current schema:

```text
schema:  agentscope-team-bundle
version: 1
```

Each bundle includes:

```text
schema
version
bundle_id
generated_at
organization
team
records
```

`bundle_id` is a SHA-256 digest of the canonical safe payload. `generated_at` and `bundle_id` themselves are excluded from the digest so the same normalized data and scope produce the same identifier.

## Export

```powershell
agentscope team export `
  --database .\data\agentscope.db `
  --output .\team-bundle.json `
  --organization "Minha Empresa" `
  --team "Backend"
```

The export supports the shared analytics filters:

```text
--from
--to
--period
--project
--model
--source
--user
--machine
```

Dates are inclusive and use `YYYY-MM-DD`. Custom `--from`/`--to` values override `--period`.

## Import

```powershell
agentscope team import .\team-bundle.json --database .\data\team.db
```

Import validates schema, version, required record groups, stable identifiers, numeric metric types, forbidden fields and the canonical `bundle_id` before writing data.

The import is transactional. A validation or write failure does not leave a partial bundle applied.

## Allowed telemetry

The bundle is produced from explicit allow lists. Depending on what the source actually exposes, safe records can contain:

- stable user key, display label and identity confidence;
- stable machine key, display label and operating-system label;
- namespaced session key and external session identifier;
- source/provider/model names;
- normalized project name;
- session timestamps;
- token, cache and context-window metrics;
- observed/source-reported and estimated monetary fields already normalized by AgentScope;
- tool name/category/provider, status, duration and input/output sizes;
- agent/subagent evidence metadata;
- optimizer, compression, cache-savings and correlation-confidence metrics.

A metric that is not supplied by a source remains unavailable/`NULL`; the bundle does not convert missing data into zero.

## Forbidden data

Team bundles must not contain:

- prompt or user-message bodies;
- assistant response bodies;
- source code;
- tool arguments, payloads or outputs;
- attachments;
- environment variables;
- secrets or credentials;
- raw provider metadata blobs;
- raw source-file paths;
- the local full project path.

The normalized project name may be exported, but the source path is deliberately excluded.

## Identity and collision safety

Display names are not identity keys. User and machine records use stable keys generated during local collection.

Session keys are namespaced using source, user, machine and external-session identity. Event keys are then namespaced by event type and session/scope. This prevents two developers with the same local provider session/event identifiers from colliding during team consolidation.

## Idempotency

Two layers prevent duplicate totals:

1. importing an already-recorded `bundle_id` skips the bundle;
2. importing a newer overlapping bundle relies on stable namespaced event keys and normalized-table uniqueness to skip events already present while accepting new events.

Provenance is stored in:

```text
team_bundles
team_event_provenance
```

This permits repeated offline delivery without inflating sessions, tokens or monetary totals.

## Recommended team workflow

```text
Developer machine A              Developer machine B
agentscope collect               agentscope collect
      ↓                                ↓
local agentscope.db              local agentscope.db
      ↓                                ↓
team export                      team export
      └──────── safe bundles ──────────┘
                    ↓
             team consolidation DB
                    ↓
               team analytics
```

The local database remains the richer/private source. The team database receives only the sanitized bundle representation.

## Security boundary

The Team Bundle reduces the amount of sensitive material transferred, but it still contains operational metadata such as developer labels, project names, model usage, token counts and costs. Treat the bundle and consolidated team database as internal telemetry.
