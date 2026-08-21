from __future__ import annotations

from pathlib import Path

from agentscope.codex_account.collector import sync_account_usage
from agentscope.codex_account.storage import CodexAccountStorage
from agentscope.storage.database import Database
from agentscope.storage.repository import Repository


class FakeClient:
    def account_read(self):
        return {
            "account": {
                "type": "chatgpt",
                "email": "person@example.com",
                "planType": "pro",
                "access_token": "SECRET_ACCESS_TOKEN",
            },
            "requiresOpenaiAuth": False,
        }

    def account_rate_limits_read(self):
        return {
            "rateLimits": {
                "limitId": "codex",
                "limitName": "Codex",
                "planType": "pro",
                "primary": {
                    "usedPercent": 63,
                    "windowDurationMins": 300,
                    "resetsAt": 1787241600,
                },
                "secondary": {
                    "usedPercent": 42,
                    "windowDurationMins": 10080,
                    "resetsAt": 1787846400,
                },
                "credits": {
                    "hasCredits": True,
                    "balance": "18.42",
                    "unlimited": False,
                    "cookie": "SECRET_COOKIE",
                },
                "spendControlReached": False,
                "individualLimit": {
                    "limit": "50.00",
                    "used": "7.25",
                    "remainingPercent": 85,
                    "resetsAt": 1788307200,
                },
            }
        }


def _repo(tmp_path: Path) -> Repository:
    db = Database(tmp_path / "agentscope.db")
    db.initialize()
    return Repository(db)


def test_sync_maps_only_allowlisted_account_fields_and_drops_identity(tmp_path):
    repo = _repo(tmp_path)
    result = sync_account_usage(repo, client=FakeClient())

    assert result.status == "complete"
    assert result.plan_type == "pro"
    assert result.credits_balance == "18.42"

    with repo.database.connect() as conn:
        row = conn.execute(
            "SELECT * FROM codex_account_usage_snapshots ORDER BY id DESC LIMIT 1"
        ).fetchone()
        serialized = " ".join("" if value is None else str(value) for value in row)

    assert row["plan_type"] == "pro"
    assert row["credits_balance"] == "18.42"
    assert row["primary_used_percent"] == 63
    assert "person@example.com" not in serialized
    assert "secret_access_token" not in serialized.lower()
    assert "secret_cookie" not in serialized.lower()


def test_missing_optional_account_values_remain_null(tmp_path):
    class MissingClient:
        def account_read(self):
            return {"account": {"type": "chatgpt", "planType": "pro"}}

        def account_rate_limits_read(self):
            return {"rateLimits": {"planType": "pro"}}

    repo = _repo(tmp_path)
    result = sync_account_usage(repo, client=MissingClient())
    assert result.status == "complete"

    latest = CodexAccountStorage(repo.database).latest_account_snapshot()
    assert latest is not None
    assert latest.primary_used_percent is None
    assert latest.credits_has_credits is None
    assert latest.credits_balance is None
    assert latest.spend_control_reached is None


def test_failed_sync_keeps_last_known_good_snapshot(tmp_path):
    repo = _repo(tmp_path)
    first = sync_account_usage(repo, client=FakeClient())
    assert first.status == "complete"

    class FailingClient:
        def account_read(self):
            raise RuntimeError("token=SECRET_SHOULD_NOT_ESCAPE")

        def account_rate_limits_read(self):
            raise AssertionError("not reached")

    failed = sync_account_usage(repo, client=FailingClient())
    assert failed.status == "failed"
    assert failed.error_code == "account_sync_failed"

    latest = CodexAccountStorage(repo.database).latest_account_snapshot()
    assert latest is not None
    assert latest.plan_type == "pro"
    assert latest.credits_balance == "18.42"
