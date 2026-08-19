from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Protocol


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


class SourceAdapter(Protocol):
    source_name: str

    def discover(self, context: DiscoveryContext) -> SourceDiscovery:
        ...

    def capabilities(self) -> SourceCapabilities:
        ...

    def collect(self, request: CollectRequest) -> Any:
        ...
