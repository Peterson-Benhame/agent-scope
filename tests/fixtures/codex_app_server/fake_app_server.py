from __future__ import annotations

import json
import os
import sys


def _write(payload: dict[str, object]) -> None:
    sys.stdout.write(json.dumps(payload, separators=(",", ":")) + "\n")
    sys.stdout.flush()


def _account_result() -> dict[str, object]:
    return {
        "account": {
            "type": "chatgpt",
            "email": "person@example.com",
            "planType": "pro",
        },
        "requiresOpenaiAuth": False,
    }


def _limits_result() -> dict[str, object]:
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
            },
            "spendControlReached": False,
            "individualLimit": {
                "limit": "50.00",
                "used": "7.25",
                "remainingPercent": 85,
                "resetsAt": 1788307200,
            },
        },
        "rateLimitsByLimitId": None,
        "rateLimitResetCredits": None,
    }


def _usage_result(thread_id: str | None) -> dict[str, object]:
    if not thread_id:
        return {
            "summary": {
                "lifetimeTokens": 123456,
                "peakDailyTokens": 50000,
                "longestRunningTurnSec": 40,
                "currentStreakDays": 2,
                "longestStreakDays": 7,
            },
            "dailyUsageBuckets": None,
            "threadUsage": None,
        }
    return {
        "summary": {
            "lifetimeTokens": 123456,
            "peakDailyTokens": 50000,
            "longestRunningTurnSec": 40,
            "currentStreakDays": 2,
            "longestStreakDays": 7,
        },
        "dailyUsageBuckets": None,
        "threadUsage": {
            "threadId": thread_id,
            "estimatedUsageCreditsMicros": 1250000,
            "estimatedUsageUsdMicros": 490000,
            "groups": [
                {
                    "model": "gpt-5.3-codex",
                    "reasoningEffort": "high",
                    "speed": "standard",
                    "estimatedUsageCreditsMicros": 1250000,
                    "netNewInputTokens": 2700,
                    "cachedInputTokens": 19200,
                    "inputTokens": 21900,
                    "outputTokens": 90,
                    "totalTokens": 21990,
                }
            ],
        },
    }


def main() -> None:
    hang = os.environ.get("FAKE_CODEX_HANG") == "1"
    for raw in sys.stdin:
        if not raw.strip():
            continue
        try:
            request = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if not isinstance(request, dict):
            continue

        method = request.get("method")
        request_id = request.get("id")
        if method == "initialized":
            continue
        if method == "initialize":
            _write(
                {
                    "id": request_id,
                    "result": {
                        "userAgent": "fake-codex",
                        "codexHome": ".codex",
                        "platformFamily": "windows",
                        "platformOs": "windows",
                    },
                }
            )
            continue
        if hang:
            continue
        if method == "account/read":
            result = _account_result()
        elif method == "account/rateLimits/read":
            result = _limits_result()
        elif method == "account/usage/read":
            params = request.get("params")
            params_obj = params if isinstance(params, dict) else {}
            thread_id = params_obj.get("threadId")
            result = _usage_result(str(thread_id) if thread_id else None)
        else:
            _write(
                {
                    "id": request_id,
                    "error": {"code": -32601, "message": "method not found"},
                }
            )
            continue
        _write({"id": request_id, "result": result})


if __name__ == "__main__":
    main()
