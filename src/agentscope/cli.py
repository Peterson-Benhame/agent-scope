from __future__ import annotations

import json
from dataclasses import asdict
from datetime import date
from pathlib import Path
from typing import Optional

import typer

from agentscope.analytics.budget import calculate_budget_status
from agentscope.analytics.filters import AnalyticsFilter, resolve_period
from agentscope.analytics.service import AnalyticsService
from agentscope.analytics.team_service import TeamAnalyticsService
from agentscope.config import AgentScopeConfig
from agentscope.extension.snapshot import build_extension_snapshot
from agentscope.identity_backfill import backfill_local_identity
from agentscope.importer import (
    ProgressEvent,
    collect_registered_sources,
    discover_registered_sources,
)
from agentscope.reporting.export import export_datasets
from agentscope.reporting.html_report import generate_html_report
from agentscope.reporting.team_html_report import generate_team_html_report
from agentscope.storage.database import Database
from agentscope.storage.repository import Repository
from agentscope.team.bundle import build_team_bundle
from agentscope.team.importer import import_team_bundle

app = typer.Typer(help="Local-first observability and analytics for agent execution histories.")
team_app = typer.Typer(help="Export, import and report sanitized team telemetry.")
extension_app = typer.Typer(help="Machine-readable integration commands.")
identity_app = typer.Typer(help="Identity maintenance commands.")
app.add_typer(team_app, name="team")
app.add_typer(extension_app, name="extension")
app.add_typer(identity_app, name="identity")


def _render_collect_progress(event: ProgressEvent) -> None:
    if event.stage == "discovering":
        typer.echo("Descobrindo fontes...")
        return
    if event.stage == "source_detected":
        source = event.source.capitalize() if event.source else "Desconhecida"
        typer.echo(f"Fonte detectada: {source}")
        return
    if event.stage == "source_failed":
        source = event.source.capitalize() if event.source else "Desconhecida"
        typer.echo(f"Falha na fonte: {source}")
        return
    if event.stage == "collecting":
        total = event.total
        percent = int((event.current / total) * 100) if total else 0
        width = 30
        filled = int((percent / 100) * width)
        bar = "█" * filled + "░" * (width - filled)
        source = event.source.capitalize() if event.source else ""
        filename = Path(event.current_file).name if event.current_file else ""
        if len(filename) > 48:
            filename = f"{filename[:45]}..."
        detail = " ".join(part for part in (source, filename) if part)
        suffix = f" {detail}" if detail else ""
        typer.echo(
            f"\rColetando [{bar}] {percent:3d}% {event.current}/{total}{suffix}",
            nl=bool(total and event.current >= total),
        )
        return
    if event.stage == "complete":
        if event.total == 0:
            typer.echo(f"Coletando [{'█' * 30}] 100% 0/0")
        typer.echo("Finalizado.")


def _repository(database: Path) -> Repository:
    db = Database(database)
    db.initialize()
    return Repository(db)


def _parse_date(value: str | None, option: str) -> date | None:
    if value is None:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise typer.BadParameter(
            f"Data inválida em {option}: {value}. Use YYYY-MM-DD."
        ) from exc


def _analytics_filter(
    *,
    period: str | None,
    from_value: str | None,
    to_value: str | None,
    project: str | None,
    model: str | None,
    source: str | None,
    user: str | None,
    machine: str | None,
) -> AnalyticsFilter:
    from_date = _parse_date(from_value, "--from")
    to_date = _parse_date(to_value, "--to")
    try:
        resolved = resolve_period(period, from_date, to_date)
    except ValueError as exc:
        raise typer.BadParameter(
            f"Período inválido: {period}. Use today, 7d, 30d ou month."
        ) from exc
    return AnalyticsFilter(
        from_date=resolved.from_date,
        to_date=resolved.to_date,
        project=project,
        model=model,
        source=source,
        user=user,
        machine=machine,
    )


@app.command()
def collect(
    codex_home: Optional[Path] = typer.Option(None, "--codex-home"),
    headroom_home: Optional[Path] = typer.Option(None, "--headroom-home"),
    database: Optional[Path] = typer.Option(None, "--database"),
    full_rescan: bool = typer.Option(False, "--full-rescan"),
) -> None:
    config = AgentScopeConfig.from_env(
        codex_home=codex_home,
        headroom_home=headroom_home,
        database_path=database,
    )
    repo = _repository(config.database_path)
    summary = collect_registered_sources(
        repo,
        config,
        full_rescan=full_rescan,
        progress=_render_collect_progress,
    )
    typer.echo(
        f"files_seen={summary.files_seen} files_imported={summary.files_imported} "
        f"files_skipped={summary.files_skipped} sessions_imported={summary.sessions_imported} "
        f"optimizations_imported={summary.optimizations_imported} errors={summary.errors}"
    )
    for diagnostic in summary.diagnostics:
        typer.echo(f"diagnostic={diagnostic}")
    if summary.errors:
        raise typer.Exit(code=1)


@identity_app.command("backfill")
def identity_backfill(
    database: Optional[Path] = typer.Option(None, "--database"),
    source: Optional[str] = typer.Option(None, "--source"),
    user_name: Optional[str] = typer.Option(None, "--user-name"),
    machine_name: Optional[str] = typer.Option(None, "--machine-name"),
) -> None:
    config = AgentScopeConfig.from_env(
        database_path=database,
        enabled_sources={source} if source else None,
        user_display_name=user_name,
        machine_display_name=machine_name,
    )
    repo = _repository(config.database_path)
    active_sources = frozenset({source}) if source else None
    summary = backfill_local_identity(
        repo,
        config,
        sources=active_sources,
    )
    typer.echo(
        f"sessions_scanned={summary.sessions_scanned} "
        f"sessions_updated={summary.sessions_updated} "
        f"sessions_without_user={summary.sessions_without_user} "
        f"sessions_without_machine={summary.sessions_without_machine} "
        f"errors={summary.errors}"
    )
    if summary.errors:
        raise typer.Exit(code=1)


@app.command()
def status(
    database: Optional[Path] = typer.Option(None, "--database"),
    codex_home: Optional[Path] = typer.Option(None, "--codex-home"),
    headroom_home: Optional[Path] = typer.Option(None, "--headroom-home"),
) -> None:
    config = AgentScopeConfig.from_env(
        codex_home=codex_home,
        headroom_home=headroom_home,
        database_path=database,
    )
    repo = _repository(config.database_path)
    with repo.database.connect() as conn:
        sessions = conn.execute("SELECT COUNT(*) AS n FROM sessions").fetchone()["n"]
        errors = conn.execute("SELECT COUNT(*) AS n FROM import_errors").fetchone()["n"]
        imports = conn.execute("SELECT COUNT(*) AS n FROM import_state").fetchone()["n"]
    discoveries = discover_registered_sources(config)
    typer.echo(
        f"database={config.database_path} sessions={sessions} imports={imports} errors={errors}"
    )
    for discovery in discoveries:
        detected = "yes" if discovery.detected else "no"
        line = (
            f"source={discovery.source} detected={detected} "
            f"artifacts={len(discovery.artifacts)}"
        )
        if discovery.diagnostic:
            line += f" diagnostic={discovery.diagnostic}"
        typer.echo(line)


@app.command()
def analyze(
    database: Optional[Path] = typer.Option(None, "--database"),
    from_value: Optional[str] = typer.Option(None, "--from"),
    to_value: Optional[str] = typer.Option(None, "--to"),
    period: Optional[str] = typer.Option(None, "--period"),
    project: Optional[str] = typer.Option(None, "--project"),
    model: Optional[str] = typer.Option(None, "--model"),
    source: Optional[str] = typer.Option(None, "--source"),
    user: Optional[str] = typer.Option(None, "--user"),
    machine: Optional[str] = typer.Option(None, "--machine"),
) -> None:
    config = AgentScopeConfig.from_env(database_path=database)
    repo = _repository(config.database_path)
    filters = _analytics_filter(
        period=period, from_value=from_value, to_value=to_value,
        project=project, model=model, source=source, user=user, machine=machine,
    )
    summary = AnalyticsService(repo, filters).summary()
    typer.echo(json.dumps(asdict(summary), ensure_ascii=False, indent=2))


@app.command("export")
def export_command(
    database: Optional[Path] = typer.Option(None, "--database"),
    output_dir: Optional[Path] = typer.Option(None, "--output-dir"),
    full_content: bool = typer.Option(False, "--full-content", help="Explicitly include full message content."),
    from_value: Optional[str] = typer.Option(None, "--from"),
    to_value: Optional[str] = typer.Option(None, "--to"),
    period: Optional[str] = typer.Option(None, "--period"),
    project: Optional[str] = typer.Option(None, "--project"),
    model: Optional[str] = typer.Option(None, "--model"),
    source: Optional[str] = typer.Option(None, "--source"),
    user: Optional[str] = typer.Option(None, "--user"),
    machine: Optional[str] = typer.Option(None, "--machine"),
) -> None:
    config = AgentScopeConfig.from_env(database_path=database, reports_path=output_dir)
    repo = _repository(config.database_path)
    filters = _analytics_filter(
        period=period, from_value=from_value, to_value=to_value,
        project=project, model=model, source=source, user=user, machine=machine,
    )
    analytics = AnalyticsService(repo, filters)
    created = export_datasets(
        repo, analytics, config.reports_path,
        filters=filters, include_content=full_content,
    )
    typer.echo(f"created={len(created)} output={config.reports_path}")


@app.command()
def report(
    database: Optional[Path] = typer.Option(None, "--database"),
    output: Optional[Path] = typer.Option(None, "--output"),
    from_value: Optional[str] = typer.Option(None, "--from"),
    to_value: Optional[str] = typer.Option(None, "--to"),
    period: Optional[str] = typer.Option(None, "--period"),
    project: Optional[str] = typer.Option(None, "--project"),
    model: Optional[str] = typer.Option(None, "--model"),
    source: Optional[str] = typer.Option(None, "--source"),
    user: Optional[str] = typer.Option(None, "--user"),
    machine: Optional[str] = typer.Option(None, "--machine"),
) -> None:
    config = AgentScopeConfig.from_env(database_path=database)
    repo = _repository(config.database_path)
    filters = _analytics_filter(
        period=period, from_value=from_value, to_value=to_value,
        project=project, model=model, source=source, user=user, machine=machine,
    )
    analytics = AnalyticsService(repo, filters)
    target = output or (config.reports_path / "report.html")
    generate_html_report(repo, analytics, target, filters=filters)
    typer.echo(f"report={target}")


@extension_app.command("snapshot")
def extension_snapshot(
    json_output: bool = typer.Option(False, "--json"),
    database: Optional[Path] = typer.Option(None, "--database"),
    from_value: Optional[str] = typer.Option(None, "--from"),
    to_value: Optional[str] = typer.Option(None, "--to"),
    period: Optional[str] = typer.Option(None, "--period"),
    project: Optional[str] = typer.Option(None, "--project"),
    model: Optional[str] = typer.Option(None, "--model"),
    source: Optional[str] = typer.Option(None, "--source"),
    user: Optional[str] = typer.Option(None, "--user"),
    machine: Optional[str] = typer.Option(None, "--machine"),
) -> None:
    if not json_output:
        raise typer.BadParameter("Use --json for the extension snapshot contract.")
    config = AgentScopeConfig.from_env(database_path=database)
    if not config.database_path.exists():
        typer.echo(f"database not found: {config.database_path}", err=True)
        raise typer.Exit(code=2)
    repo = _repository(config.database_path)
    filters = _analytics_filter(
        period=period, from_value=from_value, to_value=to_value,
        project=project, model=model, source=source, user=user, machine=machine,
    )
    payload = build_extension_snapshot(
        repo,
        filters,
        period=period,
        database_path=config.database_path,
    )
    typer.echo(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))


@team_app.command("export")
def team_export(
    output: Path = typer.Option(..., "--output"),
    database: Optional[Path] = typer.Option(None, "--database"),
    organization: Optional[str] = typer.Option(None, "--organization"),
    team: Optional[str] = typer.Option(None, "--team"),
    from_value: Optional[str] = typer.Option(None, "--from"),
    to_value: Optional[str] = typer.Option(None, "--to"),
    period: Optional[str] = typer.Option(None, "--period"),
    project: Optional[str] = typer.Option(None, "--project"),
    model: Optional[str] = typer.Option(None, "--model"),
    source: Optional[str] = typer.Option(None, "--source"),
    user: Optional[str] = typer.Option(None, "--user"),
    machine: Optional[str] = typer.Option(None, "--machine"),
) -> None:
    config = AgentScopeConfig.from_env(database_path=database)
    repo = _repository(config.database_path)
    filters = _analytics_filter(
        period=period, from_value=from_value, to_value=to_value,
        project=project, model=model, source=source, user=user, machine=machine,
    )
    bundle = build_team_bundle(
        repo, analytics_filter=filters, organization=organization, team=team,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(bundle, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    typer.echo(f"bundle_id={bundle['bundle_id']} output={output}")


@team_app.command("import")
def team_import(
    bundle_path: Path = typer.Argument(..., exists=True, dir_okay=False, readable=True),
    database: Optional[Path] = typer.Option(None, "--database"),
) -> None:
    config = AgentScopeConfig.from_env(database_path=database)
    repo = _repository(config.database_path)
    try:
        bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
        summary = import_team_bundle(repo, bundle)
    except (OSError, json.JSONDecodeError, ValueError, TypeError, KeyError) as exc:
        typer.echo(f"error={exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(
        f"bundle_id={summary.bundle_id} sessions_imported={summary.sessions_imported} "
        f"events_imported={summary.events_imported} events_skipped={summary.events_skipped} "
        f"errors={summary.errors}"
    )
    if summary.errors:
        raise typer.Exit(code=1)


@team_app.command("report")
def team_report(
    database: Optional[Path] = typer.Option(None, "--database"),
    output: Optional[Path] = typer.Option(None, "--output"),
    from_value: Optional[str] = typer.Option(None, "--from"),
    to_value: Optional[str] = typer.Option(None, "--to"),
    period: Optional[str] = typer.Option(None, "--period"),
    project: Optional[str] = typer.Option(None, "--project"),
    model: Optional[str] = typer.Option(None, "--model"),
    source: Optional[str] = typer.Option(None, "--source"),
    user: Optional[str] = typer.Option(None, "--user"),
    machine: Optional[str] = typer.Option(None, "--machine"),
    monthly_budget_usd: Optional[float] = typer.Option(None, "--monthly-budget-usd"),
) -> None:
    try:
        config = AgentScopeConfig.from_env(
            database_path=database,
            monthly_budget_usd=monthly_budget_usd,
        )
    except ValueError as exc:
        raise typer.BadParameter(str(exc), param_hint="--monthly-budget-usd") from exc
    repo = _repository(config.database_path)
    filters = _analytics_filter(
        period=period, from_value=from_value, to_value=to_value,
        project=project, model=model, source=source, user=user, machine=machine,
    )
    analytics = TeamAnalyticsService(repo, filters)
    as_of = filters.to_date or date.today()
    budget = None
    if config.monthly_budget_usd is not None:
        budget_filters = AnalyticsFilter(
            from_date=as_of.replace(day=1),
            to_date=as_of,
            project=filters.project,
            model=filters.model,
            source=filters.source,
            user=filters.user,
            machine=filters.machine,
        )
        budget_spend = TeamAnalyticsService(repo, budget_filters).summary().observed_cost_usd
        budget = calculate_budget_status(
            config.monthly_budget_usd,
            budget_spend,
            as_of,
        )
    target = output or (config.reports_path / "team-report.html")
    generate_team_html_report(repo, analytics, target, budget=budget)
    typer.echo(f"report={target}")


if __name__ == "__main__":
    app()
