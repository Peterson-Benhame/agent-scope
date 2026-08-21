from __future__ import annotations

import hashlib
import re
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable

from agentscope.pricing.catalog import (
    OPENAI_API_STANDARD_SCOPE,
    PricingCatalog,
    install_builtin_openai_catalog,
)
from agentscope.storage.repository import Repository


_PROVIDER = "openai"
_REFRESH_TTL = timedelta(hours=24)
_MODEL_URLS = {
    "gpt-5.6-sol": "https://developers.openai.com/api/docs/models/gpt-5.6-sol.md",
    "gpt-5.6-terra": "https://developers.openai.com/api/docs/models/gpt-5.6-terra.md",
    "gpt-5.6-luna": "https://developers.openai.com/api/docs/models/gpt-5.6-luna.md",
}
_STATE_SCHEMA = """
CREATE TABLE IF NOT EXISTS pricing_refresh_state (
    provider TEXT PRIMARY KEY,
    last_attempt_at TEXT,
    last_success_at TEXT,
    status TEXT NOT NULL DEFAULT 'never',
    source_hash TEXT,
    error_message TEXT,
    records_inserted INTEGER NOT NULL DEFAULT 0
);
"""


@dataclass(frozen=True, slots=True)
class PricingRefreshResult:
    status: str
    models_checked: int
    records_inserted: int
    used_last_known_good: bool
    last_success_at: str | None
    error: str | None


@dataclass(frozen=True, slots=True)
class _ModelPrices:
    input_per_1m_usd: float
    cached_input_per_1m_usd: float
    output_per_1m_usd: float


def _default_fetch_text(url: str) -> str:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "AgentScope/0.1 pricing-refresh"},
    )
    with urllib.request.urlopen(request, timeout=8) as response:
        return response.read().decode("utf-8")


def _extract_price(text: str, label: str) -> float:
    escaped = re.escape(label)
    patterns = (
        rf"(?im)^\s*{escaped}\s*$\s*^\s*\$\s*([0-9]+(?:\.[0-9]+)?)",
        rf"(?i)\b{escaped}\b\s*[:|]?\s*\$\s*([0-9]+(?:\.[0-9]+)?)",
    )
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return float(match.group(1))
    raise ValueError(f"missing {label} price")


def _parse_model_prices(text: str) -> _ModelPrices:
    return _ModelPrices(
        input_per_1m_usd=_extract_price(text, "Input"),
        cached_input_per_1m_usd=_extract_price(text, "Cached input"),
        output_per_1m_usd=_extract_price(text, "Output"),
    )


def _parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


class OpenAIPricingRefresher:
    def __init__(
        self,
        repository: Repository,
        *,
        fetch_text: Callable[[str], str] = _default_fetch_text,
        now: Callable[[], datetime] | None = None,
        ttl: timedelta = _REFRESH_TTL,
    ) -> None:
        self.repository = repository
        self.fetch_text = fetch_text
        self.now = now or (lambda: datetime.now(timezone.utc))
        self.ttl = ttl
        self._ensure_state_schema()

    def _ensure_state_schema(self) -> None:
        with self.repository.database.connect() as conn:
            conn.executescript(_STATE_SCHEMA)

    def _state(self):
        with self.repository.database.connect() as conn:
            return conn.execute(
                "SELECT * FROM pricing_refresh_state WHERE provider=?",
                (_PROVIDER,),
            ).fetchone()

    def _has_catalog(self) -> bool:
        with self.repository.database.connect() as conn:
            row = conn.execute(
                """
                SELECT COUNT(*) AS n
                FROM model_pricing
                WHERE provider=? AND pricing_scope=? AND status='active'
                """,
                (_PROVIDER, OPENAI_API_STANDARD_SCOPE),
            ).fetchone()
        return int(row["n"] or 0) > 0

    def _save_state(
        self,
        *,
        attempt_at: str,
        success_at: str | None,
        status: str,
        source_hash: str | None,
        error: str | None,
        records_inserted: int,
    ) -> None:
        with self.repository.database.connect() as conn:
            conn.execute(
                """
                INSERT INTO pricing_refresh_state(
                    provider, last_attempt_at, last_success_at, status,
                    source_hash, error_message, records_inserted
                ) VALUES(?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(provider) DO UPDATE SET
                    last_attempt_at=excluded.last_attempt_at,
                    last_success_at=COALESCE(excluded.last_success_at, pricing_refresh_state.last_success_at),
                    status=excluded.status,
                    source_hash=COALESCE(excluded.source_hash, pricing_refresh_state.source_hash),
                    error_message=excluded.error_message,
                    records_inserted=excluded.records_inserted
                """,
                (
                    _PROVIDER,
                    attempt_at,
                    success_at,
                    status,
                    source_hash,
                    error,
                    records_inserted,
                ),
            )

    def refresh(self, *, force: bool = False) -> PricingRefreshResult:
        current = self.now().astimezone(timezone.utc)
        current_iso = current.isoformat()
        state = self._state()
        last_success_at = str(state["last_success_at"]) if state and state["last_success_at"] else None
        last_success = _parse_timestamp(last_success_at)

        if not force and last_success is not None and current - last_success < self.ttl:
            return PricingRefreshResult(
                status="fresh",
                models_checked=0,
                records_inserted=0,
                used_last_known_good=True,
                last_success_at=last_success_at,
                error=None,
            )

        try:
            pages: dict[str, str] = {}
            parsed: dict[str, _ModelPrices] = {}
            for model, url in _MODEL_URLS.items():
                text = self.fetch_text(url)
                pages[model] = text
                parsed[model] = _parse_model_prices(text)

            combined = "\n".join(
                f"{model}\n{pages[model]}" for model in sorted(pages)
            )
            combined_hash = hashlib.sha256(combined.encode("utf-8")).hexdigest()
            previous_hash = str(state["source_hash"]) if state and state["source_hash"] else None
            if previous_hash == combined_hash and last_success_at is not None:
                self._save_state(
                    attempt_at=current_iso,
                    success_at=current_iso,
                    status="unchanged",
                    source_hash=combined_hash,
                    error=None,
                    records_inserted=0,
                )
                return PricingRefreshResult(
                    status="unchanged",
                    models_checked=len(parsed),
                    records_inserted=0,
                    used_last_known_good=True,
                    last_success_at=current_iso,
                    error=None,
                )

            catalog = PricingCatalog(self.repository)
            source_version = f"openai-model-pages-observed-{current.date().isoformat()}"
            inserted = 0
            for model, prices in parsed.items():
                page_hash = hashlib.sha256(pages[model].encode("utf-8")).hexdigest()
                short_cache_write = prices.input_per_1m_usd * 1.25
                records = (
                    (
                        "short",
                        prices.input_per_1m_usd,
                        prices.cached_input_per_1m_usd,
                        short_cache_write,
                        prices.output_per_1m_usd,
                    ),
                    (
                        "long",
                        prices.input_per_1m_usd * 2.0,
                        prices.cached_input_per_1m_usd * 2.0,
                        short_cache_write * 2.0,
                        prices.output_per_1m_usd * 1.5,
                    ),
                )
                for context_type, input_price, cached_price, cache_write, output_price in records:
                    if catalog.add_price(
                        provider=_PROVIDER,
                        model=model,
                        pricing_scope=OPENAI_API_STANDARD_SCOPE,
                        service_tier="standard",
                        context_type=context_type,
                        input_per_1m_usd=input_price,
                        cached_input_per_1m_usd=cached_price,
                        cache_write_per_1m_usd=cache_write,
                        output_per_1m_usd=output_price,
                        valid_from=current.date(),
                        valid_to=None,
                        valid_from_basis="catalog_observed",
                        source_url=_MODEL_URLS[model],
                        source_version=source_version,
                        source_hash=page_hash,
                    ):
                        inserted += 1

            self._save_state(
                attempt_at=current_iso,
                success_at=current_iso,
                status="updated" if inserted else "unchanged",
                source_hash=combined_hash,
                error=None,
                records_inserted=inserted,
            )
            return PricingRefreshResult(
                status="updated" if inserted else "unchanged",
                models_checked=len(parsed),
                records_inserted=inserted,
                used_last_known_good=False,
                last_success_at=current_iso,
                error=None,
            )
        except (OSError, ValueError, UnicodeError) as exc:
            if not self._has_catalog():
                install_builtin_openai_catalog(self.repository)
            fallback = self._has_catalog()
            self._save_state(
                attempt_at=current_iso,
                success_at=None,
                status="failed",
                source_hash=None,
                error=str(exc),
                records_inserted=0,
            )
            preserved_state = self._state()
            preserved_success = (
                str(preserved_state["last_success_at"])
                if preserved_state and preserved_state["last_success_at"]
                else None
            )
            return PricingRefreshResult(
                status="failed",
                models_checked=0,
                records_inserted=0,
                used_last_known_good=fallback,
                last_success_at=preserved_success,
                error=str(exc),
            )


def refresh_openai_pricing(
    repository: Repository,
    *,
    force: bool = False,
) -> PricingRefreshResult:
    return OpenAIPricingRefresher(repository).refresh(force=force)
