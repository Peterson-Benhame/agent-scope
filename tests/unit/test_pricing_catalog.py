from datetime import date

from agentscope.pricing.catalog import (
    CODEX_WORK_REFERENCE_SCOPE,
    OPENAI_API_STANDARD_SCOPE,
    PricingCatalog,
    install_builtin_openai_catalog,
)
from agentscope.storage.database import Database
from agentscope.storage.repository import Repository


def _repo(tmp_path):
    db = Database(tmp_path / "agentscope.db")
    db.initialize()
    return db, Repository(db)


def test_database_migration_creates_versioned_model_pricing_table(tmp_path):
    db, _ = _repo(tmp_path)

    with db.connect() as conn:
        columns = {
            row[1]
            for row in conn.execute("PRAGMA table_info(model_pricing)").fetchall()
        }
        migration = conn.execute(
            "SELECT description FROM schema_migrations WHERE version=4"
        ).fetchone()

    assert {
        "provider",
        "model",
        "pricing_scope",
        "service_tier",
        "context_type",
        "input_per_1m_usd",
        "cached_input_per_1m_usd",
        "cache_write_per_1m_usd",
        "output_per_1m_usd",
        "valid_from",
        "valid_to",
        "valid_from_basis",
        "source_url",
        "source_version",
        "source_hash",
        "status",
        "record_key",
    }.issubset(columns)
    assert migration["description"] == "Add versioned model pricing catalog"


def test_builtin_catalog_installs_current_gpt_56_api_reference_prices(tmp_path):
    db, repo = _repo(tmp_path)

    inserted = install_builtin_openai_catalog(repo)
    second = install_builtin_openai_catalog(repo)

    assert inserted == 12
    assert second == 0

    catalog = PricingCatalog(repo)
    terra = catalog.lookup(
        provider="openai",
        model="gpt-5.6-terra",
        pricing_scope=OPENAI_API_STANDARD_SCOPE,
        service_tier="standard",
        context_type="short",
        on_date=date(2026, 8, 18),
    )
    luna_long = catalog.lookup(
        provider="openai",
        model="gpt-5.6-luna",
        pricing_scope=OPENAI_API_STANDARD_SCOPE,
        service_tier="standard",
        context_type="long",
        on_date=date(2026, 8, 18),
    )

    assert terra is not None
    assert terra.input_per_1m_usd == 2.0
    assert terra.cached_input_per_1m_usd == 0.20
    assert terra.cache_write_per_1m_usd == 2.50
    assert terra.output_per_1m_usd == 12.0
    assert terra.valid_from == date(2026, 7, 30)
    assert terra.valid_from_basis == "provider_declared"
    assert terra.source_version == "openai-api-2026-07-30"

    assert luna_long is not None
    assert luna_long.input_per_1m_usd == 0.40
    assert luna_long.cached_input_per_1m_usd == 0.04
    assert luna_long.cache_write_per_1m_usd == 0.50
    assert luna_long.output_per_1m_usd == 1.80


def test_codex_reference_is_observed_snapshot_not_backdated(tmp_path):
    _, repo = _repo(tmp_path)
    install_builtin_openai_catalog(repo)
    catalog = PricingCatalog(repo)

    before_observation = catalog.lookup(
        provider="openai",
        model="gpt-5.6-sol",
        pricing_scope=CODEX_WORK_REFERENCE_SCOPE,
        service_tier="standard",
        context_type="short",
        on_date=date(2026, 8, 18),
    )
    observed = catalog.lookup(
        provider="openai",
        model="gpt-5.6-sol",
        pricing_scope=CODEX_WORK_REFERENCE_SCOPE,
        service_tier="standard",
        context_type="short",
        on_date=date(2026, 8, 19),
    )

    assert before_observation is None
    assert observed is not None
    assert observed.input_per_1m_usd == 5.0
    assert observed.cached_input_per_1m_usd == 0.5
    assert observed.cache_write_per_1m_usd is None
    assert observed.output_per_1m_usd == 30.0
    assert observed.valid_from_basis == "catalog_observed"
    assert observed.source_version == "codex-work-observed-2026-08-19"


def test_new_price_version_does_not_overwrite_historical_price(tmp_path):
    db, repo = _repo(tmp_path)
    install_builtin_openai_catalog(repo)
    catalog = PricingCatalog(repo)

    inserted = catalog.add_price(
        provider="openai",
        model="gpt-5.6-terra",
        pricing_scope=OPENAI_API_STANDARD_SCOPE,
        service_tier="standard",
        context_type="short",
        input_per_1m_usd=1.50,
        cached_input_per_1m_usd=0.15,
        cache_write_per_1m_usd=1.875,
        output_per_1m_usd=9.0,
        valid_from=date(2026, 9, 1),
        valid_to=None,
        valid_from_basis="provider_declared",
        source_url="https://platform.openai.com/pricing",
        source_version="test-future-2026-09-01",
        source_hash="test-future-hash",
    )

    august = catalog.lookup(
        provider="openai",
        model="gpt-5.6-terra",
        pricing_scope=OPENAI_API_STANDARD_SCOPE,
        service_tier="standard",
        context_type="short",
        on_date=date(2026, 8, 18),
    )
    september = catalog.lookup(
        provider="openai",
        model="gpt-5.6-terra",
        pricing_scope=OPENAI_API_STANDARD_SCOPE,
        service_tier="standard",
        context_type="short",
        on_date=date(2026, 9, 2),
    )

    assert inserted is True
    assert august is not None and august.input_per_1m_usd == 2.0
    assert september is not None and september.input_per_1m_usd == 1.5
    with db.connect() as conn:
        count = conn.execute(
            """
            SELECT COUNT(*) FROM model_pricing
            WHERE provider='openai' AND model='gpt-5.6-terra'
              AND pricing_scope=? AND context_type='short'
            """,
            (OPENAI_API_STANDARD_SCOPE,),
        ).fetchone()[0]
    assert count == 2
