import os
import sys
from pathlib import Path

import pytest

from agentscope.codex_account.app_server import CodexAppServerClient, CodexAppServerError


FIXTURE = Path(__file__).parents[1] / "fixtures" / "codex_app_server" / "fake_app_server.py"


def _fake_command() -> list[str]:
    return [sys.executable, str(FIXTURE)]


def test_client_initializes_and_reads_only_allowed_account_methods():
    with CodexAppServerClient(command=_fake_command(), timeout_seconds=1.0) as client:
        account = client.account_read()
        limits = client.account_rate_limits_read()
        usage = client.account_usage_read("01a016bf-d4e0-7383-9c3d-872eeeb5c5fa")

    assert account["account"]["type"] == "chatgpt"
    assert account["account"]["planType"] == "pro"
    assert limits["rateLimits"]["credits"]["balance"] == "18.42"
    assert usage["threadUsage"]["threadId"].startswith("01a016bf")


def test_client_rejects_write_method_before_it_reaches_subprocess():
    with CodexAppServerClient(command=_fake_command(), timeout_seconds=1.0) as client:
        with pytest.raises(CodexAppServerError, match="method_not_allowed"):
            client._request("account/logout", {})


def test_client_times_out_with_sanitized_error(monkeypatch):
    monkeypatch.setenv("FAKE_CODEX_HANG", "1")
    with pytest.raises(CodexAppServerError) as exc:
        with CodexAppServerClient(command=_fake_command(), timeout_seconds=0.05) as client:
            client.account_read()
    assert exc.value.code == "timeout"
    assert "access_token" not in str(exc.value).lower()
    monkeypatch.delenv("FAKE_CODEX_HANG", raising=False)
