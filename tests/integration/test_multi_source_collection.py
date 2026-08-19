import shutil
from pathlib import Path

from agentscope.config import AgentScopeConfig
from agentscope.importer import collect_registered_sources
from agentscope.sources.base import (
    DiscoveryContext,
    SourceCapabilities,
    SourceCollectionSummary,
    SourceDiscovery,
)
from agentscope.sources.claude_code import ClaudeCodeAdapter
from agentscope.sources.codex import CodexAdapter
from agentscope.sources.github_copilot import GitHubCopilotAdapter
from agentscope.sources.headroom import HeadroomAdapter
from agentscope.sources.registry import SourceRegistry
from agentscope.storage.database import Database
from agentscope.storage.repository import Repository


CODEX_FIXTURE = Path("tests/fixtures/codex/rollout.jsonl")
HEADROOM_FIXTURE = Path("tests/fixtures/headroom")
CLAUDE_FIXTURE = Path("tests/fixtures/claude_code/session.jsonl")
COPILOT_FIXTURE = Path("tests/fixtures/github_copilot/events.jsonl")


class UnsupportedAdapter:
    source_name = "unsupported_demo"

    def discover(self, context: DiscoveryContext) -> SourceDiscovery:
        return SourceDiscovery(
            source=self.source_name,
            detected=False,
            roots=(context.user_home / ".unsupported-demo",),
            diagnostic="unsupported_demo unsupported format version: 99",
        )

    def capabilities(self) -> SourceCapabilities:
        return SourceCapabilities()

    def collect(self, request) -> SourceCollectionSummary:
        raise AssertionError("unsupported adapter must never collect")


class BrokenAdapter:
    source_name = "broken_demo"

    def discover(self, context: DiscoveryContext) -> SourceDiscovery:
        artifact = context.user_home / "broken-demo.jsonl"
        artifact.write_text("{}\n", encoding="utf-8")
        return SourceDiscovery(
            source=self.source_name,
            detected=True,
            roots=(context.user_home,),
            format_version="v1",
            artifacts=(artifact,),
        )

    def capabilities(self) -> SourceCapabilities:
        return SourceCapabilities(sessions=True)

    def collect(self, request) -> SourceCollectionSummary:
        raise RuntimeError("synthetic adapter failure")


def arrange_sources(tmp_path):
    user_home = tmp_path / "user"

    codex_home = user_home / ".codex"
    codex_session = codex_home / "sessions" / "2026" / "08" / "18"
    codex_session.mkdir(parents=True)
    shutil.copy(CODEX_FIXTURE, codex_session / "rollout.jsonl")

    headroom_home = user_home / ".headroom"
    shutil.copytree(HEADROOM_FIXTURE, headroom_home)

    claude_home = user_home / ".claude"
    claude_project = claude_home / "projects" / "-work-claude-demo"
    claude_project.mkdir(parents=True)
    shutil.copy(CLAUDE_FIXTURE, claude_project / "claude-session-1.jsonl")

    copilot_home = user_home / ".copilot"
    copilot_session = copilot_home / "session-state" / "session-copilot-1"
    copilot_session.mkdir(parents=True)
    shutil.copy(COPILOT_FIXTURE, copilot_session / "events.jsonl")

    config = AgentScopeConfig.from_env(
        base_dir=tmp_path,
        codex_home=codex_home,
        headroom_home=headroom_home,
        claude_home=claude_home,
        copilot_home=copilot_home,
        kimi_home=user_home / ".kimi-code",
        gemini_home=user_home / ".gemini",
        database_path=tmp_path / "agentscope.db",
        enabled_sources={
            "codex",
            "headroom",
            "claude_code",
            "github_copilot",
            "unsupported_demo",
            "broken_demo",
        },
    )
    return config


def registry():
    return SourceRegistry(
        [
            CodexAdapter(),
            HeadroomAdapter(),
            ClaudeCodeAdapter(),
            GitHubCopilotAdapter(),
            UnsupportedAdapter(),
            BrokenAdapter(),
        ]
    )


def test_multi_provider_collection_is_isolated_idempotent_and_reports_diagnostics(tmp_path):
    config = arrange_sources(tmp_path)
    db = Database(config.database_path)
    db.initialize()
    repo = Repository(db)

    first = collect_registered_sources(repo, config, registry=registry())

    assert first.errors == 1
    assert "unsupported_demo unsupported format version: 99" in first.diagnostics
    with db.connect() as conn:
        sources = {
            row["name"]: row["sessions"]
            for row in conn.execute(
                """
                SELECT src.name, COUNT(s.id) AS sessions
                FROM sources src
                LEFT JOIN sessions s ON s.source_id=src.id
                GROUP BY src.name
                """
            ).fetchall()
        }
        assert sources["codex"] == 1
        assert sources["claude_code"] == 1
        assert sources["github_copilot"] == 1
        assert conn.execute("SELECT COUNT(*) FROM token_usage").fetchone()[0] == 3
        assert conn.execute("SELECT COUNT(*) FROM optimizations").fetchone()[0] > 0
        assert conn.execute(
            "SELECT COUNT(*) FROM import_errors WHERE source='broken_demo'"
        ).fetchone()[0] == 1
        session_count = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
        token_count = conn.execute("SELECT COUNT(*) FROM token_usage").fetchone()[0]
        optimization_count = conn.execute("SELECT COUNT(*) FROM optimizations").fetchone()[0]

    second = collect_registered_sources(repo, config, registry=registry())

    assert second.errors == 1
    assert "unsupported_demo unsupported format version: 99" in second.diagnostics
    with db.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0] == session_count
        assert conn.execute("SELECT COUNT(*) FROM token_usage").fetchone()[0] == token_count
        assert conn.execute("SELECT COUNT(*) FROM optimizations").fetchone()[0] == optimization_count
