from datetime import datetime, timezone

from agentscope.pricing.catalog import OPENAI_API_STANDARD_SCOPE, PricingCatalog
from agentscope.pricing.refresh import OpenAIPricingRefresher
from agentscope.storage.database import Database
from agentscope.storage.repository import Repository


MODEL_PAGE = """
# GPT-5.6 {name}

## Pricing

Text tokens
Per 1M tokens

Input
${input_price}

Cached input
${cached_price}

Output
${output_price}

Prompts with >272K input tokens are priced at 2x input and 1.5x output for the full request.
Cache writes are billed at 1.25x the uncached input token rate.
"""


def _repo(tmp_path):
    db = Database(tmp_path / "agentscope.db")
    db.initialize()
    return db, Repository(db)


def _pages():
    return {
        "gpt-5.6-sol": MODEL_PAGE.format(
            name="Sol", input_price="5.00", cached_price="0.50", output_price="30.00"
        ),
        "gpt-5.6-terra": MODEL_PAGE.format(
            name="Terra", input_price="2.00", cached_price="0.20", output_price="12.00"
        ),
        "gpt-5.6-luna": MODEL_PAGE.format(
            name="Luna", input_price="0.20", cached_price="0.02", output_price="1.20"
        ),
    }


def test_refresh_parses_official_model_pages_and_persists_short_and_long_context(tmp_path):
    _, repo = _repo(tmp_path)
    pages = _pages()
    calls = []

    def fetch(url):
        model = url.rsplit("/", 1)[-1].removesuffix(".md")
        calls.append(model)
        return pages[model]

    refresher = OpenAIPricingRefresher(
        repo,
        fetch_text=fetch,
        now=lambda: datetime(2026, 8, 19, 21, 0, tzinfo=timezone.utc),
    )

    result = refresher.refresh(force=True)

    assert result.status == "updated"
    assert result.models_checked == 3
    assert result.records_inserted == 6
    assert result.used_last_known_good is False
    assert sorted(calls) == ["gpt-5.6-luna", "gpt-5.6-sol", "gpt-5.6-terra"]

    catalog = PricingCatalog(repo)
    terra = catalog.lookup(
        provider="openai",
        model="gpt-5.6-terra",
        pricing_scope=OPENAI_API_STANDARD_SCOPE,
        service_tier="standard",
        context_type="short",
        on_date=datetime(2026, 8, 19).date(),
    )
    terra_long = catalog.lookup(
        provider="openai",
        model="gpt-5.6-terra",
        pricing_scope=OPENAI_API_STANDARD_SCOPE,
        service_tier="standard",
        context_type="long",
        on_date=datetime(2026, 8, 19).date(),
    )

    assert terra is not None
    assert (terra.input_per_1m_usd, terra.cached_input_per_1m_usd) == (2.0, 0.2)
    assert (terra.cache_write_per_1m_usd, terra.output_per_1m_usd) == (2.5, 12.0)
    assert terra_long is not None
    assert (terra_long.input_per_1m_usd, terra_long.cached_input_per_1m_usd) == (4.0, 0.4)
    assert (terra_long.cache_write_per_1m_usd, terra_long.output_per_1m_usd) == (5.0, 18.0)


def test_refresh_keeps_last_known_good_when_remote_source_fails(tmp_path):
    db, repo = _repo(tmp_path)
    pages = _pages()
    first = OpenAIPricingRefresher(
        repo,
        fetch_text=lambda url: pages[url.rsplit("/", 1)[-1].removesuffix(".md")],
        now=lambda: datetime(2026, 8, 19, 21, 0, tzinfo=timezone.utc),
    ).refresh(force=True)
    assert first.status == "updated"

    def fail(_url):
        raise OSError("offline")

    failed = OpenAIPricingRefresher(
        repo,
        fetch_text=fail,
        now=lambda: datetime(2026, 8, 20, 22, 0, tzinfo=timezone.utc),
    ).refresh(force=True)

    assert failed.status == "failed"
    assert failed.records_inserted == 0
    assert failed.used_last_known_good is True
    assert "offline" in (failed.error or "")
    with db.connect() as conn:
        count = conn.execute("SELECT COUNT(*) FROM model_pricing").fetchone()[0]
        state = conn.execute(
            "SELECT status, error_message FROM pricing_refresh_state WHERE provider='openai'"
        ).fetchone()
    assert count == 6
    assert state["status"] == "failed"
    assert "offline" in state["error_message"]


def test_refresh_skips_network_when_last_success_is_fresh(tmp_path):
    _, repo = _repo(tmp_path)
    pages = _pages()
    first_calls = []

    def first_fetch(url):
        first_calls.append(url)
        return pages[url.rsplit("/", 1)[-1].removesuffix(".md")]

    OpenAIPricingRefresher(
        repo,
        fetch_text=first_fetch,
        now=lambda: datetime(2026, 8, 19, 10, 0, tzinfo=timezone.utc),
    ).refresh(force=True)
    assert len(first_calls) == 3

    second_calls = []
    result = OpenAIPricingRefresher(
        repo,
        fetch_text=lambda url: second_calls.append(url) or "unexpected",
        now=lambda: datetime(2026, 8, 19, 18, 0, tzinfo=timezone.utc),
    ).refresh(force=False)

    assert result.status == "fresh"
    assert result.records_inserted == 0
    assert second_calls == []
