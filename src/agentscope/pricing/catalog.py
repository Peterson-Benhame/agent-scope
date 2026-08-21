from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date

from agentscope.storage.repository import Repository


OPENAI_API_STANDARD_SCOPE = "openai_api_standard"
_OBSERVED_ON = date(2026, 8, 19)
_SOURCE_VERSION = "openai-api-standard-observed-2026-08-19"
_MODEL_PAGE_URLS = {
    "gpt-5.3-codex": "https://developers.openai.com/api/docs/models/gpt-5.3-codex",
    "gpt-5.4": "https://developers.openai.com/api/docs/models/gpt-5.4",
    "gpt-5.4-mini": "https://developers.openai.com/api/docs/models/gpt-5.4-mini",
    "gpt-5.5": "https://developers.openai.com/api/docs/models/gpt-5.5",
    "gpt-5.6-sol": "https://developers.openai.com/api/docs/models/gpt-5.6-sol.md",
    "gpt-5.6-terra": "https://developers.openai.com/api/docs/models/gpt-5.6-terra.md",
    "gpt-5.6-luna": "https://developers.openai.com/api/docs/models/gpt-5.6-luna.md",
}
_LAUNCH_SOURCE_URL = "https://openai.com/index/gpt-5-6/"
_REDUCED_SOURCE_URL = (
    "https://openai.com/index/advancing-the-price-performance-frontier-with-gpt-5-6/"
)
_LAUNCH_VERSION = "openai-gpt-5.6-launch-2026-07-09"
_REDUCED_VERSION = "openai-gpt-5.6-price-reduction-2026-07-30"


@dataclass(frozen=True, slots=True)
class PricingRecord:
    provider: str
    model: str
    pricing_scope: str
    service_tier: str
    context_type: str
    input_per_1m_usd: float | None
    cached_input_per_1m_usd: float | None
    cache_write_per_1m_usd: float | None
    output_per_1m_usd: float | None
    valid_from: date
    valid_to: date | None
    valid_from_basis: str
    source_url: str
    source_version: str
    source_hash: str
    status: str
    record_key: str


class PricingCatalog:
    def __init__(self, repository: Repository) -> None:
        self.repository = repository

    @staticmethod
    def _record_key(*parts: object) -> str:
        raw = "|".join("" if value is None else str(value) for value in parts)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def add_price(
        self,
        *,
        provider: str,
        model: str,
        pricing_scope: str,
        service_tier: str,
        context_type: str,
        input_per_1m_usd: float | None,
        cached_input_per_1m_usd: float | None,
        cache_write_per_1m_usd: float | None,
        output_per_1m_usd: float | None,
        valid_from: date,
        valid_to: date | None,
        valid_from_basis: str,
        source_url: str,
        source_version: str,
        source_hash: str,
        status: str = "active",
    ) -> bool:
        record_key = self._record_key(
            provider,
            model,
            pricing_scope,
            service_tier,
            context_type,
            input_per_1m_usd,
            cached_input_per_1m_usd,
            cache_write_per_1m_usd,
            output_per_1m_usd,
            valid_from.isoformat(),
            valid_to.isoformat() if valid_to else None,
            valid_from_basis,
            source_url,
            source_version,
            source_hash,
            status,
        )
        with self.repository.database.connect() as conn:
            cursor = conn.execute(
                """
                INSERT OR IGNORE INTO model_pricing(
                    provider, model, pricing_scope, service_tier, context_type,
                    input_per_1m_usd, cached_input_per_1m_usd,
                    cache_write_per_1m_usd, output_per_1m_usd,
                    valid_from, valid_to, valid_from_basis, source_url,
                    source_version, source_hash, status, record_key
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    provider,
                    model,
                    pricing_scope,
                    service_tier,
                    context_type,
                    input_per_1m_usd,
                    cached_input_per_1m_usd,
                    cache_write_per_1m_usd,
                    output_per_1m_usd,
                    valid_from.isoformat(),
                    valid_to.isoformat() if valid_to else None,
                    valid_from_basis,
                    source_url,
                    source_version,
                    source_hash,
                    status,
                    record_key,
                ),
            )
        return cursor.rowcount > 0

    def lookup(
        self,
        *,
        provider: str,
        model: str,
        pricing_scope: str,
        service_tier: str,
        context_type: str,
        on_date: date,
    ) -> PricingRecord | None:
        with self.repository.database.connect() as conn:
            row = conn.execute(
                """
                SELECT *
                FROM model_pricing
                WHERE provider=?
                  AND model=?
                  AND pricing_scope=?
                  AND service_tier=?
                  AND context_type=?
                  AND status='active'
                  AND valid_from<=?
                  AND (valid_to IS NULL OR valid_to>=?)
                ORDER BY valid_from DESC, id DESC
                LIMIT 1
                """,
                (
                    provider,
                    model,
                    pricing_scope,
                    service_tier,
                    context_type,
                    on_date.isoformat(),
                    on_date.isoformat(),
                ),
            ).fetchone()
        if row is None:
            return None
        return PricingRecord(
            provider=str(row["provider"]),
            model=str(row["model"]),
            pricing_scope=str(row["pricing_scope"]),
            service_tier=str(row["service_tier"]),
            context_type=str(row["context_type"]),
            input_per_1m_usd=(
                float(row["input_per_1m_usd"])
                if row["input_per_1m_usd"] is not None
                else None
            ),
            cached_input_per_1m_usd=(
                float(row["cached_input_per_1m_usd"])
                if row["cached_input_per_1m_usd"] is not None
                else None
            ),
            cache_write_per_1m_usd=(
                float(row["cache_write_per_1m_usd"])
                if row["cache_write_per_1m_usd"] is not None
                else None
            ),
            output_per_1m_usd=(
                float(row["output_per_1m_usd"])
                if row["output_per_1m_usd"] is not None
                else None
            ),
            valid_from=date.fromisoformat(str(row["valid_from"])),
            valid_to=(
                date.fromisoformat(str(row["valid_to"]))
                if row["valid_to"] is not None
                else None
            ),
            valid_from_basis=str(row["valid_from_basis"]),
            source_url=str(row["source_url"]),
            source_version=str(row["source_version"]),
            source_hash=str(row["source_hash"]),
            status=str(row["status"]),
            record_key=str(row["record_key"]),
        )


def _source_hash(model: str) -> str:
    raw = f"{_MODEL_PAGE_URLS[model]}|{_SOURCE_VERSION}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _provenance_hash(source_url: str, source_version: str) -> str:
    return hashlib.sha256(f"{source_url}|{source_version}".encode("utf-8")).hexdigest()


def _context_rows(
    model: str,
    input_price: float,
    cached_price: float,
    output_price: float,
) -> tuple[tuple[str, str, float, float, float | None, float], ...]:
    cache_write = input_price * 1.25
    return (
        (model, "short", input_price, cached_price, cache_write, output_price),
        (
            model,
            "long",
            input_price * 2.0,
            cached_price * 2.0,
            cache_write * 2.0,
            output_price * 1.5,
        ),
    )


def _flat_context_rows(
    model: str,
    input_price: float,
    cached_price: float,
    output_price: float,
    *,
    long_context_uplift: bool,
) -> tuple[tuple[str, str, float, float, float | None, float], ...]:
    long_input = input_price * 2.0 if long_context_uplift else input_price
    long_cached = cached_price * 2.0 if long_context_uplift else cached_price
    long_output = output_price * 1.5 if long_context_uplift else output_price
    return (
        (model, "short", input_price, cached_price, None, output_price),
        (model, "long", long_input, long_cached, None, long_output),
    )


def _install_history_rows(
    repository: Repository,
    *,
    rows: tuple[tuple[str, str, float, float, float | None, float], ...],
    valid_from: date,
    valid_to: date | None,
    source_url: str,
    source_version: str,
) -> int:
    catalog = PricingCatalog(repository)
    source_hash = _provenance_hash(source_url, source_version)
    inserted = 0
    for model, context_type, input_price, cached_price, cache_write, output_price in rows:
        if catalog.add_price(
            provider="openai",
            model=model,
            pricing_scope=OPENAI_API_STANDARD_SCOPE,
            service_tier="standard",
            context_type=context_type,
            input_per_1m_usd=input_price,
            cached_input_per_1m_usd=cached_price,
            cache_write_per_1m_usd=cache_write,
            output_per_1m_usd=output_price,
            valid_from=valid_from,
            valid_to=valid_to,
            valid_from_basis="provider_declared",
            source_url=source_url,
            source_version=source_version,
            source_hash=source_hash,
        ):
            inserted += 1
    return inserted


def _install_current_model_history(repository: Repository) -> int:
    models = (
        (
            "gpt-5.3-codex",
            1.75,
            0.175,
            14.0,
            date(2026, 2, 5),
            False,
            "openai-gpt-5.3-codex-api-pricing-2026-08-21",
        ),
        (
            "gpt-5.4",
            2.50,
            0.25,
            15.0,
            date(2026, 3, 5),
            True,
            "openai-gpt-5.4-api-pricing-2026-03-05",
        ),
        (
            "gpt-5.4-mini",
            0.75,
            0.075,
            4.50,
            date(2026, 3, 17),
            False,
            "openai-gpt-5.4-mini-api-pricing-2026-03-17",
        ),
        (
            "gpt-5.5",
            5.0,
            0.50,
            30.0,
            date(2026, 4, 24),
            True,
            "openai-gpt-5.5-api-pricing-2026-04-24",
        ),
    )
    inserted = 0
    for model, input_price, cached_price, output_price, valid_from, uplift, version in models:
        inserted += _install_history_rows(
            repository,
            rows=_flat_context_rows(
                model,
                input_price,
                cached_price,
                output_price,
                long_context_uplift=uplift,
            ),
            valid_from=valid_from,
            valid_to=None,
            source_url=_MODEL_PAGE_URLS[model],
            source_version=version,
        )
    return inserted


def install_official_openai_history(repository: Repository) -> int:
    """Install provider-declared OpenAI API prices with their effective dates."""
    pre_reduction_rows = (
        *_context_rows("gpt-5.6-terra", 2.50, 0.25, 15.0),
        *_context_rows("gpt-5.6-luna", 1.0, 0.10, 6.0),
    )
    current_rows = (
        *_context_rows("gpt-5.6-terra", 2.0, 0.20, 12.0),
        *_context_rows("gpt-5.6-luna", 0.20, 0.02, 1.20),
    )
    inserted = _install_current_model_history(repository)
    inserted += _install_history_rows(
        repository,
        rows=_context_rows("gpt-5.6-sol", 5.0, 0.50, 30.0),
        valid_from=date(2026, 7, 9),
        valid_to=None,
        source_url=_LAUNCH_SOURCE_URL,
        source_version=_LAUNCH_VERSION,
    )
    inserted += _install_history_rows(
        repository,
        rows=pre_reduction_rows,
        valid_from=date(2026, 7, 9),
        valid_to=date(2026, 7, 29),
        source_url=_LAUNCH_SOURCE_URL,
        source_version=_LAUNCH_VERSION,
    )
    inserted += _install_history_rows(
        repository,
        rows=current_rows,
        valid_from=date(2026, 7, 30),
        valid_to=None,
        source_url=_REDUCED_SOURCE_URL,
        source_version=_REDUCED_VERSION,
    )
    return inserted


def install_builtin_openai_catalog(repository: Repository) -> int:
    catalog = PricingCatalog(repository)
    rows = (
        ("gpt-5.6-sol", "short", 5.0, 0.50, 6.25, 30.0),
        ("gpt-5.6-sol", "long", 10.0, 1.0, 12.50, 45.0),
        ("gpt-5.6-terra", "short", 2.0, 0.20, 2.50, 12.0),
        ("gpt-5.6-terra", "long", 4.0, 0.40, 5.0, 18.0),
        ("gpt-5.6-luna", "short", 0.20, 0.02, 0.25, 1.20),
        ("gpt-5.6-luna", "long", 0.40, 0.04, 0.50, 1.80),
    )
    inserted = 0
    for model, context_type, input_price, cached_price, cache_write, output_price in rows:
        if catalog.add_price(
            provider="openai",
            model=model,
            pricing_scope=OPENAI_API_STANDARD_SCOPE,
            service_tier="standard",
            context_type=context_type,
            input_per_1m_usd=input_price,
            cached_input_per_1m_usd=cached_price,
            cache_write_per_1m_usd=cache_write,
            output_per_1m_usd=output_price,
            valid_from=_OBSERVED_ON,
            valid_to=None,
            valid_from_basis="catalog_observed",
            source_url=_MODEL_PAGE_URLS[model],
            source_version=_SOURCE_VERSION,
            source_hash=_source_hash(model),
        ):
            inserted += 1
    return inserted
