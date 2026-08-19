from __future__ import annotations

from typing import Any

from agentscope.team.bundle import (
    TEAM_BUNDLE_SCHEMA,
    TEAM_BUNDLE_VERSION,
    canonical_bundle_payload,
    compute_bundle_id,
)


class TeamBundleValidationError(ValueError):
    pass


_REQUIRED_GROUPS = {
    "users",
    "machines",
    "sessions",
    "token_usage",
    "costs",
    "tool_calls",
    "agents",
    "optimizations",
}
_TOP_LEVEL_FIELDS = {
    "schema",
    "version",
    "bundle_id",
    "generated_at",
    "organization",
    "team",
    "records",
}
_RECORD_FIELDS = {
    "users": {
        "stable_key",
        "display_name",
        "provider_user_id",
        "provider",
        "identity_confidence",
    },
    "machines": {
        "stable_key",
        "display_name",
        "os",
    },
    "sessions": {
        "session_key",
        "external_session_id",
        "source",
        "project",
        "started_at",
        "ended_at",
        "originator",
        "provider",
        "model",
        "cli_version",
        "user_key",
        "machine_key",
    },
    "token_usage": {
        "event_key",
        "session_key",
        "timestamp",
        "model",
        "input_tokens",
        "cached_input_tokens",
        "cache_write_input_tokens",
        "output_tokens",
        "reasoning_output_tokens",
        "total_tokens",
        "context_window",
    },
    "costs": {
        "event_key",
        "session_key",
        "model",
        "period_start",
        "period_end",
        "estimated_raw_cost_usd",
        "observed_cost_usd",
        "estimated_cost_after_optimization_usd",
        "compression_savings_usd",
        "cache_savings_usd",
        "total_savings_usd",
        "pricing_source",
        "pricing_version",
    },
    "tool_calls": {
        "event_key",
        "session_key",
        "tool",
        "provider",
        "category",
        "external_call_id",
        "timestamp",
        "duration_ms",
        "status",
        "input_size",
        "output_size",
    },
    "agents": {
        "event_key",
        "session_key",
        "agent",
        "agent_type",
        "parent_agent",
        "started_at",
        "ended_at",
        "evidence_type",
    },
    "optimizations": {
        "event_key",
        "session_key",
        "optimizer",
        "optimizer_version",
        "timestamp",
        "model",
        "original_tokens",
        "optimized_tokens",
        "tokens_saved",
        "compression_percent",
        "cache_read_tokens",
        "compression_savings_usd",
        "cache_savings_usd",
        "observed_input_cost_usd",
        "correlation_confidence",
    },
}
_FORBIDDEN_FIELDS = {
    "content",
    "message",
    "messages",
    "prompt",
    "response",
    "payload",
    "tool_payload",
    "raw_file_path",
    "source_file",
    "attachments",
    "metadata_json",
}
_INTEGER_METRICS = {
    "input_tokens",
    "cached_input_tokens",
    "cache_write_input_tokens",
    "output_tokens",
    "reasoning_output_tokens",
    "total_tokens",
    "context_window",
    "input_size",
    "output_size",
    "original_tokens",
    "optimized_tokens",
    "tokens_saved",
    "cache_read_tokens",
}
_NUMERIC_METRICS = _INTEGER_METRICS | {
    "duration_ms",
    "estimated_raw_cost_usd",
    "observed_cost_usd",
    "estimated_cost_after_optimization_usd",
    "compression_savings_usd",
    "cache_savings_usd",
    "total_savings_usd",
    "compression_percent",
    "observed_input_cost_usd",
}


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise TeamBundleValidationError(message)


def _reject_unexpected_fields(
    value: dict[str, Any],
    allowed: set[str],
    path: str,
) -> None:
    unexpected = sorted(set(value) - allowed)
    _require(
        not unexpected,
        f"unexpected field at {path}: {', '.join(unexpected)}",
    )


def _scan_forbidden(value: Any, path: str = "bundle") -> None:
    if isinstance(value, dict):
        for key, nested in value.items():
            if key in _FORBIDDEN_FIELDS:
                raise TeamBundleValidationError(f"forbidden field {key} at {path}")
            _scan_forbidden(nested, f"{path}.{key}")
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            _scan_forbidden(nested, f"{path}[{index}]")


def _validate_numeric_fields(record: dict[str, Any], group: str) -> None:
    for key in _NUMERIC_METRICS:
        if key not in record or record[key] is None:
            continue
        value = record[key]
        if key in _INTEGER_METRICS:
            _require(
                isinstance(value, int) and not isinstance(value, bool),
                f"{group}.{key} must be an integer or null",
            )
        else:
            _require(
                isinstance(value, (int, float)) and not isinstance(value, bool),
                f"{group}.{key} must be numeric or null",
            )


def _validate_record_fields(records: dict[str, Any]) -> None:
    for group in _REQUIRED_GROUPS:
        for record in records[group]:
            _require(isinstance(record, dict), f"{group} record must be an object")
            _reject_unexpected_fields(
                record,
                _RECORD_FIELDS[group],
                f"records.{group}",
            )


def validate_team_bundle(bundle: dict) -> None:
    _require(isinstance(bundle, dict), "bundle must be an object")
    _reject_unexpected_fields(bundle, _TOP_LEVEL_FIELDS, "bundle")
    _require(bundle.get("schema") == TEAM_BUNDLE_SCHEMA, "invalid bundle schema")
    _require(bundle.get("version") == TEAM_BUNDLE_VERSION, "unsupported bundle version")
    _require(isinstance(bundle.get("bundle_id"), str), "bundle_id is required")
    _require(isinstance(bundle.get("generated_at"), str), "generated_at is required")
    _require(
        bundle.get("organization") is None
        or isinstance(bundle.get("organization"), str),
        "organization must be a string or null",
    )
    _require(
        bundle.get("team") is None or isinstance(bundle.get("team"), str),
        "team must be a string or null",
    )

    records = bundle.get("records")
    _require(isinstance(records, dict), "records must be an object")
    missing = sorted(_REQUIRED_GROUPS - set(records))
    extra = sorted(set(records) - _REQUIRED_GROUPS)
    _require(not missing, f"missing record groups: {', '.join(missing)}")
    _require(not extra, f"unexpected record groups: {', '.join(extra)}")
    for group in _REQUIRED_GROUPS:
        _require(isinstance(records[group], list), f"records.{group} must be a list")

    _scan_forbidden(bundle)
    _validate_record_fields(records)

    for record in records["users"]:
        _require(
            isinstance(record.get("stable_key"), str) and bool(record.get("stable_key")),
            "users.stable_key is required",
        )
    for record in records["machines"]:
        _require(
            isinstance(record.get("stable_key"), str) and bool(record.get("stable_key")),
            "machines.stable_key is required",
        )
    for record in records["sessions"]:
        _require(
            isinstance(record.get("session_key"), str) and bool(record.get("session_key")),
            "sessions.session_key is required",
        )
        _require(
            isinstance(record.get("source"), str) and bool(record.get("source")),
            "sessions.source is required",
        )

    for group in ("token_usage", "costs", "tool_calls", "agents", "optimizations"):
        for record in records[group]:
            _require(
                isinstance(record.get("event_key"), str) and bool(record.get("event_key")),
                f"{group}.event_key is required",
            )
            if group != "optimizations" or record.get("session_key") is not None:
                _require(
                    isinstance(record.get("session_key"), str)
                    and bool(record.get("session_key")),
                    f"{group}.session_key is required",
                )
            _validate_numeric_fields(record, group)

    expected_id = compute_bundle_id(canonical_bundle_payload(bundle))
    _require(
        bundle["bundle_id"] == expected_id,
        "bundle_id does not match canonical payload",
    )
