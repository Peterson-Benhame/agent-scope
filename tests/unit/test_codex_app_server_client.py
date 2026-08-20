import os
import sys
from pathlib import Path

import pytest

from agentscope.codex_account.app_server import (
    CodexAppServerClient,
    CodexAppServerError,
    discover_codex_binary,
)


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


def test_client_classifies_usage_profile_rpc_error_without_leaking_message(monkeypatch):
    monkeypatch.setenv("FAKE_CODEX_USAGE_ERROR", "profile")
    with pytest.raises(CodexAppServerError) as exc:
        with CodexAppServerClient(command=_fake_command(), timeout_seconds=1.0) as client:
            client.account_usage_read()

    assert exc.value.code == "token_usage_profile_failed"
    assert exc.value.rpc_code == -32603
    assert "SECRET_SHOULD_NOT_LEAK" not in str(exc.value)
    assert "Bearer" not in str(exc.value)


def test_client_classifies_thread_usage_rpc_error_without_leaking_message(monkeypatch):
    monkeypatch.setenv("FAKE_CODEX_USAGE_ERROR", "thread")
    with pytest.raises(CodexAppServerError) as exc:
        with CodexAppServerClient(command=_fake_command(), timeout_seconds=1.0) as client:
            client.account_usage_read("01a016bf-d4e0-7383-9c3d-872eeeb5c5fa")

    assert exc.value.code == "thread_usage_backend_failed"
    assert exc.value.rpc_code == -32603
    assert "SECRET_SHOULD_NOT_LEAK" not in str(exc.value)
    assert "Bearer" not in str(exc.value)


def test_discovers_vscode_bundled_codex_on_windows(tmp_path, monkeypatch):
    monkeypatch.setattr("shutil.which", lambda _: None)
    extension = (
        tmp_path
        / ".vscode"
        / "extensions"
        / "openai.chatgpt-26.803.61601-win32-x64"
        / "bin"
        / "windows-x86_64"
        / "codex.exe"
    )
    extension.parent.mkdir(parents=True)
    extension.write_bytes(b"")

    resolved = discover_codex_binary(
        "codex",
        home=tmp_path,
        platform="win32",
    )

    assert resolved == str(extension)


def test_discovers_newest_vscode_bundled_codex_on_windows(tmp_path, monkeypatch):
    monkeypatch.setattr("shutil.which", lambda _: None)
    older = (
        tmp_path
        / ".vscode"
        / "extensions"
        / "openai.chatgpt-26.700.10000-win32-x64"
        / "bin"
        / "windows-x86_64"
        / "codex.exe"
    )
    newer = (
        tmp_path
        / ".vscode"
        / "extensions"
        / "openai.chatgpt-26.803.61601-win32-x64"
        / "bin"
        / "windows-x86_64"
        / "codex.exe"
    )
    for candidate in (older, newer):
        candidate.parent.mkdir(parents=True)
        candidate.write_bytes(b"")
    os.utime(older, (1, 1))
    os.utime(newer, (2, 2))

    resolved = discover_codex_binary(
        "codex",
        home=tmp_path,
        platform="win32",
    )

    assert resolved == str(newer)


def test_explicit_codex_binary_path_is_authoritative(tmp_path):
    explicit = tmp_path / "custom-codex.exe"
    explicit.write_bytes(b"")

    resolved = discover_codex_binary(
        str(explicit),
        home=tmp_path,
        platform="win32",
    )

    assert resolved == str(explicit)
