from datetime import date

import pytest

from agentscope.costs.calculator import calculate_token_usage_costs
from agentscope.domain.models import NormalizedSession, NormalizedTokenUsage
from agentscope.pricing.catalog import PricingCatalog
from agentscope.storage.database import Database
from agentscope.storage.repository import Repository
from agentscope.usage_context import SessionUsageContext, persist_session_usage_context


def _repo(tmp_path):
    db = Database(tmp_path / "agentscope.db")
    db.initialize()
    return db, Repository(db)


def _add_openai_usage(
    repo,
    *,
    external_session_id,
    model,
    timestamp,
    input_tokens,
    cached_input_tokens,
    cache_write_input_tokens,
    output_tokens,
):
    session_id = repo.upsert_session(
        NormalizedSession(
            external_session_id=external_session_id,
            source="codex",
            provider="headroom",
            model=model,
            started_at=timestamp,
        )
    )
    persist_session_usage_context(
        repo,
        session_id,
        SessionUsageContext(
            provider="openai",
            product="codex",
            client="vscode",
            client_confidence="explicit",
        ),
    )
    return repo.insert_token_usage(
        session_id,
        None,
        NormalizedTokenUsage(
            timestamp=timestamp,
            session_external_id=external_session_id,
            model=model,
            input_tokens=input_tokens,
            cached_input_tokens=cached_input_tokens,
            cache_write_input_tokens=cache_write_input_tokens,
            output_tokens=output_tokens,
            total_tokens=(input_tokens or 0) + (output_tokens or 0),
            source_file=f"{external_session_id}.jsonl",
            source_line=1,
        ),
    )


def _price(
    repo,
    *,
    model,
    context_type,
    input_price,
    cached_price,
    cache_write_price,
    output_price,
):
    PricingCatalog(repo).add_price(
        provider="openai",
        model=model,
        pricing_scope="openai_api_standard",
        service_tier="standard",
        context_type=context_type,
        input_per_1m_usd=input_price,
        cached_input_per_1m_usd=cached_price,
        cache_write_per_1m_usd=cache_write_price,
        output_per_1m_usd=output_price,
        valid_from=date(2026, 8, 19),
        valid_to=None,
        valid_from_basis="provider_declared",
        source_url="https://example.invalid/pricing",
        source_version="test-pricing-v1",
        source_hash="test-hash-v1",
    )


def test_calculates_each_model_from_uncached_cached_cache_write_and_output(tmp_path):
    db, repo = _repo(tmp_path)
    _price(
        repo,
        model="gpt-5.6-sol",
        context_type="short",
        input_price=5.0,
        cached_price=0.5,
        cache_write_price=6.25,
        output_price=30.0,
    )
    _price(
        repo,
        model="gpt-5.6-terra",
        context_type="long",
        input_price=4.0,
        cached_price=0.4,
        cache_write_price=5.0,
        output_price=18.0,
    )
    sol_usage_id = _add_openai_usage(
        repo,
        external_session_id="sol-session",
        model="gpt-5.6-sol",
        timestamp="2026-08-19T12:00:00Z",
        input_tokens=1_000_000,
        cached_input_tokens=200_000,
        cache_write_input_tokens=100_000,
        output_tokens=100_000,
    )
    terra_usage_id = _add_openai_usage(
        repo,
        external_session_id="terra-session",
        model="gpt-5.6-terra",
        timestamp="2026-08-19T13:00:00Z",
        input_tokens=300_000,
        cached_input_tokens=50_000,
        cache_write_input_tokens=None,
        output_tokens=10_000,
    )

    summary = calculate_token_usage_costs(repo, utc_offset_minutes=0)

    assert summary.events_scanned == 2
    assert summary.events_priced == 2
    assert summary.events_unpriced == 0
    assert summary.complete is True
    assert summary.by_model["gpt-5.6-sol"] == pytest.approx(7.225)
    assert summary.by_model["gpt-5.6-terra"] == pytest.approx(1.2)
    assert summary.total_estimated_cost_usd == pytest.approx(8.425)

    with db.connect() as conn:
        rows = conn.execute(
            """
            SELECT token_usage_id, estimated_raw_cost_usd, pricing_source, pricing_version
            FROM costs
            WHERE token_usage_id IS NOT NULL
            ORDER BY token_usage_id
            """
        ).fetchall()
    assert [row["token_usage_id"] for row in rows] == [sol_usage_id, terra_usage_id]
    assert sum(row["estimated_raw_cost_usd"] for row in rows) == pytest.approx(8.425)
    assert {row["pricing_version"] for row in rows} == {"test-pricing-v1"}


def test_uses_local_usage_day_for_non_retroactive_pricing(tmp_path):
    db, repo = _repo(tmp_path)
    _price(
        repo,
        model="gpt-5.6-sol",
        context_type="short",
        input_price=5.0,
        cached_price=0.5,
        cache_write_price=6.25,
        output_price=30.0,
    )
    _add_openai_usage(
        repo,
        external_session_id="cross-midnight",
        model="gpt-5.6-sol",
        timestamp="2026-08-19T00:10:00Z",
        input_tokens=1_000,
        cached_input_tokens=0,
        cache_write_input_tokens=0,
        output_tokens=100,
    )

    summary = calculate_token_usage_costs(repo, utc_offset_minutes=-180)

    assert summary.events_scanned == 1
    assert summary.events_priced == 0
    assert summary.events_unpriced == 1
    assert summary.complete is False
    assert summary.total_estimated_cost_usd is None
    assert summary.unpriced_reasons == {"pricing_unavailable": 1}
    with db.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM costs WHERE token_usage_id IS NOT NULL").fetchone()[0] == 0


def test_calculation_is_idempotent_per_token_usage_event(tmp_path):
    db, repo = _repo(tmp_path)
    _price(
        repo,
        model="gpt-5.6-luna",
        context_type="short",
        input_price=0.2,
        cached_price=0.02,
        cache_write_price=0.25,
        output_price=1.2,
    )
    usage_id = _add_openai_usage(
        repo,
        external_session_id="luna-session",
        model="gpt-5.6-luna",
        timestamp="2026-08-19T15:00:00Z",
        input_tokens=10_000,
        cached_input_tokens=2_000,
        cache_write_input_tokens=0,
        output_tokens=1_000,
    )

    first = calculate_token_usage_costs(repo, utc_offset_minutes=0)
    second = calculate_token_usage_costs(repo, utc_offset_minutes=0)

    assert first.events_priced == 1
    assert second.events_priced == 1
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT token_usage_id FROM costs WHERE token_usage_id IS NOT NULL"
        ).fetchall()
    assert [row["token_usage_id"] for row in rows] == [usage_id]


def test_invalid_or_incomplete_token_breakdown_is_not_priced(tmp_path):
    _, repo = _repo(tmp_path)
    _price(
        repo,
        model="gpt-5.6-sol",
        context_type="short",
        input_price=5.0,
        cached_price=0.5,
        cache_write_price=6.25,
        output_price=30.0,
    )
    _add_openai_usage(
        repo,
        external_session_id="invalid-session",
        model="gpt-5.6-sol",
        timestamp="2026-08-19T12:00:00Z",
        input_tokens=1_000,
        cached_input_tokens=900,
        cache_write_input_tokens=200,
        output_tokens=100,
    )
    _add_openai_usage(
        repo,
        external_session_id="incomplete-session",
        model="gpt-5.6-sol",
        timestamp="2026-08-19T12:30:00Z",
        input_tokens=1_000,
        cached_input_tokens=None,
        cache_write_input_tokens=0,
        output_tokens=100,
    )

    summary = calculate_token_usage_costs(repo, utc_offset_minutes=0)

    assert summary.events_priced == 0
    assert summary.events_unpriced == 2
    assert summary.complete is False
    assert summary.total_estimated_cost_usd is None
    assert summary.unpriced_reasons == {
        "invalid_token_breakdown": 1,
        "usage_incomplete": 1,
    }
