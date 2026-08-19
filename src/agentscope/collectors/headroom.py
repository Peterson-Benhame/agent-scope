from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agentscope.domain.models import NormalizedOptimization


@dataclass(slots=True)
class HeadroomCollectedData:
    lifetime: dict[str, Any] = field(default_factory=dict)
    by_model: dict[str, Any] = field(default_factory=dict)
    by_project: dict[str, Any] = field(default_factory=dict)
    optimizations: list[NormalizedOptimization] = field(default_factory=list)
    missing_files: list[str] = field(default_factory=list)
    discrepancies: list[dict[str, Any]] = field(default_factory=list)
    session_events: list[dict[str, Any]] = field(default_factory=list)


def _number(value: Any) -> int | float:
    if isinstance(value, (int, float)):
        return value
    return 0


def _request_events(home: Path) -> list[NormalizedOptimization]:
    events: list[NormalizedOptimization] = []
    for path in sorted(home.glob("*.jsonl")):
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for line_number, raw in enumerate(lines, start=1):
            if not raw.strip():
                continue
            try:
                item = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if not isinstance(item, dict):
                continue
            if not {"before", "after", "saved"}.issubset(item):
                continue
            before = int(_number(item.get("before")))
            after = int(_number(item.get("after")))
            saved = int(_number(item.get("saved")))
            compression_percent = (saved / before * 100.0) if before else None
            events.append(
                NormalizedOptimization(
                    timestamp=str(item.get("ts") or item.get("timestamp") or ""),
                    optimizer="headroom",
                    model=item.get("model"),
                    original_tokens=before,
                    optimized_tokens=after,
                    tokens_saved=saved,
                    compression_percent=compression_percent,
                    compression_savings_usd=float(_number(item.get("cost_usd"))) if item.get("cost_usd") is not None else None,
                    source_file=str(path),
                    source_line=line_number,
                    metadata={
                        "client": item.get("client"),
                        "source": item.get("source"),
                        "pid": item.get("pid"),
                    },
                )
            )
    return events


def _history_events(history: list[dict[str, Any]], source_file: Path) -> list[NormalizedOptimization]:
    result: list[NormalizedOptimization] = []
    previous = {
        "total_tokens_saved": 0,
        "compression_savings_usd": 0.0,
        "cache_read_tokens": 0,
        "cache_savings_usd": 0.0,
        "total_input_tokens": 0,
        "total_input_cost_usd": 0.0,
    }
    for index, item in enumerate(history, start=1):
        saved = int(_number(item.get("total_tokens_saved")) - _number(previous["total_tokens_saved"]))
        optimized = int(_number(item.get("total_input_tokens")) - _number(previous["total_input_tokens"]))
        cache_read = int(_number(item.get("cache_read_tokens")) - _number(previous["cache_read_tokens"]))
        compression_savings = float(
            _number(item.get("compression_savings_usd")) - _number(previous["compression_savings_usd"])
        )
        cache_savings = float(_number(item.get("cache_savings_usd")) - _number(previous["cache_savings_usd"]))
        observed_cost = float(_number(item.get("total_input_cost_usd")) - _number(previous["total_input_cost_usd"]))
        original = optimized + saved
        compression_percent = (saved / original * 100.0) if original else None
        result.append(
            NormalizedOptimization(
                timestamp=str(item.get("timestamp") or ""),
                optimizer="headroom",
                model=item.get("model"),
                original_tokens=original,
                optimized_tokens=optimized,
                tokens_saved=saved,
                compression_percent=compression_percent,
                cache_read_tokens=cache_read,
                compression_savings_usd=compression_savings,
                cache_savings_usd=cache_savings,
                observed_input_cost_usd=observed_cost,
                source_file=str(source_file),
                source_line=index,
                metadata={"derived_from_cumulative_history": True},
            )
        )
        for key in previous:
            previous[key] = item.get(key, previous[key])
    return result


def _session_stats_events(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    events: list[dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    for line_number, raw in enumerate(lines, start=1):
        if not raw.strip():
            continue
        try:
            item = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict) and item.get("type") in {"compress", "retrieve"}:
            copy = dict(item)
            copy["_source_file"] = str(path)
            copy["_source_line"] = line_number
            events.append(copy)
    return events


def _session_stats_optimizations(events: list[dict[str, Any]]) -> list[NormalizedOptimization]:
    result: list[NormalizedOptimization] = []
    for item in events:
        if item.get("type") != "compress":
            continue
        before = int(_number(item.get("input_tokens")))
        after = int(_number(item.get("output_tokens")))
        saved = max(before - after, 0)
        raw_ts = item.get("timestamp")
        if isinstance(raw_ts, (int, float)):
            timestamp = datetime.fromtimestamp(float(raw_ts), tz=timezone.utc).isoformat()
        else:
            timestamp = str(raw_ts or "")
        result.append(
            NormalizedOptimization(
                timestamp=timestamp,
                optimizer="headroom",
                original_tokens=before,
                optimized_tokens=after,
                tokens_saved=saved,
                compression_percent=float(item.get("savings_percent")) if item.get("savings_percent") is not None else ((saved / before * 100.0) if before else None),
                source_file=item.get("_source_file"),
                source_line=item.get("_source_line"),
                metadata={
                    "source": "session_stats",
                    "pid": item.get("pid"),
                    "strategy": item.get("strategy"),
                },
            )
        )
    return result


def collect_headroom(home: Path) -> HeadroomCollectedData:
    data = HeadroomCollectedData()
    proxy_path = home / "proxy_savings.json"
    payload: dict[str, Any] = {}
    if proxy_path.exists():
        try:
            loaded = json.loads(proxy_path.read_text(encoding="utf-8", errors="replace"))
            if isinstance(loaded, dict):
                payload = loaded
        except (OSError, json.JSONDecodeError):
            payload = {}
    else:
        data.missing_files.append(str(proxy_path))

    data.lifetime = dict(payload.get("lifetime") or {})
    data.by_model = dict(payload.get("by_model") or {})
    data.by_project = dict(payload.get("projects") or {})
    data.discrepancies = list(payload.get("discrepancies") or [])

    session_stats = home / "session_stats.jsonl"
    data.session_events = _session_stats_events(session_stats)

    per_request = _request_events(home)
    if per_request:
        data.optimizations = per_request
    else:
        history = payload.get("history") or []
        if isinstance(history, list) and history:
            normalized_history = [x for x in history if isinstance(x, dict)]
            data.optimizations = _history_events(normalized_history, proxy_path)
        elif data.session_events:
            data.optimizations = _session_stats_optimizations(data.session_events)

    if not session_stats.exists():
        data.missing_files.append(str(session_stats))
    return data
