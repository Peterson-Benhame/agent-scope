from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from agentscope.config import AgentScopeConfig
from agentscope.identity import resolve_local_identity
from agentscope.sources.base import (
    CollectRequest,
    DiscoveryContext,
    SourceCollectionSummary,
    SourceDiscovery,
)
from agentscope.sources.claude_code import ClaudeCodeAdapter
from agentscope.sources.codex import CodexAdapter
from agentscope.sources.gemini import GeminiAdapter
from agentscope.sources.github_copilot import GitHubCopilotAdapter
from agentscope.sources.headroom import HeadroomAdapter
from agentscope.sources.kimi import KimiAdapter
from agentscope.sources.registry import SourceRegistry
from agentscope.storage.repository import Repository


ImportSummary = SourceCollectionSummary


@dataclass(frozen=True, slots=True)
class ProgressEvent:
    stage: str
    current: int
    total: int
    source: str | None = None
    current_file: str | None = None


ProgressCallback = Callable[[ProgressEvent], None]


def _emit(progress: ProgressCallback | None, event: ProgressEvent) -> None:
    if progress is not None:
        progress(event)


def default_source_registry() -> SourceRegistry:
    return SourceRegistry(
        [
            CodexAdapter(),
            HeadroomAdapter(),
            ClaudeCodeAdapter(),
            GitHubCopilotAdapter(),
            KimiAdapter(),
            GeminiAdapter(),
        ]
    )


def discovery_context(config: AgentScopeConfig) -> DiscoveryContext:
    overrides: dict[str, Path] = {
        "codex": config.codex_home,
        "headroom": config.headroom_home,
    }
    optional_homes = {
        "claude_code": config.claude_home,
        "github_copilot": config.copilot_home,
        "kimi": config.kimi_home,
        "gemini": config.gemini_home,
    }
    overrides.update(
        {source: path for source, path in optional_homes.items() if path is not None}
    )
    return DiscoveryContext(
        user_home=config.codex_home.parent,
        overrides=overrides,
    )


def discover_registered_sources(
    config: AgentScopeConfig,
    *,
    registry: SourceRegistry | None = None,
) -> list[SourceDiscovery]:
    active_registry = registry or default_source_registry()
    return active_registry.discover(
        discovery_context(config),
        enabled_sources=config.enabled_sources,
    )


def collect_registered_sources(
    repository: Repository,
    config: AgentScopeConfig,
    *,
    registry: SourceRegistry | None = None,
    full_rescan: bool = False,
    progress: ProgressCallback | None = None,
) -> ImportSummary:
    active_registry = registry or default_source_registry()
    local_user, local_machine = resolve_local_identity(config)

    _emit(progress, ProgressEvent(stage="discovering", current=0, total=0))
    discoveries = discover_registered_sources(config, registry=active_registry)
    detected = [item for item in discoveries if item.detected]
    total_files = sum(len(item.artifacts) for item in detected)
    processed_files = 0
    summary = ImportSummary(
        diagnostics=tuple(
            discovery.diagnostic
            for discovery in discoveries
            if discovery.diagnostic
        )
    )

    for discovery in discoveries:
        if not discovery.detected:
            continue
        _emit(
            progress,
            ProgressEvent(
                stage="source_detected",
                current=processed_files,
                total=total_files,
                source=discovery.source,
            ),
        )

    _emit(
        progress,
        ProgressEvent(
            stage="collecting",
            current=processed_files,
            total=total_files,
        ),
    )

    for discovery in detected:
        adapter = active_registry.adapter_for(discovery.source)
        try:
            result = adapter.collect(
                CollectRequest(
                    repository=repository,
                    discovery=discovery,
                    full_rescan=full_rescan,
                    progress=progress,
                    user=local_user,
                    machine=local_machine,
                )
            )
            summary = summary + result
            for artifact in discovery.artifacts:
                processed_files += 1
                _emit(
                    progress,
                    ProgressEvent(
                        stage="collecting",
                        current=processed_files,
                        total=total_files,
                        source=discovery.source,
                        current_file=str(artifact),
                    ),
                )
            _emit(
                progress,
                ProgressEvent(
                    stage="source_complete",
                    current=processed_files,
                    total=total_files,
                    source=discovery.source,
                ),
            )
        except Exception as exc:
            summary.errors += 1
            summary.diagnostics += (f"{discovery.source}: {exc}",)
            origin = (
                str(discovery.artifacts[0])
                if discovery.artifacts
                else str(discovery.roots[0]) if discovery.roots else discovery.source
            )
            repository.record_import_error(
                discovery.source,
                origin,
                None,
                "adapter",
                str(exc),
            )
            processed_files += len(discovery.artifacts)
            _emit(
                progress,
                ProgressEvent(
                    stage="source_failed",
                    current=processed_files,
                    total=total_files,
                    source=discovery.source,
                ),
            )

    _emit(
        progress,
        ProgressEvent(
            stage="complete",
            current=processed_files,
            total=total_files,
        ),
    )
    return summary


def collect_sources(
    repository: Repository,
    *,
    codex_home: Path | None = None,
    headroom_home: Path | None = None,
    full_rescan: bool = False,
    progress: ProgressCallback | None = None,
) -> ImportSummary:
    enabled: set[str] = set()
    if codex_home is not None:
        enabled.add("codex")
    if headroom_home is not None:
        enabled.add("headroom")

    config = AgentScopeConfig.from_env(
        codex_home=codex_home,
        headroom_home=headroom_home,
        enabled_sources=enabled,
    )
    return collect_registered_sources(
        repository,
        config,
        full_rescan=full_rescan,
        progress=progress,
    )
