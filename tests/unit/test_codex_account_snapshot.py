from __future__ import annotations

from agentscope.analytics.filters import AnalyticsFilter
from agentscope.codex_account.app_server import CodexAppServerClient
from agentscope.codex_account.models import CodexAccountSnapshot
from agentscope.codex_account.storage import CodexAccountStorage
from agentscope.extension.snapshot import build_extension_snapshot
from agentscope.storage.database import Database
from agentscope.storage.repository import Repository


def test_extension_snapshot_projects_latest_stored_codex_account_offline(tmp_path, monkeypatch):
    db = Database(tmp_path / "agentscope.db")
    db.initialize()
    repo = Repository(db)
    CodexAccountStorage(db).insert_account_snapshot(
        CodexAccountSnapshot(
            captured_at="2026-08-20T16:00:00+00:00",
            auth_mode="chatgpt",
            plan_type="pro",
            primary_used_percent=63,
            primary_resets_at=1787241600,
            secondary_used_percent=42,
            secondary_resets_at=1787846400,
            credits_has_credits=True,
            credits_balance="18.42",
            credits_unlimited=False,
            spend_control_reached=False,
        )
    )

    def fail_if_started(*args, **kwargs):
        raise AssertionError("snapshot rendering must not instantiate Codex app-server")

    monkeypatch.setattr(CodexAppServerClient, "__init__", fail_if_started)

    snapshot = build_extension_snapshot(
        repo,
        AnalyticsFilter(),
        period="7d",
        database_path=db.path,
    )

    assert snapshot["codex_account"] == {
        "available": True,
        "captured_at": "2026-08-20T16:00:00+00:00",
        "plan_type": "pro",
        "primary_used_percent": 63,
        "primary_resets_at": 1787241600,
        "secondary_used_percent": 42,
        "secondary_resets_at": 1787846400,
        "credits": {
            "has_credits": True,
            "balance": "18.42",
            "unlimited": False,
        },
        "spend_control_reached": False,
    }


def test_extension_snapshot_marks_codex_account_unavailable_without_stored_snapshot(tmp_path):
    db = Database(tmp_path / "agentscope.db")
    db.initialize()
    repo = Repository(db)

    snapshot = build_extension_snapshot(
        repo,
        AnalyticsFilter(),
        period="7d",
        database_path=db.path,
    )

    assert snapshot["codex_account"] == {"available": False}
