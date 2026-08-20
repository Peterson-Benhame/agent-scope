from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from agentscope.codex_account.app_server import CodexAppServerClient, CodexAppServerError
from agentscope.codex_account.models import CodexAccountSnapshot
from agentscope.codex_account.storage import CodexAccountStorage
from agentscope.storage.repository import Repository


@dataclass(frozen=True, slots=True)
class CodexAccountSyncResult:
    status: str
    account_snapshot_id: int | None
    plan_type: str | None
    credits_balance: str | None
    error_code: str | None = None


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
