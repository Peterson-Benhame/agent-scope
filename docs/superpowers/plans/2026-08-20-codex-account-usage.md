# Codex Account Usage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a safe, read-only Codex account integration that collects plan/rate-limit/credit snapshots and authoritative per-thread usage through `codex app-server`, then correlates that evidence with local AgentScope sessions and presents it without confusing estimates with observed billing.

**Architecture:** A focused `agentscope.codex_account` package owns the stdio JSON-RPC client, sanitized domain mapping, persistence, thread correlation and conservative attribution. The CLI explicitly triggers synchronization; dashboard/snapshot paths read only from SQLite and never start network/process activity. Raw rollout telemetry remains immutable; backend thread usage is stored as separate authoritative evidence.

**Tech Stack:** Python 3.11+, stdlib `subprocess`/`threading`/`queue`, Typer, SQLite, pytest, TypeScript, VS Code webview, Codex app-server JSON-RPC.

**Spec:** `docs/superpowers/specs/2026-08-20-codex-account-usage-design.md`

## Global Constraints

- Integration is read-only and opt-in; dashboard render and extension snapshot generation must never invoke Codex app-server.
- Never read, copy, export, persist or log `auth.json`, access tokens, refresh tokens, cookies, API keys, email addresses or raw account-response bodies.
- Spawn `codex app-server --stdio` without `shell=True`; authentication remains owned by Codex.
- Allow only `initialize`, `initialized`, `account/read`, `account/rateLimits/read`, and `account/usage/read`.
- Unknown account values remain `NULL`/unavailable; never convert unavailable values to zero.
- `codex-auto-review` remains raw local telemetry; do not rewrite `token_usage.model_id`.
- Resolve Code Review executor models only from explicit backend thread-usage groups or another explicit source for that thread.
- Backend estimated credits/USD are estimates, not observed charges.
- Billing-source attribution defaults to `unknown`; inference must carry explicit confidence and evidence.
- Team/shared-server functionality remains out of scope.
- Follow TDD: failing test first, verify RED, minimal implementation, verify GREEN, then refactor.

---

## File Structure

Create a focused package rather than adding account-process logic to existing collectors:

```text
src/agentscope/codex_account/
    __init__.py              package exports
    models.py                sanitized dataclasses/enums only
    app_server.py            process lifecycle + JSON-RPC read-only client
    storage.py               focused persistence/read queries
    collector.py             account/rate-limit + thread usage orchestration
    attribution.py           conservative plan-vs-credit reconciliation

src/agentscope/storage/database.py
    schema migration V6 only

src/agentscope/cli.py
    `codex-account status|sync` commands only

src/agentscope/extension/snapshot.py
    optional stored `codex_account` projection; no process/network calls

vscode-extension/src/contracts/snapshot.ts
    optional account contract
vscode-extension/src/views/dashboardViewModel.ts
    presentation mapping
vscode-extension/media/dashboard.js
    account card/detail rendering
```

Tests:

```text
tests/fixtures/codex_app_server/fake_app_server.py
tests/unit/test_codex_account_storage.py
tests/unit/test_codex_app_server_client.py
tests/unit/test_codex_account_collector.py
tests/unit/test_codex_thread_usage.py
tests/unit/test_codex_account_attribution.py
tests/unit/test_codex_account_cli.py
tests/unit/test_codex_account_snapshot.py
vscode-extension/src/test/unit/snapshot.test.ts
vscode-extension/src/test/unit/dashboardViewModel.test.ts
```

---

### Task 1: Sanitized Domain Types and Additive SQLite Schema

**Files:**
- Create: `src/agentscope/codex_account/__init__.py`
- Create: `src/agentscope/codex_account/models.py`
- Modify: `src/agentscope/storage/database.py` after the existing V5 migration
- Create: `tests/unit/test_codex_account_storage.py`

**Interfaces:**
- Produces: `CodexAccountSnapshot`, `CodexThreadUsageSnapshot`, `CodexThreadUsageGroup`, `BillingSource`, `AttributionConfidence`.
- Produces tables: `codex_account_usage_snapshots`, `codex_thread_usage_snapshots`, `codex_thread_usage_groups`.
- Later tasks consume these exact field names; do not add a raw-response JSON column.

- [ ] **Step 1: Write the failing migration/domain test**

```python
from agentscope.codex_account.models import BillingSource, AttributionConfidence
from agentscope.storage.database import Database


def test_codex_account_schema_is_additive_and_secret_free(tmp_path):
    db = Database(tmp_path / "agentscope.db")
    db.initialize()
    with db.connect() as conn:
        versions = {row[0] for row in conn.execute("SELECT version FROM schema_migrations")}
        assert 6 in versions
        account_cols = {row[1] for row in conn.execute("PRAGMA table_info(codex_account_usage_snapshots)")}
        thread_cols = {row[1] for row in conn.execute("PRAGMA table_info(codex_thread_usage_snapshots)")}
        group_cols = {row[1] for row in conn.execute("PRAGMA table_info(codex_thread_usage_groups)")}

    assert {"captured_at", "plan_type", "credits_balance", "primary_used_percent"} <= account_cols
    assert {"thread_id", "session_id", "estimated_usage_credits_micros", "estimated_usage_usd_micros"} <= thread_cols
    assert {"model", "cached_input_tokens", "output_tokens", "total_tokens"} <= group_cols
    forbidden = {"access_token", "refresh_token", "cookie", "api_key", "email", "raw_json", "raw_response"}
    assert not forbidden.intersection(account_cols | thread_cols | group_cols)
    assert BillingSource.UNKNOWN.value == "unknown"
    assert AttributionConfidence.INFERRED_HIGH.value == "inferred_high"
```

- [ ] **Step 2: Run the test and verify RED**

Run:

```bash
python -m pytest tests/unit/test_codex_account_storage.py -q
```

Expected: import failure for `agentscope.codex_account.models` or missing migration/table assertions.

- [ ] **Step 3: Add sanitized domain types**

Implement in `src/agentscope/codex_account/models.py`:

```python
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class BillingSource(str, Enum):
    INCLUDED_PLAN = "included_plan"
    ADDITIONAL_CREDITS = "additional_credits"
    MIXED = "mixed"
    UNKNOWN = "unknown"


class AttributionConfidence(str, Enum):
    EXPLICIT = "explicit"
    INFERRED_HIGH = "inferred_high"
    INFERRED_LOW = "inferred_low"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class CodexAccountSnapshot:
    captured_at: str
    auth_mode: str | None = None
    plan_type: str | None = None
    limit_id: str | None = None
    limit_name: str | None = None
    primary_used_percent: int | None = None
    primary_window_duration_mins: int | None = None
    primary_resets_at: int | None = None
    secondary_used_percent: int | None = None
    secondary_window_duration_mins: int | None = None
    secondary_resets_at: int | None = None
    credits_has_credits: bool | None = None
    credits_balance: str | None = None
    credits_unlimited: bool | None = None
    spend_control_reached: bool | None = None
    individual_limit: str | None = None
    individual_used: str | None = None
    individual_remaining_percent: int | None = None
    individual_resets_at: int | None = None
    source: str = "codex_app_server"
    status: str = "complete"
    error_code: str | None = None


@dataclass(frozen=True, slots=True)
class CodexThreadUsageGroup:
    model: str | None
    reasoning_effort: str | None
    speed: str | None
    estimated_usage_credits_micros: int
    net_new_input_tokens: int | None = None
    cached_input_tokens: int | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None


@dataclass(frozen=True, slots=True)
class CodexThreadUsageSnapshot:
    captured_at: str
    thread_id: str
    session_id: int | None
    estimated_usage_credits_micros: int | None
    estimated_usage_usd_micros: int | None
    source: str = "codex_app_server"
    status: str = "complete"
    billing_route_available: bool = True
    billing_source: BillingSource = BillingSource.UNKNOWN
    attribution_confidence: AttributionConfidence = AttributionConfidence.UNKNOWN
    evidence_json: str = "{}"
    groups: tuple[CodexThreadUsageGroup, ...] = field(default_factory=tuple)
```

Export these from `src/agentscope/codex_account/__init__.py`.

- [ ] **Step 4: Add schema V6 and migration**

Add `SCHEMA_V6` to `src/agentscope/storage/database.py` with the three tables specified in the design. Use `INTEGER` for booleans, `TEXT` for decimal-like backend strings, foreign keys to `sessions(id)` and thread snapshot rows, and indexes on `captured_at`, `thread_id`, and `session_id`.

Add:

```python
def _migrate_v6(self, conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA_V6)
    conn.execute(
        "INSERT OR IGNORE INTO schema_migrations(version, description) VALUES(6, ?)",
        ("Add sanitized Codex account and thread usage snapshots",),
    )
```

Call `_migrate_v6(conn)` after `_migrate_v5(conn)` in `initialize()`.

- [ ] **Step 5: Run migration tests GREEN and full storage regressions**

```bash
python -m pytest tests/unit/test_codex_account_storage.py tests/unit/test_storage.py tests/unit/test_identity_migration.py -q
```

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add src/agentscope/codex_account src/agentscope/storage/database.py tests/unit/test_codex_account_storage.py
git commit -m "feat: add Codex account usage storage"
```

---

### Task 2: Cross-Platform Read-Only Codex App-Server Client

**Files:**
- Create: `src/agentscope/codex_account/app_server.py`
- Create: `tests/fixtures/codex_app_server/fake_app_server.py`
- Create: `tests/unit/test_codex_app_server_client.py`

**Interfaces:**
- Produces: `CodexAppServerClient(codex_bin: str = "codex", timeout_seconds: float = 10.0)`.
- Produces methods: `start()`, `close()`, context-manager methods, `account_read()`, `account_rate_limits_read()`, `account_usage_read(thread_id: str | None = None)`.
- No public arbitrary `request(method, ...)` API; the generic request helper remains private.

- [ ] **Step 1: Write failing tests for handshake, allow-list and timeout**

Tests must launch the Python fake fixture as the executable command via constructor support for `command: list[str] | None` used only by tests.

```python
def test_client_initializes_and_reads_only_allowed_account_methods(fake_command):
    with CodexAppServerClient(command=fake_command, timeout_seconds=1.0) as client:
        account = client.account_read()
        limits = client.account_rate_limits_read()
        usage = client.account_usage_read("01a016bf-d4e0-7383-9c3d-872eeeb5c5fa")

    assert account["account"]["type"] == "chatgpt"
    assert account["account"]["planType"] == "pro"
    assert limits["rateLimits"]["credits"]["balance"] == "18.42"
    assert usage["threadUsage"]["threadId"].startswith("01a016bf")


def test_client_rejects_write_method_before_it_reaches_subprocess(fake_command):
    with CodexAppServerClient(command=fake_command, timeout_seconds=1.0) as client:
        with pytest.raises(CodexAppServerError, match="method_not_allowed"):
            client._request("account/logout", {})


def test_client_times_out_with_sanitized_error(fake_hanging_command):
    with pytest.raises(CodexAppServerError) as exc:
        with CodexAppServerClient(command=fake_hanging_command, timeout_seconds=0.05) as client:
            client.account_read()
    assert exc.value.code == "timeout"
    assert "access_token" not in str(exc.value).lower()
```

- [ ] **Step 2: Run and verify RED**

```bash
python -m pytest tests/unit/test_codex_app_server_client.py -q
```

Expected: missing client module/classes.

- [ ] **Step 3: Implement the fake app-server fixture**

`tests/fixtures/codex_app_server/fake_app_server.py` must:

- read one JSON object per stdin line;
- return an `initialize` result;
- accept `initialized` notification without response;
- return deterministic results for the three account methods;
- include deliberately sensitive fields such as `email` only in the fake `account/read` payload so later sanitization tests can prove they are dropped;
- support environment variable `FAKE_CODEX_HANG=1` to suppress responses for timeout testing.

- [ ] **Step 4: Implement the client with a reader thread + queue**

Use stdlib only. Launch:

```python
subprocess.Popen(
    self.command or [self.codex_bin, "app-server", "--stdio"],
    stdin=subprocess.PIPE,
    stdout=subprocess.PIPE,
    stderr=subprocess.DEVNULL,
    text=True,
    encoding="utf-8",
    bufsize=1,
    shell=False,
)
```

A daemon reader thread parses stdout JSONL and pushes dict messages to `queue.Queue`. `_request()` writes a monotonically increasing integer `id`, then waits until the matching response id arrives; unrelated notifications are ignored. `queue.get(timeout=self.timeout_seconds)` enforces Windows-compatible timeout behavior.

Define:

```python
_ALLOWED_REQUESTS = {
    "initialize",
    "account/read",
    "account/rateLimits/read",
    "account/usage/read",
}
_ALLOWED_NOTIFICATIONS = {"initialized"}
```

Initialization sequence:

```python
self._request("initialize", {
    "clientInfo": {
        "name": "agentscope",
        "title": "AgentScope",
        "version": "0.1.0",
    }
})
self._notify("initialized", {})
```

Account methods:

```python
def account_read(self) -> dict[str, object]:
    return self._request("account/read", {"refreshToken": False})


def account_rate_limits_read(self) -> dict[str, object]:
    return self._request("account/rateLimits/read", None)


def account_usage_read(self, thread_id: str | None = None) -> dict[str, object]:
    params = {"threadId": thread_id} if thread_id else {}
    return self._request("account/usage/read", params)
```

`CodexAppServerError` contains only `code` and a sanitized fixed message; never include the raw response/body.

- [ ] **Step 5: Verify GREEN**

```bash
python -m pytest tests/unit/test_codex_app_server_client.py -q
```

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add src/agentscope/codex_account/app_server.py tests/fixtures/codex_app_server tests/unit/test_codex_app_server_client.py
git commit -m "feat: add read-only Codex app-server client"
```

---

### Task 3: Sanitized Account Mapping and Persistence

**Files:**
- Create: `src/agentscope/codex_account/storage.py`
- Create: `src/agentscope/codex_account/collector.py`
- Create: `tests/unit/test_codex_account_collector.py`

**Interfaces:**
- Produces: `CodexAccountStorage(database: Database)` with `insert_account_snapshot()`, `latest_account_snapshot()`, `insert_thread_usage_snapshot()`, `latest_thread_usage()`.
- Produces: `sync_account_usage(repository: Repository, *, client: CodexAppServerClient | None = None, codex_bin: str = "codex", timeout_seconds: float = 10.0) -> CodexAccountSyncResult`.
- `CodexAccountSyncResult` fields: `status`, `account_snapshot_id`, `plan_type`, `credits_balance`, `error_code`.

- [ ] **Step 1: Write the failing sanitizer/persistence tests**

```python
def test_sync_maps_only_allowlisted_account_fields_and_drops_identity(tmp_path, fake_client):
    repo = make_repo(tmp_path)
    result = sync_account_usage(repo, client=fake_client)
    assert result.status == "complete"

    with repo.database.connect() as conn:
        row = conn.execute(
            "SELECT * FROM codex_account_usage_snapshots ORDER BY id DESC LIMIT 1"
        ).fetchone()
        serialized = " ".join("" if value is None else str(value) for value in row)

    assert row["plan_type"] == "pro"
    assert row["credits_balance"] == "18.42"
    assert row["primary_used_percent"] == 63
    assert "person@example.com" not in serialized
    assert "access_token" not in serialized.lower()
```

Also test missing `credits`, missing windows and malformed optional values stay `None`, not `0`.

- [ ] **Step 2: Run RED**

```bash
python -m pytest tests/unit/test_codex_account_collector.py -q
```

Expected: missing storage/collector APIs.

- [ ] **Step 3: Implement focused storage**

`CodexAccountStorage` writes explicit columns only. Do not serialize input dicts. `latest_account_snapshot()` reconstructs a `CodexAccountSnapshot` from the newest successful row.

- [ ] **Step 4: Implement strict mapping functions**

In `collector.py`, use helpers that accept `dict[str, object]` and explicitly read only documented fields:

```python
def _map_account_and_limits(
    account_result: dict[str, object],
    limits_result: dict[str, object],
    captured_at: str,
) -> CodexAccountSnapshot:
    account = account_result.get("account")
    account_obj = account if isinstance(account, dict) else {}
    rate_limits = limits_result.get("rateLimits")
    limits = rate_limits if isinstance(rate_limits, dict) else {}
    primary = limits.get("primary") if isinstance(limits.get("primary"), dict) else {}
    secondary = limits.get("secondary") if isinstance(limits.get("secondary"), dict) else {}
    credits = limits.get("credits") if isinstance(limits.get("credits"), dict) else {}
    individual = limits.get("individualLimit") if isinstance(limits.get("individualLimit"), dict) else {}
    return CodexAccountSnapshot(
        captured_at=captured_at,
        auth_mode=_string_or_none(account_obj.get("type")),
        plan_type=_string_or_none(account_obj.get("planType") or limits.get("planType")),
        limit_id=_string_or_none(limits.get("limitId")),
        limit_name=_string_or_none(limits.get("limitName")),
        primary_used_percent=_int_or_none(primary.get("usedPercent")),
        primary_window_duration_mins=_int_or_none(primary.get("windowDurationMins")),
        primary_resets_at=_int_or_none(primary.get("resetsAt")),
        secondary_used_percent=_int_or_none(secondary.get("usedPercent")),
        secondary_window_duration_mins=_int_or_none(secondary.get("windowDurationMins")),
        secondary_resets_at=_int_or_none(secondary.get("resetsAt")),
        credits_has_credits=_bool_or_none(credits.get("hasCredits")),
        credits_balance=_string_or_none(credits.get("balance")),
        credits_unlimited=_bool_or_none(credits.get("unlimited")),
        spend_control_reached=_bool_or_none(limits.get("spendControlReached")),
        individual_limit=_string_or_none(individual.get("limit")),
        individual_used=_string_or_none(individual.get("used")),
        individual_remaining_percent=_int_or_none(individual.get("remainingPercent")),
        individual_resets_at=_int_or_none(individual.get("resetsAt")),
    )
```

Do not copy `email` or unknown keys.

- [ ] **Step 5: Implement sync orchestration and non-destructive failure**

On success, persist one snapshot. On app-server failure, return `status="failed"` and sanitized `error_code`; do not insert fabricated account values and do not delete previous rows.

- [ ] **Step 6: Verify GREEN**

```bash
python -m pytest tests/unit/test_codex_account_collector.py tests/unit/test_codex_account_storage.py -q
```

- [ ] **Step 7: Commit**

```bash
git add src/agentscope/codex_account/storage.py src/agentscope/codex_account/collector.py tests/unit/test_codex_account_collector.py
git commit -m "feat: persist sanitized Codex account snapshots"
```

---

### Task 4: `codex-account status` and `sync` CLI — Phase A Deliverable

**Files:**
- Modify: `src/agentscope/cli.py` near existing Typer sub-app declarations and command groups
- Create: `tests/unit/test_codex_account_cli.py`

**Interfaces:**
- Produces commands:
  - `agentscope codex-account status --database PATH [--json]`
  - `agentscope codex-account sync --database PATH [--codex-bin PATH] [--timeout-seconds N] [--json]`
- `status` reads SQLite only.

- [ ] **Step 1: Write failing CLI tests with Typer `CliRunner`**

Assert `status` on an empty DB returns an unavailable payload without spawning a subprocess. Assert `sync` with fake command support at the Python-function level returns sanitized JSON containing plan/credit fields but not email or credentials.

- [ ] **Step 2: Run RED**

```bash
python -m pytest tests/unit/test_codex_account_cli.py -q
```

- [ ] **Step 3: Register the Typer group and commands**

Add:

```python
codex_account_app = typer.Typer(help="Read-only ChatGPT/Codex account usage snapshots.")
app.add_typer(codex_account_app, name="codex-account")
```

`status` reads `CodexAccountStorage.latest_account_snapshot()` and prints either JSON or concise key/value text.

`sync` creates the app-server client only inside the command execution, invokes `sync_account_usage`, prints sanitized result, exits non-zero only when the sync itself fails.

- [ ] **Step 4: Verify targeted and CLI regression tests**

```bash
python -m pytest tests/unit/test_codex_account_cli.py tests/unit/test_cli.py -q
```

If `tests/unit/test_cli.py` does not exist on the execution branch, run `python -m pytest tests/unit -q` instead; do not create a placeholder test file.

- [ ] **Step 5: Commit**

```bash
git add src/agentscope/cli.py tests/unit/test_codex_account_cli.py
git commit -m "feat: add Codex account sync commands"
```

**Checkpoint:** Phase A is independently useful. Before Phase B, verify the fake app-server integration is green and no persisted columns contain account identity/secrets.

---

### Task 5: Exact Thread Correlation and Authoritative Thread Usage — Phase B

**Files:**
- Modify: `src/agentscope/codex_account/collector.py`
- Modify: `src/agentscope/codex_account/storage.py`
- Modify: `src/agentscope/cli.py`
- Create: `tests/unit/test_codex_thread_usage.py`

**Interfaces:**
- Produces: `select_local_codex_threads(repository, from_date, to_date, utc_offset_minutes) -> list[LocalCodexThread]`.
- `LocalCodexThread(thread_id: str, session_id: int, started_at: str | None)` uses exact `sessions.external_session_id` only.
- Produces: `sync_thread_usage(..., thread_ids: Sequence[LocalCodexThread]) -> ThreadSyncSummary`.

- [ ] **Step 1: Write failing exact-correlation tests**

Create sessions where one exact UUID matches the backend thread, one filename/time is similar but UUID differs, and one non-Codex source has the same external id. Assert only the exact Codex session is linked.

- [ ] **Step 2: Write failing thread-mapping tests**

Fixture response must include:

```json
{
  "threadUsage": {
    "threadId": "01a016bf-d4e0-7383-9c3d-872eeeb5c5fa",
    "estimatedUsageCreditsMicros": 1250000,
    "estimatedUsageUsdMicros": 490000,
    "groups": [
      {
        "model": "gpt-5.3-codex",
        "reasoningEffort": "high",
        "speed": "standard",
        "estimatedUsageCreditsMicros": 1250000,
        "netNewInputTokens": 2700,
        "cachedInputTokens": 19200,
        "inputTokens": 21900,
        "outputTokens": 90,
        "totalTokens": 21990
      }
    ]
  }
}
```

Assert model, tokens, credits and USD are persisted exactly; `token_usage.model_id` remains unchanged.

Also test two model groups stay two rows.

- [ ] **Step 3: Run RED**

```bash
python -m pytest tests/unit/test_codex_thread_usage.py -q
```

- [ ] **Step 4: Implement exact local-thread selection**

Query only source `codex`, use the same local-date expression convention as dashboard analytics, require non-empty `external_session_id`, and return exact ids. Do not infer from `raw_file_path`.

- [ ] **Step 5: Implement authoritative thread usage mapping**

Call `client.account_usage_read(thread.thread_id)`. If `threadUsage` is `null` or absent, persist a thread snapshot with `billing_route_available=False`, no fake credits/USD and no groups. If present, map only allowlisted fields into `CodexThreadUsageSnapshot` and `CodexThreadUsageGroup`.

- [ ] **Step 6: Extend CLI sync flags**

Add:

```text
--threads
--from YYYY-MM-DD
--to YYYY-MM-DD
```

`--threads` uses the selected date range and exact local Codex thread IDs after the account snapshot sync. Reuse existing `_parse_date` / `resolve_period` semantics where applicable.

- [ ] **Step 7: Verify GREEN**

```bash
python -m pytest tests/unit/test_codex_thread_usage.py tests/unit/test_codex_account_cli.py -q
```

- [ ] **Step 8: Commit**

```bash
git add src/agentscope/codex_account src/agentscope/cli.py tests/unit/test_codex_thread_usage.py tests/unit/test_codex_account_cli.py
git commit -m "feat: collect authoritative Codex thread usage"
```

---

### Task 6: Conservative Plan-vs-Credit Attribution — Phase C

**Files:**
- Create: `src/agentscope/codex_account/attribution.py`
- Modify: `src/agentscope/codex_account/storage.py`
- Create: `tests/unit/test_codex_account_attribution.py`

**Interfaces:**
- Produces: `attribute_thread_billing(repository: Repository, thread_snapshot_id: int) -> BillingAttribution`.
- `BillingAttribution` fields: `billing_source`, `confidence`, `credit_balance_delta`, `pre_snapshot_id`, `post_snapshot_id`, `overlapping_session_count`.
- Updates only attribution columns/evidence on the thread snapshot; never changes backend usage totals.

- [ ] **Step 1: Write four failing classification tests**

Cover:

1. no bracketing snapshots -> `unknown/unknown`;
2. tight pre/post snapshots, no overlapping local activity, credit balance decreases consistently -> `additional_credits/inferred_high`;
3. credit change with overlapping activity -> `unknown/inferred_low` rather than assigning the full delta to the thread;
4. no credit balance change while plan window usage rises -> `included_plan/inferred_low` only, not explicit.

- [ ] **Step 2: Run RED**

```bash
python -m pytest tests/unit/test_codex_account_attribution.py -q
```

- [ ] **Step 3: Implement evidence-first reconciliation**

Use `Decimal` for credit-balance differences. Bracketing snapshots must be before thread start and after thread end/last usage timestamp; if no end timestamp exists, use the thread usage snapshot capture time only for low-confidence inference.

Count overlapping local Codex sessions in the bracket. High-confidence additional-credit attribution requires exactly the target session and a positive pre-minus-post credit delta. Never convert the delta into an observed per-thread charge.

Serialize evidence as a small allowlisted JSON object containing only snapshot ids/timestamps, balance delta string and overlap count.

- [ ] **Step 4: Verify GREEN**

```bash
python -m pytest tests/unit/test_codex_account_attribution.py -q
```

- [ ] **Step 5: Commit**

```bash
git add src/agentscope/codex_account/attribution.py src/agentscope/codex_account/storage.py tests/unit/test_codex_account_attribution.py
git commit -m "feat: infer Codex billing source conservatively"
```

---

### Task 7: Stored Account Snapshot and Review Evidence in VS Code Dashboard

**Files:**
- Modify: `src/agentscope/extension/contracts.py`
- Modify: `src/agentscope/extension/snapshot.py`
- Create: `tests/unit/test_codex_account_snapshot.py`
- Modify: `vscode-extension/src/contracts/snapshot.ts`
- Modify: `vscode-extension/src/test/unit/snapshot.test.ts`
- Modify: `vscode-extension/src/views/dashboardViewModel.ts`
- Modify: `vscode-extension/src/test/unit/dashboardViewModel.test.ts`
- Modify: `vscode-extension/media/dashboard.js`
- Modify: `vscode-extension/media/dashboard.css` only if existing card layout needs account-specific detail styling

**Interfaces:**
- Adds optional `codex_account` to snapshot v2 without incrementing schema version.
- No account table/data -> field absent or `available:false`; old fixtures remain valid.
- Dashboard keeps `Custo equivalente via API` separate from account/credit status.

- [ ] **Step 1: Write Python snapshot RED tests**

Assert snapshot generation does not instantiate `CodexAppServerClient`; it only reads the latest stored successful account snapshot. Expected projection:

```python
assert snapshot["codex_account"] == {
    "available": True,
    "captured_at": "2026-08-20T16:00:00+00:00",
    "plan_type": "pro",
    "primary_used_percent": 63,
    "primary_resets_at": 1787241600,
    "secondary_used_percent": 42,
    "secondary_resets_at": 1787846400,
    "credits": {
        "has_credits": True,
        "balance": "18.42",
        "unlimited": False,
    },
    "spend_control_reached": False,
}
```

- [ ] **Step 2: Run Python RED**

```bash
python -m pytest tests/unit/test_codex_account_snapshot.py -q
```

- [ ] **Step 3: Add snapshot projection**

Create a frozen `SnapshotCodexAccount`/nested credit dataclass or a focused dict builder. Read from `CodexAccountStorage.latest_account_snapshot()` only. Preserve absent values as `None`.

- [ ] **Step 4: Write TypeScript RED tests**

Update the unit fixture with an optional account section and assert:

```typescript
assert.strictEqual(vm.codexAccount?.title, 'Codex — ChatGPT Pro');
assert.strictEqual(vm.codexAccount?.primaryUsageLabel, '63,00%');
assert.strictEqual(vm.codexAccount?.creditBalanceLabel, '18,42 créditos');
```

Also assert a snapshot without `codex_account` still parses.

- [ ] **Step 5: Run TypeScript RED**

```bash
cd vscode-extension
npm run compile
```

Expected: missing `codex_account` contract/viewmodel fields.

- [ ] **Step 6: Implement TypeScript contract/viewmodel and dashboard rendering**

Add optional interfaces with nullable fields and strict validation when present. Render an account card/section only when available. Use copy that distinguishes:

```text
Codex — ChatGPT Pro
Uso incluído: 63,00%
Saldo de créditos: 18,42 créditos
```

Do not call the credit balance “gasto”, and do not merge it into the API-equivalent cost card.

For review/thread details, display backend `estimated_usage_usd_micros / 1_000_000` as `Estimativa do backend Codex`, never `Custo observado`.

- [ ] **Step 7: Verify GREEN**

```bash
python -m pytest tests/unit/test_codex_account_snapshot.py -q
cd vscode-extension
npm run compile
npm test
```

- [ ] **Step 8: Commit**

```bash
git add src/agentscope/extension tests/unit/test_codex_account_snapshot.py vscode-extension
git commit -m "feat: show stored Codex account usage in dashboard"
```

---

### Task 8: Full Verification, Security Audit and Real Windows Acceptance

**Files:**
- Modify only if verification exposes a defect; any defect requires a new failing regression test before the fix.
- Update: `README.md` with command usage after behavior is proven.

**Interfaces:**
- Final deliverable commands are stable and documented.

- [ ] **Step 1: Add README command examples and semantics**

Document:

```powershell
agentscope codex-account status --database ".\data\agentscope.db" --json
agentscope codex-account sync --database ".\data\agentscope.db" --json
agentscope codex-account sync `
  --database ".\data\agentscope.db" `
  --from 2026-08-10 `
  --to 2026-08-20 `
  --threads `
  --json
```

State that the feature reuses Codex-managed authentication, stores no credentials, and treats backend USD/credit values as estimates unless explicitly documented otherwise.

- [ ] **Step 2: Run fatal lint + full Python tests**

```bash
flake8 . --count --select=E9,F63,F7,F82 --show-source --statistics
python -m pytest -q
```

Expected: fatal lint count `0`; pytest `0 failed`.

- [ ] **Step 3: Run full VS Code verification**

```bash
cd vscode-extension
npm run compile
npm test
```

Then run the repository's extension-host integration test command exactly as defined in `vscode-extension/package.json` / CI workflow. Expected: all pass.

- [ ] **Step 4: Audit persistence for secret-bearing columns/values**

Run a test/diagnostic that inspects all three new tables and serializes all values; assert none contain case-insensitive markers:

```text
access_token
refresh_token
bearer 
cookie
api_key
@email-like-value-from-fixture
```

The audit must use fixture sentinel secrets so it proves sanitization rather than assuming it.

- [ ] **Step 5: Real local Phase A acceptance on Windows**

```powershell
git pull
python -m pip install -e ".[dev]"
agentscope codex-account sync --database ".\data\agentscope.db" --json
agentscope codex-account status --database ".\data\agentscope.db" --json
```

Expected: sanitized plan/rate-limit/credit fields or a sanitized unsupported/not-logged-in error; existing AgentScope analytics remain usable in either case.

- [ ] **Step 6: Real local historical thread acceptance**

```powershell
agentscope codex-account sync `
  --database ".\data\agentscope.db" `
  --from 2026-08-10 `
  --to 2026-08-20 `
  --threads `
  --json
```

Inspect the known review thread `01a016bf-d4e0-7383-9c3d-872eeeb5c5fa`. If the backend returns thread usage, verify executor model group(s), credits and optional USD are persisted without changing raw `codex-auto-review` token rows. If the backend returns no billing route/history, report unavailable rather than substituting GPT-5.3-Codex by assumption.

- [ ] **Step 7: Re-run full verification after any acceptance fix**

Any real-account defect found in Steps 5–6 gets a regression test first, then the full Python and VS Code verification is rerun.

- [ ] **Step 8: Commit documentation/final acceptance adjustments**

```bash
git add README.md
git commit -m "docs: document Codex account usage integration"
```

---

## Self-Review

### Spec coverage

- Read-only app-server integration: Tasks 2–5.
- No credential-file/token persistence: Tasks 1–3 and Task 8 audit.
- Account/rate-limit snapshots: Tasks 1, 3, 4.
- Historical exact thread correlation: Task 5.
- Real Code Review model evidence without rewriting local telemetry: Task 5.
- Backend estimated credits/USD distinction: Tasks 5 and 7.
- Conservative plan-vs-credit attribution with confidence: Task 6.
- Dashboard has no network side effects: Task 7 Python test and architecture boundary.
- Failure/last-known-good semantics: Tasks 3–4.
- Backward-compatible optional snapshot section: Task 7.
- Full CI/security/local validation: Task 8.

### Placeholder scan

No `TBD`, `TODO`, “implement later”, unspecified error-handling steps, or “similar to previous task” instructions are present. Optional behavior is described with explicit semantics.

### Type consistency

- `CodexAccountSnapshot`, `CodexThreadUsageSnapshot`, `CodexThreadUsageGroup`, `BillingSource`, and `AttributionConfidence` originate in Task 1 and are consumed with the same names thereafter.
- `CodexAppServerClient` originates in Task 2 and is used by Tasks 3–5.
- `CodexAccountStorage` originates in Task 3 and is reused by CLI, attribution and snapshot tasks.
- Thread correlation uses `sessions.external_session_id` exactly throughout.

## Execution Checkpoints

The implementation should be reviewed at three natural checkpoints:

1. After Task 4: Phase A can safely read and persist account/rate-limit snapshots.
2. After Task 5: Phase B can query exact historical threads and preserve backend model groups.
3. After Tasks 6–8: attribution/dashboard/security/full acceptance are complete.
