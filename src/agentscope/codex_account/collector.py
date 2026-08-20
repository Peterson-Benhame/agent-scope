from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any, Sequence

from agentscope.codex_account.app_server import CodexAppServerClient, CodexAppServerError
from agentscope.codex_account.models import (
    CodexAccountSnapshot,
    CodexThreadUsageGroup,
    CodexThreadUsageSnapshot,
)
from agentscope.codex_account.storage import CodexAccountStorage
from agentscope.storage.repository import Repository


@dataclass(frozen=True, slots=True)
class CodexAccountSyncResult:
    status: str
    account_snapshot_id: int | None
    plan_type: str | None
    credits_balance: str | None
    error_code: str | None = None


@dataclass(frozen=True, slots=True)
class LocalCodexThread:
    thread_id: str
    session_id: int
    started_at: str | None


@dataclass(frozen=True, slots=True)
class ThreadSyncSummary:
    threads_requested: int
    threads_synced: int
    threads_unavailable: int
    errors: int


def _string_or_none(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _int_or_none(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    return value if isinstance(value, int) else None


def _bool_or_none(value: object) -> bool | None:
    return value if isinstance(value, bool) else None


def _dict_or_empty(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _map_account_and_limits(
    account_result: dict[str, object],
    limits_result: dict[str, object],
    captured_at: str,
) -> CodexAccountSnapshot:
    account = _dict_or_empty(account_result.get("account"))
    limits = _dict_or_empty(limits_result.get("rateLimits"))
    primary = _dict_or_empty(limits.get("primary"))
    secondary = _dict_or_empty(limits.get("secondary"))
    credits = _dict_or_empty(limits.get("credits"))
    individual = _dict_or_empty(limits.get("individualLimit"))
    return CodexAccountSnapshot(
        captured_at=captured_at,
        auth_mode=_string_or_none(account.get("type")),
        plan_type=_string_or_none(account.get("planType") or limits.get("planType")),
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


def sync_account_usage(
    repository: Repository,
    *,
    client: CodexAppServerClient | object | None = None,
    codex_bin: str = "codex",
    timeout_seconds: float = 10.0,
) -> CodexAccountSyncResult:
    storage = CodexAccountStorage(repository.database)
    owns_client = client is None
    active_client = client or CodexAppServerClient(
        codex_bin=codex_bin,
        timeout_seconds=timeout_seconds,
    )
    try:
        if owns_client:
            active_client.start()
        account_result = active_client.account_read()
        limits_result = active_client.account_rate_limits_read()
        if not isinstance(account_result, dict) or not isinstance(limits_result, dict):
            raise ValueError("invalid account response")
        snapshot = _map_account_and_limits(
            account_result,
            limits_result,
            datetime.now(timezone.utc).isoformat(),
        )
        snapshot_id = storage.insert_account_snapshot(snapshot)
        return CodexAccountSyncResult(
            status="complete",
            account_snapshot_id=snapshot_id,
            plan_type=snapshot.plan_type,
            credits_balance=snapshot.credits_balance,
        )
    except CodexAppServerError as exc:
        return CodexAccountSyncResult(
            status="failed",
            account_snapshot_id=None,
            plan_type=None,
            credits_balance=None,
            error_code=exc.code,
        )
    except Exception:
        return CodexAccountSyncResult(
            status="failed",
            account_snapshot_id=None,
            plan_type=None,
            credits_balance=None,
            error_code="account_sync_failed",
        )
    finally:
        if owns_client:
            active_client.close()


def select_local_codex_threads(
    repository: Repository,
    from_date: date | None,
    to_date: date | None,
    *,
    utc_offset_minutes: int,
) -> list[LocalCodexThread]:
    clauses = ["src.name='codex'", "trim(s.external_session_id) <> ''"]
    params: list[object] = []
    modifier = f"{utc_offset_minutes:+d} minutes"
    if from_date is not None:
        clauses.append("date(s.started_at, ?) >= ?")
        params.extend([modifier, from_date.isoformat()])
    if to_date is not None:
        clauses.append("date(s.started_at, ?) <= ?")
        params.extend([modifier, to_date.isoformat()])
    with repository.database.connect() as conn:
        rows = conn.execute(
            """
            SELECT s.id, s.external_session_id, s.started_at
            FROM sessions s
            JOIN sources src ON src.id=s.source_id
            WHERE """
            + " AND ".join(clauses)
            + " ORDER BY s.started_at, s.id",
            params,
        ).fetchall()
    return [
        LocalCodexThread(
            thread_id=str(row["external_session_id"]),
            session_id=int(row["id"]),
            started_at=str(row["started_at"]) if row["started_at"] is not None else None,
        )
        for row in rows
    ]


def _map_thread_group(value: object) -> CodexThreadUsageGroup | None:
    group = _dict_or_empty(value)
    credits = _int_or_none(group.get("estimatedUsageCreditsMicros"))
    if credits is None:
        return None
    return CodexThreadUsageGroup(
        model=_string_or_none(group.get("model")),
        reasoning_effort=_string_or_none(group.get("reasoningEffort")),
        speed=_string_or_none(group.get("speed")),
        estimated_usage_credits_micros=credits,
        net_new_input_tokens=_int_or_none(group.get("netNewInputTokens")),
        cached_input_tokens=_int_or_none(group.get("cachedInputTokens")),
        input_tokens=_int_or_none(group.get("inputTokens")),
        output_tokens=_int_or_none(group.get("outputTokens")),
        total_tokens=_int_or_none(group.get("totalTokens")),
    )


def _map_thread_usage(
    thread: LocalCodexThread,
    result: dict[str, object],
    captured_at: str,
) -> CodexThreadUsageSnapshot:
    usage_value = result.get("threadUsage")
    if not isinstance(usage_value, dict):
        return CodexThreadUsageSnapshot(
            captured_at=captured_at,
            thread_id=thread.thread_id,
            session_id=thread.session_id,
            estimated_usage_credits_micros=None,
            estimated_usage_usd_micros=None,
            billing_route_available=False,
        )
    response_thread_id = _string_or_none(usage_value.get("threadId"))
    if response_thread_id != thread.thread_id:
        return CodexThreadUsageSnapshot(
            captured_at=captured_at,
            thread_id=thread.thread_id,
            session_id=thread.session_id,
            estimated_usage_credits_micros=None,
            estimated_usage_usd_micros=None,
            status="invalid_thread_response",
            billing_route_available=False,
        )
    raw_groups = usage_value.get("groups")
    groups = tuple(
        group
        for group in (
            _map_thread_group(value)
            for value in raw_groups
        )
        if group is not None
    ) if isinstance(raw_groups, list) else ()
    return CodexThreadUsageSnapshot(
        captured_at=captured_at,
        thread_id=thread.thread_id,
        session_id=thread.session_id,
        estimated_usage_credits_micros=_int_or_none(
            usage_value.get("estimatedUsageCreditsMicros")
        ),
        estimated_usage_usd_micros=_int_or_none(
            usage_value.get("estimatedUsageUsdMicros")
        ),
        groups=groups,
    )


def sync_thread_usage(
    repository: Repository,
    *,
    client: object,
    thread_ids: Sequence[LocalCodexThread],
) -> ThreadSyncSummary:
    storage = CodexAccountStorage(repository.database)
    synced = 0
    unavailable = 0
    errors = 0
    for thread in thread_ids:
        captured_at = datetime.now(timezone.utc).isoformat()
        try:
            result = client.account_usage_read(thread.thread_id)
            if not isinstance(result, dict):
                raise ValueError("invalid thread usage response")
            snapshot = _map_thread_usage(thread, result, captured_at)
            storage.insert_thread_usage_snapshot(snapshot)
            if snapshot.billing_route_available:
                synced += 1
            else:
                unavailable += 1
        except Exception:
            errors += 1
    return ThreadSyncSummary(
        threads_requested=len(thread_ids),
        threads_synced=synced,
        threads_unavailable=unavailable,
        errors=errors,
    )
