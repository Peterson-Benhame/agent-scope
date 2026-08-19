from __future__ import annotations

from collections.abc import Iterable

from agentscope.sources.base import DiscoveryContext, SourceAdapter, SourceDiscovery


class SourceRegistry:
    def __init__(self, adapters: Iterable[SourceAdapter]):
        self._adapters = tuple(adapters)
        names = [adapter.source_name for adapter in self._adapters]
        if len(names) != len(set(names)):
            raise ValueError("Source adapter names must be unique")

    @property
    def adapters(self) -> tuple[SourceAdapter, ...]:
        return self._adapters

    @property
    def source_names(self) -> tuple[str, ...]:
        return tuple(adapter.source_name for adapter in self._adapters)

    def discover(
        self,
        context: DiscoveryContext,
        enabled_sources: set[str] | frozenset[str] | None = None,
    ) -> list[SourceDiscovery]:
        registered = set(self.source_names)
        if enabled_sources is not None:
            unknown = sorted(set(enabled_sources) - registered)
            if unknown:
                raise ValueError(
                    "Unknown configured source(s): " + ", ".join(unknown)
                )

        discoveries: list[SourceDiscovery] = []
        for adapter in self._adapters:
            if enabled_sources is not None and adapter.source_name not in enabled_sources:
                continue
            discoveries.append(adapter.discover(context))
        return discoveries

    def adapter_for(self, source: str) -> SourceAdapter:
        for adapter in self._adapters:
            if adapter.source_name == source:
                return adapter
        raise ValueError(f"Unknown source: {source}")
