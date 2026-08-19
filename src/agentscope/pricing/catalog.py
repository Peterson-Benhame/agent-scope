from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date

from agentscope.storage.repository import Repository


OPENAI_API_STANDARD_SCOPE = "openai_api_standard"
_OPENAI_PRICING_URL = "https://platform.openai.com/pricing"
_OBSERVED_ON = date(2026, 8, 19)
_SOURCE_VERSION = "openai-api-standard-observed-2026-08-19"


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


def _source_hash() -> str:
    raw = f"{_OPENAI_PRICING_URL}|{_SOURCE_VERSION}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def install_builtin_openai_catalog(repository: Repository) -> int:
    catalog = PricingCatalog(repository)
    source_hash = _source_hash()
    rows = (
        ("gpt-5.6-sol", "short", 5.0, 0.50, 6.25, 30.0),
        ("gpt-5.6-sol", "long", 10.0, 1.0, 12.50, 45.0),
        ("gpt-5.6-terra", "short", 2.50, 0.25, 3.125, 15.0),
        ("gpt-5.6-terra", "long", 5.0, 0.50, 6.25, 22.50),
        ("gpt-5.6-luna", "short", 1.0, 0.10, 1.25, 6.0),
        ("gpt-5.6-luna", "long", 2.0, 0.20, 2.50, 9.0),
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
            source_url=_OPENAI_PRICING_URL,
            source_version=_SOURCE_VERSION,
            source_hash=source_hash,
        ):
            inserted += 1
    return inserted
