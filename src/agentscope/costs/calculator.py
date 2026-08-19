from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date
from typing import Any

from agentscope.pricing.catalog import OPENAI_API_STANDARD_SCOPE, PricingCatalog, PricingRecord
from agentscope.storage.repository import Repository


_LONG_CONTEXT_INPUT_THRESHOLD = 272_000


@dataclass(frozen=True, slots=True)
class CostCalculationSummary:
    events_scanned: int
    events_priced: int
    events_unpriced: int
    complete: bool
    by_model: dict[str, float]
    total_estimated_cost_usd: float | None
    unpriced_reasons: dict[str, int]


def _ensure_cost_link_schema(repository: Repository) -> None:
    with repository.database.connect() as conn:
        columns = {str(row[1]) for row in conn.execute("PRAGMA table_info(costs)")}
        if "token_usage_id" not in columns:
            conn.execute(
                "ALTER TABLE costs ADD COLUMN token_usage_id INTEGER REFERENCES token_usage(id)"
            )
        conn.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_costs_token_usage_id
            ON costs(token_usage_id)
            WHERE token_usage_id IS NOT NULL
            """
        )


def _usage_rows(repository: Repository, utc_offset_minutes: int) -> list[dict[str, Any]]:
    modifier = f"{utc_offset_minutes:+d} minutes"
    with repository.database.connect() as conn:
        rows = conn.execute(
            f"""
            SELECT tu.id AS token_usage_id,
                   tu.session_id,
                   tu.timestamp,
                   date(tu.timestamp, '{modifier}') AS usage_day,
                   COALESCE(tu.model_id, s.model_id) AS model_id,
                   COALESCE(tm.name, sm.name) AS model,
                   tu.input_tokens,
                   tu.cached_input_tokens,
                   tu.cache_write_input_tokens,
                   tu.output_tokens,
                   uc.provider AS usage_provider
            FROM token_usage tu
            JOIN sessions s ON s.id=tu.session_id
            LEFT JOIN models tm ON tm.id=tu.model_id
            LEFT JOIN models sm ON sm.id=s.model_id
            LEFT JOIN session_usage_context uc ON uc.session_id=s.id
            ORDER BY tu.id
            """
        ).fetchall()
    return [dict(row) for row in rows]


def _classify_usage(row: dict[str, Any]) -> tuple[str | None, int, int, int, int]:
    model = row.get("model")
    input_tokens = row.get("input_tokens")
    cached_tokens = row.get("cached_input_tokens")
    output_tokens = row.get("output_tokens")
    cache_write_tokens = row.get("cache_write_input_tokens")

    if not isinstance(model, str) or not model:
        return "model_unavailable", 0, 0, 0, 0
    if input_tokens is None or cached_tokens is None or output_tokens is None:
        return "usage_incomplete", 0, 0, 0, 0

    try:
        input_value = int(input_tokens)
        cached_value = int(cached_tokens)
        output_value = int(output_tokens)
        cache_write_value = int(cache_write_tokens or 0)
    except (TypeError, ValueError):
        return "usage_incomplete", 0, 0, 0, 0

    values = (input_value, cached_value, cache_write_value, output_value)
    if any(value < 0 for value in values):
        return "invalid_token_breakdown", 0, 0, 0, 0
    if cached_value + cache_write_value > input_value:
        return "invalid_token_breakdown", 0, 0, 0, 0

    return None, input_value, cached_value, cache_write_value, output_value


def _price_for_usage(
    catalog: PricingCatalog,
    row: dict[str, Any],
    input_tokens: int,
) -> PricingRecord | None:
    provider = row.get("usage_provider")
    model = row.get("model")
    usage_day = row.get("usage_day")
    if not isinstance(provider, str) or not provider:
        return None
    if not isinstance(model, str) or not model:
        return None
    if not isinstance(usage_day, str) or not usage_day:
        return None

    context_type = "long" if input_tokens > _LONG_CONTEXT_INPUT_THRESHOLD else "short"
    return catalog.lookup(
        provider=provider,
        model=model,
        pricing_scope=OPENAI_API_STANDARD_SCOPE,
        service_tier="standard",
        context_type=context_type,
        on_date=date.fromisoformat(usage_day),
    )


def _calculate_cost(
    price: PricingRecord,
    input_tokens: int,
    cached_tokens: int,
    cache_write_tokens: int,
    output_tokens: int,
) -> float | None:
    uncached_tokens = input_tokens - cached_tokens - cache_write_tokens
    components = (
        (uncached_tokens, price.input_per_1m_usd),
        (cached_tokens, price.cached_input_per_1m_usd),
        (cache_write_tokens, price.cache_write_per_1m_usd),
        (output_tokens, price.output_per_1m_usd),
    )
    if any(tokens > 0 and unit_price is None for tokens, unit_price in components):
        return None
    return sum(
        (tokens / 1_000_000.0) * float(unit_price or 0.0)
        for tokens, unit_price in components
    )


def _persist_cost(
    repository: Repository,
    row: dict[str, Any],
    price: PricingRecord,
    cost_usd: float,
) -> None:
    with repository.database.connect() as conn:
        conn.execute(
            """
            INSERT INTO costs(
                session_id, model_id, token_usage_id, period_start, period_end,
                estimated_raw_cost_usd, observed_cost_usd,
                pricing_source, pricing_version, event_key
            ) VALUES(?, ?, ?, ?, ?, ?, NULL, ?, ?, ?)
            ON CONFLICT(token_usage_id) DO UPDATE SET
                session_id=excluded.session_id,
                model_id=excluded.model_id,
                period_start=excluded.period_start,
                period_end=excluded.period_end,
                estimated_raw_cost_usd=excluded.estimated_raw_cost_usd,
                pricing_source=excluded.pricing_source,
                pricing_version=excluded.pricing_version
            """,
            (
                int(row["session_id"]),
                row.get("model_id"),
                int(row["token_usage_id"]),
                str(row["timestamp"]),
                str(row["timestamp"]),
                cost_usd,
                price.source_url,
                price.source_version,
                f"token_usage_cost:{int(row['token_usage_id'])}",
            ),
        )


def calculate_token_usage_costs(
    repository: Repository,
    *,
    utc_offset_minutes: int,
) -> CostCalculationSummary:
    _ensure_cost_link_schema(repository)
    rows = _usage_rows(repository, utc_offset_minutes)
    catalog = PricingCatalog(repository)
    by_model: dict[str, float] = defaultdict(float)
    reasons: Counter[str] = Counter()
    priced = 0

    for row in rows:
        reason, input_tokens, cached_tokens, cache_write_tokens, output_tokens = _classify_usage(row)
        if reason is not None:
            reasons[reason] += 1
            continue

        if not row.get("usage_provider"):
            reasons["provider_unavailable"] += 1
            continue

        price = _price_for_usage(catalog, row, input_tokens)
        if price is None:
            reasons["pricing_unavailable"] += 1
            continue

        cost_usd = _calculate_cost(
            price,
            input_tokens,
            cached_tokens,
            cache_write_tokens,
            output_tokens,
        )
        if cost_usd is None:
            reasons["pricing_incomplete"] += 1
            continue

        _persist_cost(repository, row, price, cost_usd)
        model = str(row["model"])
        by_model[model] += cost_usd
        priced += 1

    unpriced = len(rows) - priced
    complete = unpriced == 0
    total = sum(by_model.values()) if complete else None
    return CostCalculationSummary(
        events_scanned=len(rows),
        events_priced=priced,
        events_unpriced=unpriced,
        complete=complete,
        by_model=dict(sorted(by_model.items())),
        total_estimated_cost_usd=total,
        unpriced_reasons=dict(sorted(reasons.items())),
    )
