# Codex Account Usage Integration — Design

Date: 2026-08-20
Status: Proposed / user-approved architecture, pending written-spec review
Scope: AgentScope local-first Codex account usage, rate-limit and thread-usage integration

## 1. Goal

Add an optional, read-only Codex account usage integration that complements AgentScope's local rollout telemetry with account-level quota/credit information and authoritative thread-level usage returned by the Codex app-server.

The feature must answer, when evidence is available:

- Which ChatGPT/Codex plan is active.
- Current Codex quota/rate-limit usage and reset times.
- Whether additional credits exist and the currently reported credit balance.
- Thread-level estimated usage credits and optional estimated USD usage.
- The real model(s) reported by the Codex backend for a thread, including Code Review threads.
- Whether a usage item appears to have consumed included plan capacity, additional credits, both, or cannot be determined.

It must never present an inference as observed billing fact.

## 2. Non-goals

This increment does not:

- Read, copy, export or persist ChatGPT/Codex access tokens, refresh tokens, cookies, API keys or `auth.json` contents.
- Call undocumented ChatGPT HTTP endpoints directly.
- Consume rate-limit reset credits or perform any write operation against the Codex account.
- Treat API-equivalent cost as real spend.
- Rewrite source-reported rollout telemetry.
- Guarantee plan-vs-credit attribution for historical activity when account evidence is insufficient.
- Add Team/shared-server functionality.

## 3. Authoritative integration surface

AgentScope will integrate through the official `codex app-server` process over stdio JSON-RPC.

The Codex app-server exposes account methods used by rich Codex clients, including:

- `account/read`
- `account/rateLimits/read`
- `account/usage/read`

`account/rateLimits/read` exposes ChatGPT/Codex rate-limit snapshots, plan type, credit information, reset information and spend-control state when the backend provides them.

`account/usage/read` exposes account token-activity summaries and, when called with a valid `threadId`, can expose authoritative thread usage including estimated credits, optional estimated USD and breakdown groups by model/reasoning/speed.

AgentScope will not call `/backend-api/wham/*` or `/api/codex/*` itself. Authentication remains owned by the Codex process.

## 4. Architecture

```text
.codex/sessions/*.jsonl
        |
        | local rollout telemetry
        v
AgentScope local DB <-----------------------------+
        ^                                         |
        | sanitized account/thread snapshots      |
        |                                         |
AgentScope CodexAccountClient                     |
        |                                         |
        | stdio JSON-RPC                          |
        v                                         |
`codex app-server --stdio`                        |
        |                                         |
        +-- account/read --------------------------+
        +-- account/rateLimits/read ---------------+
        +-- account/usage/read --------------------+
```

The integration is split into four layers:

1. `CodexAppServerClient`: process lifecycle, initialize handshake and strict read-only request allow-list.
2. `CodexAccountCollector`: maps app-server responses into sanitized domain records.
3. Storage/repository: persists account and thread usage snapshots with provenance.
4. Analytics/dashboard: reconciles stored account evidence with local sessions without network calls during render/snapshot generation.

## 5. Security model

### 5.1 Authentication ownership

The Codex CLI/app-server owns authentication. AgentScope does not parse or load credential files.

The subprocess is launched without `shell=True`. AgentScope communicates only via stdin/stdout JSON-RPC.

### 5.2 Read-only method allow-list

The client permits only:

- `initialize`
- `initialized` notification
- `account/read`
- `account/rateLimits/read`
- `account/usage/read`

Any attempt to invoke login, logout, reset-credit consumption, email actions or arbitrary methods is rejected locally.

### 5.3 Data minimization

Account responses may contain account-identifying fields. The adapter drops them before persistence.

Persisted data may include:

- auth mode category
- plan type
- quota percentages and reset timestamps
- credit presence/balance/unlimited flag
- spend-control status
- thread id already correlated with local Codex telemetry
- usage counts, model, reasoning effort, speed
- estimated usage credits and optional estimated USD
- collection timestamps, source and confidence/provenance

Persisted data must not include:

- email
- access token
- refresh token
- cookie
- API key
- account JWT claims
- raw auth payload
- raw response body

Application logs must not print raw app-server responses.

## 6. Storage design

Introduce a new additive schema migration.

### 6.1 `codex_account_usage_snapshots`

One sanitized account/rate-limit observation per sync.

Fields:

- `id`
- `captured_at`
- `auth_mode`
- `plan_type`
- `limit_id`
- `limit_name`
- `primary_used_percent`
- `primary_window_duration_mins`
- `primary_resets_at`
- `secondary_used_percent`
- `secondary_window_duration_mins`
- `secondary_resets_at`
- `credits_has_credits`
- `credits_balance`
- `credits_unlimited`
- `spend_control_reached`
- `individual_limit`
- `individual_used`
- `individual_remaining_percent`
- `individual_resets_at`
- `source` = `codex_app_server`
- `status`
- `error_code` nullable, sanitized

No secret-bearing raw JSON column is allowed.

### 6.2 `codex_thread_usage_snapshots`

One authoritative thread-usage observation per thread/sync.

Fields:

- `id`
- `captured_at`
- `thread_id`
- `session_id` nullable FK to local `sessions`
- `estimated_usage_credits_micros`
- `estimated_usage_usd_micros` nullable
- `source` = `codex_app_server`
- `status`
- `billing_route_available`

### 6.3 `codex_thread_usage_groups`

Backend breakdown rows attached to a thread snapshot.

Fields:

- `id`
- `thread_usage_snapshot_id`
- `model` nullable
- `reasoning_effort` nullable
- `speed` nullable
- `estimated_usage_credits_micros`
- `net_new_input_tokens` nullable
- `cached_input_tokens` nullable
- `input_tokens` nullable
- `output_tokens` nullable
- `total_tokens` nullable

This table is the preferred evidence for the executor model of Code Review threads.

## 7. Thread correlation

The local Codex collector already persists `sessions.external_session_id`. For Codex rollouts this is expected to carry the Codex thread/session UUID when available.

Correlation algorithm:

1. Match app-server `thread_id` to the local Codex session `external_session_id` exactly.
2. Do not correlate by filename/time alone when exact id evidence is absent.
3. Persist `session_id` only on exact-id match.
4. Record unmatched thread usage without fabricating a local session link.

## 8. Code Review model resolution

`codex-auto-review` is treated as an activity/source label when authoritative backend thread usage provides actual model breakdown groups.

AgentScope must not overwrite the raw local `token_usage.model_id` value. Source telemetry remains immutable evidence.

For reporting:

- If thread usage returns one backend model, expose it as `resolved_executor_model` with `source=codex_app_server` and `confidence=explicit`.
- If multiple backend models are returned, expose all groups and do not collapse them into one model.
- If the backend returns no model, keep the executor model unknown.

For monetary calculations:

- Prefer backend `estimated_usage_usd_micros` for the thread when available and label it `Codex backend estimate`, not observed charge.
- Otherwise, API-equivalent estimates may be computed from authoritative per-group token/model evidence using AgentScope's pricing catalog.
- Do not assign GPT-5.3-Codex merely because the activity is Code Review unless the backend or another explicit source reports that model for the specific thread.

This removes the need to invent a price for the pseudo-model `codex-auto-review`.

## 9. Billing-source attribution semantics

A thread can have one of:

- `included_plan`
- `additional_credits`
- `mixed`
- `unknown`

And one confidence level:

- `explicit`
- `inferred_high`
- `inferred_low`
- `unknown`

### 9.1 Explicit

Only use `explicit` if the backend response explicitly identifies the billing source for the thread. Current design does not assume such a field exists.

### 9.2 High-confidence inference

May be used only when all conditions hold:

- A pre-thread and post-thread account snapshot bracket the thread tightly.
- No other local Codex thread/activity overlaps the interval.
- The additional-credit balance changes in a direction and magnitude consistent with thread usage.
- The quota state is consistent with additional-credit consumption.

Persist the evidence timestamps and delta, not a fabricated exact charge.

### 9.3 Low-confidence inference

Used when account snapshots change consistently but concurrent activity or missing snapshots prevent isolation.

### 9.4 Unknown

Default whenever evidence is insufficient.

Historical activity will commonly remain `unknown` unless the backend itself returns sufficient thread/account billing evidence.

## 10. Commands

Add a new CLI group:

```powershell
agentscope codex-account status --database ".\data\agentscope.db"
```

Reads stored snapshots only. No network/process invocation.

```powershell
agentscope codex-account sync --database ".\data\agentscope.db"
```

Starts Codex app-server, reads account + rate limits, persists one sanitized snapshot, then exits.

```powershell
agentscope codex-account sync `
  --database ".\data\agentscope.db" `
  --from 2026-08-10 `
  --to 2026-08-20 `
  --threads
```

Additionally queries `account/usage/read` for exact local Codex thread IDs active in the selected period.

Optional flags:

- `--timeout-seconds`
- `--codex-bin`
- `--json`

No command accepts credentials.

## 11. Network/process behavior

Account synchronization is explicit and opt-in.

- Dashboard render: no network.
- Extension snapshot generation: no network.
- `agentscope collect`: does not automatically query account usage in the first implementation.
- `codex-account sync`: performs app-server requests.

A future opt-in auto-sync may be added after the manual path is validated.

## 12. Failure handling

The integration is best-effort and must not damage existing analytics.

Failure states include:

- `codex` binary not found
- app-server unsupported by installed Codex version
- not logged in to ChatGPT
- app-server initialization failure
- account method unsupported
- thread usage unavailable on older server/backend
- timeout
- malformed response

Failures:

- never erase last-known-good snapshots
- never fabricate zeros for unavailable account values
- return sanitized diagnostics
- leave local token/cost analytics functional

## 13. Snapshot/dashboard contract

Add an optional `codex_account` section to the extension snapshot so older producers/consumers remain compatible.

Example:

```json
{
  "codex_account": {
    "available": true,
    "captured_at": "2026-08-20T16:00:00Z",
    "plan_type": "pro",
    "primary_used_percent": 63,
    "primary_resets_at": 1787241600,
    "secondary_used_percent": 42,
    "secondary_resets_at": 1787846400,
    "credits": {
      "has_credits": true,
      "balance": "18.42",
      "unlimited": false
    },
    "spend_control_reached": false
  }
}
```

Dashboard additions:

- `Codex — ChatGPT Pro`
- included-use percentage(s) and reset times when available
- additional credit balance when available
- API-equivalent cost remains a separate metric
- Code Review/thread details can show backend-estimated credits/USD and executor model evidence

Never label `estimated_usage_usd_micros` as a real charge unless a future explicit billing source supports that claim.

## 14. Test strategy

Follow TDD.

### Unit tests

- JSON-RPC client initialization framing.
- Strict read-only method allow-list.
- Response sanitization drops email/tokens/unknown secret-like fields.
- Rate-limit response mapping.
- Thread-usage response mapping.
- Exact thread-id correlation.
- Multiple-model thread groups remain multiple.
- Unknown fields remain unavailable, not zero.
- Attribution remains unknown without sufficient evidence.
- High-confidence attribution requires non-overlap + bracketing snapshots.
- Database migration is additive/idempotent.
- Snapshot contract accepts absent `codex_account` for backward compatibility.

### Integration tests

Use a fake stdio JSON-RPC app-server process/fixture. Tests must not depend on a real OpenAI account or credentials.

Validate process startup, handshake, request/response correlation, timeout and clean shutdown.

### Real local acceptance

After CI is green, run against the user's installed Codex account:

```powershell
agentscope codex-account sync --database ".\data\agentscope.db" --json
```

Then query historical review threads:

```powershell
agentscope codex-account sync `
  --database ".\data\agentscope.db" `
  --from 2026-08-10 `
  --to 2026-08-20 `
  --threads `
  --json
```

Acceptance requires confirming that no credential values are present in DB rows, CLI output or logs.

## 15. Delivery phases

### Phase A — safe account collector

- schema migration
- stdio app-server client
- `account/read`
- `account/rateLimits/read`
- sanitized snapshot storage
- `codex-account status/sync`

### Phase B — thread usage / Code Review resolution

- exact local thread selection
- `account/usage/read(threadId)`
- thread-usage storage + groups
- Code Review executor-model reporting
- backend-estimated credits/USD display

### Phase C — conservative attribution

- pre/post account snapshot reconciliation
- included-plan / additional-credits / mixed / unknown
- confidence + evidence
- dashboard presentation

## 16. Acceptance criteria

1. AgentScope can read Codex account/rate-limit data through `codex app-server` without reading credential files.
2. No secrets or account email are persisted or logged.
3. Existing local analytics continue working when account sync is unavailable.
4. Account values retain `null`/unavailable semantics when absent.
5. Historical Code Review threads are queried by exact thread id when possible.
6. Backend model groups are preserved and used as executor-model evidence without rewriting raw rollout telemetry.
7. Backend estimated credits/USD are clearly distinguished from observed billing.
8. Plan-vs-additional-credit attribution is never presented as fact unless explicit evidence exists.
9. Dashboard/network separation remains intact: rendering never triggers account requests.
10. Full Python and VS Code CI suites pass before local acceptance.
