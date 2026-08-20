from __future__ import annotations

import json
from dataclasses import asdict
from datetime import date
from pathlib import Path
from typing import Optional

import typer

from agentscope.analytics.filters import current_local_utc_offset_minutes
from agentscope.cli import app
from agentscope.codex_account.app_server import CodexAppServerClient
from agentscope.codex_account.collector import (
    select_local_codex_threads,
    sync_account_usage,
    sync_thread_usage,
)
from agentscope.codex_account.storage import CodexAccountStorage
from agentscope.config import AgentScopeConfig
from agentscope.storage.database import Database
from agentscope.storage.repository import Repository


codex_account_app = typer.Typer(
    help="Read-only ChatGPT/Codex account usage snapshots."
)
app.add_typer(codex_account_app, name="codex-account")


def _repository(database: Path) -> Repository:
    db = Database(database)
    db.initialize()
    return Repository(db)


def _optional_date(value: str | None, option_name: str) -> date | None:
    if value is None:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise typer.BadParameter(
            f"Data inválida em {option_name}: {value}. Use YYYY-MM-DD."
        ) from exc


def _status_payload(storage: CodexAccountStorage) -> dict[str, object]:
    snapshot = storage.latest_account_snapshot()
    if snapshot is None:
        return {"available": False, "reason": "no_account_snapshot"}
    return {
        "available": True,
        "captured_at": snapshot.captured_at,
        "auth_mode": snapshot.auth_mode,
        "plan_type": snapshot.plan_type,
        "limit_id": snapshot.limit_id,
        "limit_name": snapshot.limit_name,
        "primary_used_percent": snapshot.primary_used_percent,
        "primary_window_duration_mins": snapshot.primary_window_duration_mins,
        "primary_resets_at": snapshot.primary_resets_at,
        "secondary_used_percent": snapshot.secondary_used_percent,
        "secondary_window_duration_mins": snapshot.secondary_window_duration_mins,
        "secondary_resets_at": snapshot.secondary_resets_at,
        "credits_has_credits": snapshot.credits_has_credits,
        "credits_balance": snapshot.credits_balance,
        "credits_unlimited": snapshot.credits_unlimited,
        "spend_control_reached": snapshot.spend_control_reached,
        "individual_limit": snapshot.individual_limit,
        "individual_used": snapshot.individual_used,
        "individual_remaining_percent": snapshot.individual_remaining_percent,
        "individual_resets_at": snapshot.individual_resets_at,
        "source": snapshot.source,
    }


@codex_account_app.command("status")
def codex_account_status(
    database: Optional[Path] = typer.Option(None, "--database"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    config = AgentScopeConfig.from_env(database_path=database)
    repo = _repository(config.database_path)
    payload = _status_payload(CodexAccountStorage(repo.database))
    if json_output:
        typer.echo(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
        return
    if not payload["available"]:
        typer.echo("codex_account=unavailable reason=no_account_snapshot")
        return
    typer.echo(
        f"plan_type={payload['plan_type'] or 'unavailable'} "
        f"primary_used_percent={payload['primary_used_percent']} "
        f"credits_balance={payload['credits_balance'] or 'unavailable'}"
    )


@codex_account_app.command("sync")
def codex_account_sync(
    database: Optional[Path] = typer.Option(None, "--database"),
    codex_bin: str = typer.Option("codex", "--codex-bin"),
    timeout_seconds: float = typer.Option(10.0, "--timeout-seconds", min=0.1),
    threads: bool = typer.Option(False, "--threads"),
    from_value: Optional[str] = typer.Option(None, "--from"),
    to_value: Optional[str] = typer.Option(None, "--to"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    config = AgentScopeConfig.from_env(database_path=database)
    repo = _repository(config.database_path)
    from_date = _optional_date(from_value, "--from")
    to_date = _optional_date(to_value, "--to")
    if from_date is not None and to_date is not None and from_date > to_date:
        raise typer.BadParameter("--from não pode ser posterior a --to.")

    with CodexAppServerClient(
        codex_bin=codex_bin,
        timeout_seconds=timeout_seconds,
    ) as client:
        result = sync_account_usage(repo, client=client)
        thread_summary = None
        if result.status == "complete" and threads:
            local_threads = select_local_codex_threads(
                repo,
                from_date,
                to_date,
                utc_offset_minutes=current_local_utc_offset_minutes(),
            )
            thread_summary = sync_thread_usage(
                repo,
                client=client,
                thread_ids=local_threads,
            )

    payload = asdict(result)
    if thread_summary is not None:
        payload["threads"] = asdict(thread_summary)
    if json_output:
        typer.echo(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
    else:
        typer.echo(
            f"status={result.status} "
            f"plan_type={result.plan_type or 'unavailable'} "
            f"credits_balance={result.credits_balance or 'unavailable'} "
            f"error_code={result.error_code or 'none'}"
        )
        if thread_summary is not None:
            typer.echo(
                f"threads_requested={thread_summary.threads_requested} "
                f"threads_synced={thread_summary.threads_synced} "
                f"threads_unavailable={thread_summary.threads_unavailable} "
                f"thread_errors={thread_summary.errors}"
            )
    if result.status != "complete":
        raise typer.Exit(code=1)


__all__ = ["app"]
