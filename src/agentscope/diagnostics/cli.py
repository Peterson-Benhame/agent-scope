from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Optional

import typer

from agentscope.analytics.filters import AnalyticsFilter, resolve_period
from agentscope.config import AgentScopeConfig
from agentscope.diagnostics.codex_origin import CodexOriginDiagnostics
from agentscope.storage.database import Database
from agentscope.storage.repository import Repository


app = typer.Typer(
    help="Inspect Codex session origin using locally stored evidence.",
    invoke_without_command=True,
)


def _parse_date(value: str | None, option: str) -> date | None:
    if value is None:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise typer.BadParameter(
            f"Data inválida em {option}: {value}. Use YYYY-MM-DD."
        ) from exc


@app.callback(invoke_without_command=True)
def inspect_codex_origin(
    json_output: bool = typer.Option(False, "--json"),
    database: Optional[Path] = typer.Option(None, "--database"),
    from_value: Optional[str] = typer.Option(None, "--from"),
    to_value: Optional[str] = typer.Option(None, "--to"),
    period: Optional[str] = typer.Option(None, "--period"),
    project: Optional[str] = typer.Option(None, "--project"),
    model: Optional[str] = typer.Option(None, "--model"),
    user: Optional[str] = typer.Option(None, "--user"),
    machine: Optional[str] = typer.Option(None, "--machine"),
) -> None:
    config = AgentScopeConfig.from_env(database_path=database)
    if not config.database_path.exists():
        typer.echo(f"database not found: {config.database_path}", err=True)
        raise typer.Exit(code=2)

    from_date = _parse_date(from_value, "--from")
    to_date = _parse_date(to_value, "--to")
    try:
        resolved = resolve_period(period, from_date, to_date)
    except ValueError as exc:
        raise typer.BadParameter(
            f"Período inválido: {period}. Use today, 7d, 30d ou month."
        ) from exc

    db = Database(config.database_path)
    db.initialize()
    repo = Repository(db)
    filters = AnalyticsFilter(
        from_date=resolved.from_date,
        to_date=resolved.to_date,
        project=project,
        model=model,
        source="codex",
        user=user,
        machine=machine,
    )
    payload = CodexOriginDiagnostics(repo, filters).inspect()

    if json_output:
        typer.echo(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
        return

    summary = payload["summary"]
    typer.echo(
        f"sessions={summary['sessions']} total_tokens={summary['total_tokens']} "
        f"unclassified_sessions={summary['unclassified_sessions']}"
    )
    for client in summary["clients"]:
        typer.echo(
            f"client={client['client']} sessions={client['sessions']} "
            f"total_tokens={client['total_tokens']}"
        )


if __name__ == "__main__":
    app()
