from pathlib import Path
import shutil

from agentscope.collectors.headroom import collect_headroom


FIXTURE = Path("tests/fixtures/headroom")


def test_collects_lifetime_and_breakdowns():
    data = collect_headroom(FIXTURE)
    assert data.lifetime["requests"] == 3
    assert data.lifetime["tokens_saved"] == 1500
    assert data.by_model["gpt-5.6-terra"]["requests"] == 3
    assert data.by_project["demo"]["tokens_saved"] == 1500


def test_prefers_per_request_jsonl_events_to_avoid_double_counting():
    data = collect_headroom(FIXTURE)
    assert len(data.optimizations) == 2
    assert sum(x.tokens_saved or 0 for x in data.optimizations) == 1500
    assert sum(x.compression_savings_usd or 0 for x in data.optimizations) == 0.003
    assert all(x.optimizer == "headroom" for x in data.optimizations)


def test_derives_deltas_from_cumulative_history_when_no_request_jsonl(tmp_path):
    shutil.copy(FIXTURE / "proxy_savings.json", tmp_path / "proxy_savings.json")
    data = collect_headroom(tmp_path)
    assert len(data.optimizations) == 2
    first, second = data.optimizations
    assert first.tokens_saved == 500
    assert first.optimized_tokens == 15000
    assert first.original_tokens == 15500
    assert second.tokens_saved == 1000
    assert second.optimized_tokens == 35000
    assert second.cache_read_tokens == 8000
    assert round(second.cache_savings_usd or 0, 6) == 0.014
    assert round(second.observed_input_cost_usd or 0, 6) == 0.055


def test_missing_optional_headroom_files_is_not_fatal(tmp_path):
    data = collect_headroom(tmp_path)
    assert data.lifetime == {}
    assert data.optimizations == []
    assert data.missing_files


def test_collects_session_stats_without_double_counting_durable_ledger():
    data = collect_headroom(FIXTURE)
    assert len(data.session_events) == 2
    assert data.session_events[0]["type"] == "compress"
    assert data.session_events[0]["pid"] == 321
    assert len(data.optimizations) == 2


def test_uses_session_stats_as_fallback_when_no_durable_savings_or_proxy_history(tmp_path):
    shutil.copy(FIXTURE / "session_stats.jsonl", tmp_path / "session_stats.jsonl")
    data = collect_headroom(tmp_path)
    assert len(data.optimizations) == 1
    event = data.optimizations[0]
    assert event.original_tokens == 5000
    assert event.optimized_tokens == 2000
    assert event.tokens_saved == 3000
    assert event.metadata["source"] == "session_stats"
    assert event.metadata["pid"] == 321
