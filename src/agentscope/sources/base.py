from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Protocol

from agentscope.domain.models import NormalizedMachine, NormalizedUser


ProgressCallback = Callable[[Any], None]


@dataclass(frozen=True, slots=True)
class SourceCapabilities:
    sessions: bool = False
    messages: bool = False
    tokens: bool = False
    cache: bool = False
    costs: bool = False
    tools: bool = False
    agents: bool = False
    skills: bool = False
    optimizations: bool = False
    user_identity: bool = False


@dataclass(frozen=True, slots=True)
class SourceDiscovery:
    source: str
    detected: bool
    roots: tuple[Path, ...] = ()
    format_version: str | None = None
    artifacts: tuple[Path, ...] = ()
    diagnostic: str | None = None


@dataclass(frozen=True, slots=True)
class DiscoveryContext:
    user_home: Path
    overrides: dict[str, Path] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class CollectRequest:
    repository: Any
    discovery: SourceDiscovery
    full_rescan: bool = False
    progress: ProgressCallback | None = None
    user: NormalizedUser | None = None
    machine: NormalizedMachine | None = None


@dataclass(slots=True)
class SourceCollectionSummary:
    files_seen: int = 0
    files_imported: int = 0
    files_skipped: int = 0
    sessions_imported: int = 0
    optimizations_imported: int = 0
    errors: int = 0

    def __add__(self, other: "SourceCollectionSummary") -> "SourceCollectionSummary":
        return SourceCollectionSummary(
            files_seen=self.files_seen + other.files_seen,
            files_imported=self.files_imported + other.files_imported,
            files_skipped=self.files_skipped + other.files_skipped,
            sessions_imported=self.sessions_imported + other.sessions_imported,
            optimizations_imported=(
                self.optimizations_imported + other.optimizations_imported
            ),
            errors=self.errors + other.errors,
        )


class SourceAdapter(Protocol):
    source_name: str

    def discover(self, context: DiscoveryContext) -> SourceDiscovery:
        ...

    def capabilities(self) -> SourceCapabilities:
        ...

    def collect(self, request: CollectRequest) -> SourceCollectionSummary:
        ...
