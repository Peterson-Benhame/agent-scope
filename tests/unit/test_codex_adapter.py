import json
import shutil
from pathlib import Path

from agentscope.domain.models import NormalizedMachine, NormalizedUser
from agentscope.sources.base import CollectRequest, DiscoveryContext
from agentscope.sources.codex import CodexAdapter
from agentscope.storage.database import Database
from agentscope.storage.repository import Repository


FIXTURE = Path("tests/fixtures/codex/rollout.jsonl")


def make_repo(tmp_path):
    db = Database(tmp_path / "agentscope.db")
    db.initialize()
    return db, Repository(db)


def make_codex_home(tmp_path):
    home = tmp_path / ".codex"
    target = home / "sessions" / "2026" / "08" / "18"
    target.mkdir(parents=True)
    rollout = target / "rollout.jsonl"
    shutil.copy(FIXTURE, rollout)
    return home, rollout


def test_codex_adapter_discovers_rollout_files_from_override(tmp_path):
    home, rollout = make_codex_home(tmp_path)
    adapter = CodexAdapter()

    discovery = adapter.discover(
        DiscoveryContext(user_home=tmp_path, overrides={"codex": home})
    )

    assert discovery.source == "codex"
    assert discovery.detected is True
    assert discovery.roots == (home,)
    assert discovery.artifacts == (rollout,)
    assert discovery.format_version == "rollout-jsonl"


def test_codex_adapter_declares_only_supported_capabilities():
    capabilities = CodexAdapter().capabilities()

    assert capabilities.sessions is True
    assert capabilities.messages is True
    assert capabilities.tokens is True
    assert capabilities.tools is True
    assert capabilities.agents is True
    assert capabilities.skills is True
    assert capabilities.cache is True
    assert capabilities.costs is False
    assert capabilities.optimizations is False
    assert capabilities.user_identity is False


def test_codex_adapter_collect_is_idempotent(tmp_path):
    db, repo = make_repo(tmp_path)
    home, _ = make_codex_home(tmp_path)
    adapter = CodexAdapter()
    discovery = adapter.discover(
        DiscoveryContext(user_home=tmp_path, overrides={"codex": home})
    )

    first = adapter.collect(CollectRequest(repository=repo, discovery=discovery))
    second = adapter.collect(CollectRequest(repository=repo, discovery=discovery))

    assert first.files_seen == 1
    assert first.files_imported == 1
    assert first.sessions_imported == 1
    assert second.files_seen == 1
    assert second.files_skipped == 1
    with db.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0] == 3
        assert conn.execute("SELECT COUNT(*) FROM token_usage").fetchone()[0] == 1


def test_codex_adapter_associates_explicit_local_identity(tmp_path):
    db, repo = make_repo(tmp_path)
    home, _ = make_codex_home(tmp_path)
    adapter = CodexAdapter()
    discovery = adapter.discover(
        DiscoveryContext(user_home=tmp_path, overrides={"codex": home})
    )
    user = NormalizedUser(stable_key="local-user:test", display_name="Dev A")
    machine = NormalizedMachine(
        stable_key="local-machine:test",
        display_name="Notebook A",
    )

    adapter.collect(
        CollectRequest(
            repository=repo,
            discovery=discovery,
            user=user,
            machine=machine,
        )
    )

    with db.connect() as conn:
        row = conn.execute(
            """
            SELECT u.display_name AS user_name, m.display_name AS machine_name
            FROM sessions s
            JOIN users u ON u.id=s.user_id
            JOIN machines m ON m.id=s.machine_id
            WHERE s.external_session_id='session-1'
            """
        ).fetchone()
    assert row["user_name"] == "Dev A"
    assert row["machine_name"] == "Notebook A"


def test_codex_adapter_persists_product_client_and_billing_context(tmp_path):
    db, repo = make_repo(tmp_path)
    home, _ = make_codex_home(tmp_path)
    adapter = CodexAdapter()
    discovery = adapter.discover(
        DiscoveryContext(user_home=tmp_path, overrides={"codex": home})
    )

    result = adapter.collect(CollectRequest(repository=repo, discovery=discovery))

    assert result.errors == 0
    with db.connect() as conn:
        row = conn.execute(
            """
            SELECT s.provider AS model_provider,
                   uc.provider, uc.product, uc.client, uc.billing_mode,
                   uc.client_confidence, uc.billing_confidence, uc.evidence_json
            FROM sessions s
            JOIN session_usage_context uc ON uc.session_id=s.id
            WHERE s.external_session_id='session-1'
            """
        ).fetchone()

    assert row["model_provider"] == "headroom"
    assert row["provider"] == "openai"
    assert row["product"] == "codex"
    assert row["client"] == "vscode"
    assert row["billing_mode"] == "unknown"
    assert row["client_confidence"] == "explicit"
    assert row["billing_confidence"] == "unknown"
    assert json.loads(row["evidence_json"]) == [
        "originator=codex_vscode",
        "source=vscode",
    ]


def test_codex_usage_context_is_idempotent_on_full_rescan(tmp_path):
    db, repo = make_repo(tmp_path)
    home, _ = make_codex_home(tmp_path)
    adapter = CodexAdapter()
    discovery = adapter.discover(
        DiscoveryContext(user_home=tmp_path, overrides={"codex": home})
    )
    request = CollectRequest(
        repository=repo,
        discovery=discovery,
        full_rescan=True,
    )

    adapter.collect(request)
    adapter.collect(request)

    with db.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM session_usage_context").fetchone()[0] == 1
