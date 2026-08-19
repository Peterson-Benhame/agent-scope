from agentscope.sources.base import (
    CollectRequest,
    DiscoveryContext,
    SourceAdapter,
    SourceCapabilities,
    SourceCollectionSummary,
    SourceDiscovery,
)


def test_source_capabilities_default_to_unavailable():
    capabilities = SourceCapabilities()

    assert capabilities.sessions is False
    assert capabilities.messages is False
    assert capabilities.tokens is False
    assert capabilities.cache is False
    assert capabilities.costs is False
    assert capabilities.tools is False
    assert capabilities.agents is False
    assert capabilities.skills is False
    assert capabilities.optimizations is False
    assert capabilities.user_identity is False


def test_source_discovery_preserves_roots_artifacts_and_diagnostic(tmp_path):
    root = tmp_path / ".provider"
    artifact = root / "history.jsonl"
    discovery = SourceDiscovery(
        source="provider",
        detected=True,
        roots=(root,),
        format_version="1",
        artifacts=(artifact,),
        diagnostic=None,
    )

    assert discovery.source == "provider"
    assert discovery.detected is True
    assert discovery.roots == (root,)
    assert discovery.artifacts == (artifact,)
    assert discovery.format_version == "1"


def test_discovery_context_and_collect_request_are_provider_neutral(tmp_path):
    user_home = tmp_path / "user"
    override = tmp_path / "custom"
    context = DiscoveryContext(user_home=user_home, overrides={"provider": override})
    discovery = SourceDiscovery(source="provider", detected=False)
    request = CollectRequest(
        repository=object(),
        discovery=discovery,
        full_rescan=True,
        progress=None,
    )

    assert context.user_home == user_home
    assert context.overrides["provider"] == override
    assert request.discovery is discovery
    assert request.full_rescan is True


def test_source_collection_summaries_add_field_by_field():
    first = SourceCollectionSummary(
        files_seen=2,
        files_imported=1,
        files_skipped=1,
        sessions_imported=1,
    )
    second = SourceCollectionSummary(
        files_seen=3,
        files_imported=2,
        optimizations_imported=4,
        errors=1,
    )

    combined = first + second

    assert combined.files_seen == 5
    assert combined.files_imported == 3
    assert combined.files_skipped == 1
    assert combined.sessions_imported == 1
    assert combined.optimizations_imported == 4
    assert combined.errors == 1


def test_source_adapter_protocol_exposes_required_methods():
    assert SourceAdapter.__name__ == "SourceAdapter"
    for name in ("discover", "capabilities", "collect"):
        assert name in SourceAdapter.__dict__
