from __future__ import annotations

import json
import queue
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Any


_ALLOWED_REQUESTS = {
    "initialize",
    "account/read",
    "account/rateLimits/read",
    "account/usage/read",
}
_ALLOWED_NOTIFICATIONS = {"initialized"}


def discover_codex_binary(
    codex_bin: str = "codex",
    *,
    home: Path | None = None,
    platform: str | None = None,
) -> str | None:
    """Resolve Codex without reading any authentication material."""
    direct_path = Path(codex_bin).expanduser()
    if direct_path.is_file():
        return str(direct_path)

    on_path = shutil.which(codex_bin)
    if on_path:
        return on_path

    current_platform = platform or sys.platform
    if current_platform != "win32" or codex_bin != "codex":
        return None

    user_home = home or Path.home()
    candidates: list[Path] = []
    for extensions_root in (
        user_home / ".vscode" / "extensions",
        user_home / ".vscode-insiders" / "extensions",
    ):
        if not extensions_root.is_dir():
            continue
        candidates.extend(
            candidate
            for candidate in extensions_root.glob(
                "openai.chatgpt-*/bin/windows-*/codex.exe"
            )
            if candidate.is_file()
        )

    if not candidates:
        return None

    return str(max(candidates, key=lambda path: path.stat().st_mtime))


def detect_codex_thread_usage_support(
    codex_bin: str = "codex",
    *,
    timeout_seconds: float = 15.0,
) -> bool | None:
    """Inspect the installed app-server schema for `account/usage/read(threadId)`.

    Returns True when the generated schema explicitly exposes `threadId`, False
    when account usage exists but the thread parameter is absent, and None when
    capability detection itself cannot be completed.
    """
    resolved = discover_codex_binary(codex_bin)
    if resolved is None:
        return None
    try:
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)
            completed = subprocess.run(
                [
                    resolved,
                    "app-server",
                    "generate-json-schema",
                    "--out",
                    str(output),
                ],
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                check=False,
            )
            if completed.returncode != 0:
                return None
            found_account_usage = False
            found_thread_id = False
            for schema_file in output.rglob("*.json"):
                text = schema_file.read_text(encoding="utf-8", errors="ignore")
                if "account/usage/read" in text:
                    found_account_usage = True
                is_usage_params_schema = (
                    schema_file.stem == "GetAccountTokenUsageParams"
                    or "GetAccountTokenUsageParams" in text
                )
                if is_usage_params_schema and "threadId" in text:
                    found_thread_id = True
            if found_thread_id:
                return True
            if found_account_usage:
                return False
            return None
    except (OSError, subprocess.SubprocessError):
        return None


class CodexAppServerError(RuntimeError):
    def __init__(
        self,
        code: str,
        message: str | None = None,
        *,
        rpc_code: int | None = None,
    ) -> None:
        self.code = code
        self.rpc_code = rpc_code
        super().__init__(message or code)


def _safe_remote_error_code(
    method: str,
    params: dict[str, object] | None,
    error: object,
) -> tuple[str, int | None]:
    error_obj = error if isinstance(error, dict) else {}
    rpc_code = error_obj.get("code")
    rpc_code_value = rpc_code if isinstance(rpc_code, int) else None
    message = error_obj.get("message")
    message_value = message.lower() if isinstance(message, str) else ""

    if method == "account/usage/read":
        if "token usage profile" in message_value:
            return "token_usage_profile_failed", rpc_code_value
        if "thread usage" in message_value:
            return "thread_usage_backend_failed", rpc_code_value
        if params and params.get("threadId") is not None:
            return "thread_usage_remote_error", rpc_code_value
        return "token_usage_remote_error", rpc_code_value

    return "remote_error", rpc_code_value


class CodexAppServerClient:
    def __init__(
        self,
        *,
        codex_bin: str = "codex",
        timeout_seconds: float = 10.0,
        command: list[str] | None = None,
    ) -> None:
        self.codex_bin = codex_bin
        self.timeout_seconds = timeout_seconds
        self.command = list(command) if command is not None else None
        self._process: subprocess.Popen[str] | None = None
        self._messages: queue.Queue[dict[str, Any]] = queue.Queue()
        self._reader: threading.Thread | None = None
        self._next_id = 1

    def __enter__(self) -> "CodexAppServerClient":
        try:
            self.start()
        except Exception:
            self.close()
            raise
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.close()

    def start(self) -> None:
        if self._process is not None:
            return
        if self.command is not None:
            command = self.command
        else:
            resolved = discover_codex_binary(self.codex_bin)
            if resolved is None:
                raise CodexAppServerError("codex_not_found", "codex_not_found")
            command = [resolved, "app-server", "--stdio"]
        try:
            self._process = subprocess.Popen(
                command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                encoding="utf-8",
                bufsize=1,
                shell=False,
            )
        except FileNotFoundError as exc:
            raise CodexAppServerError("codex_not_found", "codex_not_found") from exc
        except OSError as exc:
            raise CodexAppServerError(
                "process_start_failed",
                "process_start_failed",
            ) from exc

        self._reader = threading.Thread(target=self._read_stdout, daemon=True)
        self._reader.start()
        self._request(
            "initialize",
            {
                "clientInfo": {
                    "name": "agentscope",
                    "title": "AgentScope",
                    "version": "0.1.0",
                }
            },
        )
        self._notify("initialized", {})

    def close(self) -> None:
        process = self._process
        self._process = None
        if process is None:
            return
        if process.stdin is not None:
            try:
                process.stdin.close()
            except OSError:
                pass
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=1.0)
            except subprocess.TimeoutExpired:
                process.kill()
                try:
                    process.wait(timeout=1.0)
                except subprocess.TimeoutExpired:
                    pass

    def account_read(self) -> dict[str, Any]:
        return self._request("account/read", {"refreshToken": False})

    def account_rate_limits_read(self) -> dict[str, Any]:
        return self._request("account/rateLimits/read", None)

    def account_usage_read(self, thread_id: str | None = None) -> dict[str, Any]:
        params: dict[str, object] = {}
        if thread_id is not None:
            params["threadId"] = thread_id
        return self._request("account/usage/read", params)

    def _read_stdout(self) -> None:
        process = self._process
        if process is None or process.stdout is None:
            return
        for raw in process.stdout:
            try:
                message = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if isinstance(message, dict):
                self._messages.put(message)

    def _send(self, payload: dict[str, object]) -> None:
        process = self._process
        if process is None or process.stdin is None or process.poll() is not None:
            raise CodexAppServerError("process_exited", "process_exited")
        try:
            process.stdin.write(json.dumps(payload, separators=(",", ":")) + "\n")
            process.stdin.flush()
        except (BrokenPipeError, OSError) as exc:
            raise CodexAppServerError("process_exited", "process_exited") from exc

    def _notify(self, method: str, params: dict[str, object] | None) -> None:
        if method not in _ALLOWED_NOTIFICATIONS:
            raise CodexAppServerError("method_not_allowed", "method_not_allowed")
        payload: dict[str, object] = {"method": method}
        if params is not None:
            payload["params"] = params
        self._send(payload)

    def _request(
        self,
        method: str,
        params: dict[str, object] | None,
    ) -> dict[str, Any]:
        if method not in _ALLOWED_REQUESTS:
            raise CodexAppServerError("method_not_allowed", "method_not_allowed")
        request_id = self._next_id
        self._next_id += 1
        payload: dict[str, object] = {"method": method, "id": request_id}
        if params is not None:
            payload["params"] = params
        self._send(payload)

        deadline = time.monotonic() + self.timeout_seconds
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise CodexAppServerError("timeout", "timeout")
            try:
                message = self._messages.get(timeout=remaining)
            except queue.Empty as exc:
                raise CodexAppServerError("timeout", "timeout") from exc
            if message.get("id") != request_id:
                continue
            if "error" in message:
                safe_code, rpc_code = _safe_remote_error_code(
                    method,
                    params,
                    message.get("error"),
                )
                raise CodexAppServerError(
                    safe_code,
                    safe_code,
                    rpc_code=rpc_code,
                )
            result = message.get("result")
            if not isinstance(result, dict):
                raise CodexAppServerError("invalid_response", "invalid_response")
            return result
