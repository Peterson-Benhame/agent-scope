from pathlib import Path

import pytest

from agentscope.sources.base import DiscoveryContext, SourceCapabilities, SourceDiscovery
from agentscope.sources.registry import SourceRegistry


class FakeAdapter:
    def __init__(self, name: str, calls: list[str]):
        self.source_name = name
        self.calls = calls

    def discover(self, context: DiscoveryContext) -> SourceDiscovery:
        self.calls.append(self.source_name)
        return SourceDiscovery(
            source=self.source_name,
            detected=True,
            roots=(context.user_home / f".{self.source_name}",),
        )

    def capabilities(self) -> SourceCapabilities:
        return SourceCapabilities(sessions=True)

    def collect(self, request):
        raise AssertionError("collect is not part of this discovery test")


def test_registry_preserves_adapter_registration_order(tmp_path):
    calls: list[str] = []
    registry = SourceRegistry([
        FakeAdapter("codex", calls),
        FakeAdapter("headroom", calls),
    ])

    discoveries = registry.discover(DiscoveryContext(user_home=tmp_path))

    assert [item.source for item in discoveries] == ["codex", "headroom"]
    assert calls == ["codex", "headroom"]


def test_disabled_adapter_is_not_discovered(tmp_path):
    calls: list[str] = []
    registry = SourceRegistry([
        FakeAdapter("codex", calls),
        FakeAdapter("headroom", calls),
    ])

    discoveries = registry.discover(
        DiscoveryContext(user_home=tmp_path),
        enabled_sources={"codex"},
    )

    assert [item.source for item in discoveries] == ["codex"]
    assert calls == ["codex"]


def test_unknown_enabled_source_raises_clear_error(tmp_path):
    registry = SourceRegistry([FakeAdapter("codex", [])])

    with pytest.raises(ValueError, match="unknown-source"):
        registry.discover(
            DiscoveryContext(user_home=tmp_path),
            enabled_sources={"codex", "unknown-source"},
        )
