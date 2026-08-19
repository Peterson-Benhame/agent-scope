from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Optional

import typer

from agentscope.analytics.service import AnalyticsService
from agentscope.config import AgentScopeConfig
from agentscope.importer import ProgressEvent, collect_sources
from agentscope.reporting.export import export_datasets
from agentscope.reporting.html_report import generate_html_report
from agentscope.storage.database import Database
from agentscope.storage.repository import Repository

app = typer.Typer(help="Local-first observability and analytics for agent execution histories.")


def _render_collect_progress(event: ProgressEvent) -> None:
    if event.stage == "discovering":
        typer.echo("Descobrindo arquivos...")
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


@app.command()
def collect(
    codex_home: Optional[Path] = typer.Option(None, "--codex-home"),
    headroom_home: Optional[Path] = typer.Option(None, "--headroom-home"),
    database: Optional[Path] = typer.Option(None, "--database"),
    full_rescan: bool = typer.Option(False, "--full-rescan"),
) -> None:
    config = AgentScopeConfig.from_env(codex_home=codex_home, headroom_home=headroom_home, database_path=database)
    repo = _repository(config.database_path)
    summary = collect_sources(
        repo,
        codex_home=config.codex_home,
        headroom_home=config.headroom_home,
        full_rescan=full_rescan,
        progress=_render_collect_progress,
    )
    typer.echo(
        f"files_seen={summary.files_seen} files_imported={summary.files_imported} "
        f"files_skipped={summary.files_skipped} sessions_imported={summary.sessions_imported} "
        f"optimizations_imported={summary.optimizations_imported} errors={summary.errors}"
    )
    if summary.errors:
        raise typer.Exit(code=1)


@app.command()
def status(
    database: Optional[Path] = typer.Option(None, "--database"),
    codex_home: Optional[Path] = typer.Option(None, "--codex-home"),
    headroom_home: Optional[Path] = typer.Option(None, "--headroom-home"),
) -> None:
    config = AgentScopeConfig.from_env(codex_home=codex_home, headroom_home=headroom_home, database_path=database)
    repo = _repository(config.database_path)
    with repo.database.connect() as conn:
        sessions = conn.execute("SELECT COUNT(*) AS n FROM sessions").fetchone()["n"]
        errors = conn.execute("SELECT COUNT(*) AS n FROM import_errors").fetchone()["n"]
        imports = conn.execute("SELECT COUNT(*) AS n FROM import_state").fetchone()["n"]
    codex_files = len(list((config.codex_home / "sessions").rglob("*.jsonl"))) if (config.codex_home / "sessions").exists() else 0
    headroom_files = len([p for p in [config.headroom_home / "proxy_savings.json", *config.headroom_home.glob("*.jsonl")] if p.exists()]) if config.headroom_home.exists() else 0
    typer.echo(
        f"database={config.database_path} sessions={sessions} imports={imports} errors={errors} "
        f"codex_files={codex_files} headroom_files={headroom_files}"
    )


@app.command()
def analyze(database: Optional[Path] = typer.Option(None, "--database")) -> None:
    config = AgentScopeConfig.from_env(database_path=database)
    repo = _repository(config.database_path)
    summary = AnalyticsService(repo).summary()
    typer.echo(json.dumps(asdict(summary), ensure_ascii=False, indent=2))


@app.command("export")
def export_command(
    database: Optional[Path] = typer.Option(None, "--database"),
    output_dir: Optional[Path] = typer.Option(None, "--output-dir"),
    full_content: bool = typer.Option(False, "--full-content", help="Explicitly include full message content."),
) -> None:
    config = AgentScopeConfig.from_env(database_path=database, reports_path=output_dir)
    repo = _repository(config.database_path)
    created = export_datasets(repo, AnalyticsService(repo), config.reports_path, include_content=full_content)
    typer.echo(f"created={len(created)} output={config.reports_path}")


@app.command()
def report(
    database: Optional[Path] = typer.Option(None, "--database"),
    output: Optional[Path] = typer.Option(None, "--output"),
) -> None:
    config = AgentScopeConfig.from_env(database_path=database)
    repo = _repository(config.database_path)
    target = output or (config.reports_path / "report.html")
    generate_html_report(repo, AnalyticsService(repo), target)
    typer.echo(f"report={target}")


if __name__ == "__main__":
    app()
