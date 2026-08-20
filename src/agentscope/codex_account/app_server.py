from __future__ import annotations

import json
import queue
import subprocess
import threading
import time
from typing import Any


_ALLOWED_REQUESTS = {
    "initialize",
    "account/read",
    "account/rateLimits/read",
    "account/usage/read",
}
_ALLOWED_NOTIFICATIONS = {"initialized"}


class CodexAppServerError(RuntimeError):
    def __init__(self, code: str, message: str | None = None):
        self.code = code
        super().__init__(message or code)


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
        command = self.command or [self.codex_bin, "app-server", "--stdio"]
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
            raise CodexAppServerError(
                "codex_not_found",
                "codex_not_found",
            ) from exc
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
                raise CodexAppServerError("remote_error", "remote_error")
            result = message.get("result")
            if not isinstance(result, dict):
                raise CodexAppServerError("invalid_response", "invalid_response")
            return result
