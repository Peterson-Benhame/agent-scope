from datetime import date

from agentscope.pricing.catalog import (
    OPENAI_API_STANDARD_SCOPE,
    PricingCatalog,
    install_official_openai_history,
)
from agentscope.storage.database import Database
from agentscope.storage.repository import Repository


def _repo(tmp_path):
    db = Database(tmp_path / "agentscope.db")
    db.initialize()
    return Repository(db)


def _lookup(catalog, model, on_date, context_type="short"):
    return catalog.lookup(
        provider="openai",
        model=model,
        pricing_scope=OPENAI_API_STANDARD_SCOPE,
        service_tier="standard",
        context_type=context_type,
        on_date=on_date,
    )


def test_official_history_tracks_launch_and_july_30_price_change(tmp_path):
    repo = _repo(tmp_path)

    inserted = install_official_openai_history(repo)
    second = install_official_openai_history(repo)

    assert inserted == 10
    assert second == 0

    catalog = PricingCatalog(repo)
    terra_launch = _lookup(catalog, "gpt-5.6-terra", date(2026, 7, 29))
    terra_reduced = _lookup(catalog, "gpt-5.6-terra", date(2026, 7, 30))
    luna_launch = _lookup(catalog, "gpt-5.6-luna", date(2026, 7, 29))
    luna_reduced = _lookup(catalog, "gpt-5.6-luna", date(2026, 7, 30))
    sol_august = _lookup(catalog, "gpt-5.6-sol", date(2026, 8, 18))

    assert terra_launch is not None
    assert (terra_launch.input_per_1m_usd, terra_launch.cached_input_per_1m_usd) == (2.5, 0.25)
    assert (terra_launch.cache_write_per_1m_usd, terra_launch.output_per_1m_usd) == (3.125, 15.0)
    assert terra_launch.valid_from == date(2026, 7, 9)
    assert terra_launch.valid_to == date(2026, 7, 29)
    assert terra_launch.valid_from_basis == "provider_declared"

    assert terra_reduced is not None
    assert (terra_reduced.input_per_1m_usd, terra_reduced.cached_input_per_1m_usd) == (2.0, 0.2)
    assert (terra_reduced.cache_write_per_1m_usd, terra_reduced.output_per_1m_usd) == (2.5, 12.0)
    assert terra_reduced.valid_from == date(2026, 7, 30)
    assert terra_reduced.valid_to is None

    assert luna_launch is not None
    assert (luna_launch.input_per_1m_usd, luna_launch.cached_input_per_1m_usd) == (1.0, 0.1)
    assert (luna_launch.cache_write_per_1m_usd, luna_launch.output_per_1m_usd) == (1.25, 6.0)

    assert luna_reduced is not None
    assert (luna_reduced.input_per_1m_usd, luna_reduced.cached_input_per_1m_usd) == (0.2, 0.02)
    assert (luna_reduced.cache_write_per_1m_usd, luna_reduced.output_per_1m_usd) == (0.25, 1.2)

    assert sol_august is not None
    assert (sol_august.input_per_1m_usd, sol_august.cached_input_per_1m_usd) == (5.0, 0.5)
    assert (sol_august.cache_write_per_1m_usd, sol_august.output_per_1m_usd) == (6.25, 30.0)
    assert sol_august.valid_from == date(2026, 7, 9)


def test_official_history_has_long_context_rates(tmp_path):
    repo = _repo(tmp_path)
    install_official_openai_history(repo)
    catalog = PricingCatalog(repo)

    terra_long = _lookup(
        catalog,
        "gpt-5.6-terra",
        date(2026, 8, 18),
        context_type="long",
    )

    assert terra_long is not None
    assert (terra_long.input_per_1m_usd, terra_long.cached_input_per_1m_usd) == (4.0, 0.4)
    assert (terra_long.cache_write_per_1m_usd, terra_long.output_per_1m_usd) == (5.0, 18.0)
