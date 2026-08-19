from agentscope.config import AgentScopeConfig
from agentscope.domain.models import NormalizedSession
from agentscope.importer import ProgressEvent, collect_registered_sources
from agentscope.sources.base import (
    CollectRequest,
    DiscoveryContext,
    SourceCapabilities,
    SourceCollectionSummary,
    SourceDiscovery,
)
from agentscope.sources.registry import SourceRegistry
from agentscope.storage.database import Database
from agentscope.storage.repository import Repository


class SuccessfulAdapter:
    source_name = "success"

    def discover(self, context: DiscoveryContext) -> SourceDiscovery:
        return SourceDiscovery(
            source=self.source_name,
            detected=True,
            artifacts=(context.user_home / "success.jsonl",),
        )

    def capabilities(self) -> SourceCapabilities:
        return SourceCapabilities(sessions=True)

    def collect(self, request: CollectRequest) -> SourceCollectionSummary:
        request.repository.upsert_session(
            NormalizedSession(
                external_session_id="fake-session",
                source=self.source_name,
                started_at="2026-08-18T10:00:00Z",
            )
        )
        return SourceCollectionSummary(
            files_seen=1,
            files_imported=1,
            sessions_imported=1,
        )


class FailingAdapter:
    source_name = "failure"

    def discover(self, context: DiscoveryContext) -> SourceDiscovery:
        return SourceDiscovery(
            source=self.source_name,
            detected=True,
            artifacts=(context.user_home / "failure.jsonl",),
        )

    def capabilities(self) -> SourceCapabilities:
        return SourceCapabilities(sessions=True)

    def collect(self, request: CollectRequest) -> SourceCollectionSummary:
        raise RuntimeError("provider exploded")


def make_repo_and_config(tmp_path):
    db = Database(tmp_path / "agentscope.db")
    db.initialize()
    repo = Repository(db)
    config = AgentScopeConfig.from_env(base_dir=tmp_path)
    return db, repo, config


def test_registered_collection_isolates_adapter_failures(tmp_path):
    db, repo, config = make_repo_and_config(tmp_path)
    registry = SourceRegistry([SuccessfulAdapter(), FailingAdapter()])
    events: list[ProgressEvent] = []

    summary = collect_registered_sources(
        repo,
        config,
        registry=registry,
        progress=events.append,
    )

    assert summary.sessions_imported == 1
    assert summary.files_imported == 1
    assert summary.errors == 1
    with db.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM import_errors").fetchone()[0] == 1

    stages = [event.stage for event in events]
    assert stages[0] == "discovering"
    assert "source_detected" in stages
    assert "source_complete" in stages
    assert "source_failed" in stages
    assert stages[-1] == "complete"


def test_registered_collection_respects_enabled_sources(tmp_path):
    db, repo, config = make_repo_and_config(tmp_path)
    config = AgentScopeConfig(
        codex_home=config.codex_home,
        headroom_home=config.headroom_home,
        database_path=config.database_path,
        reports_path=config.reports_path,
        safe_mode=config.safe_mode,
        timezone=config.timezone,
        enabled_sources=frozenset({"success"}),
    )
    registry = SourceRegistry([SuccessfulAdapter(), FailingAdapter()])

    summary = collect_registered_sources(repo, config, registry=registry)

    assert summary.errors == 0
    assert summary.sessions_imported == 1
    with db.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0] == 1
