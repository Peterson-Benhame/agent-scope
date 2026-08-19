from datetime import date

from agentscope.costs.calculator import calculate_token_usage_costs
from agentscope.domain.models import NormalizedSession, NormalizedTokenUsage
from agentscope.pricing.catalog import install_official_openai_history
from agentscope.storage.database import Database
from agentscope.storage.repository import Repository
from agentscope.usage_context import SessionUsageContext, persist_session_usage_context


def _repo(tmp_path):
    db = Database(tmp_path / "agentscope.db")
    db.initialize()
    return Repository(db)


def _usage(repo, session_key, model, timestamp):
    session_id = repo.upsert_session(
        NormalizedSession(
            external_session_id=session_key,
            source="codex",
            model=model,
            started_at=timestamp,
        )
    )
    persist_session_usage_context(
        repo,
        session_id,
        SessionUsageContext(provider="openai", product="codex", client="vscode"),
    )
    repo.insert_token_usage(
        session_id,
        None,
        NormalizedTokenUsage(
            timestamp=timestamp,
            session_external_id=session_key,
            model=model,
            input_tokens=1000,
            cached_input_tokens=100,
            cache_write_input_tokens=0,
            output_tokens=100,
            total_tokens=1100,
            source_file=f"{session_key}.jsonl",
            source_line=1,
        ),
    )


def test_cost_calculation_only_scans_requested_local_date_range(tmp_path):
    repo = _repo(tmp_path)
    install_official_openai_history(repo)
    _usage(repo, "feb-legacy", None, "2026-02-03T12:00:00Z")
    _usage(repo, "aug-inside", "gpt-5.6-terra", "2026-08-18T12:00:00Z")
    _usage(repo, "aug-outside", "gpt-5.6-sol", "2026-08-10T12:00:00Z")

    result = calculate_token_usage_costs(
        repo,
        utc_offset_minutes=-180,
        from_date=date(2026, 8, 13),
        to_date=date(2026, 8, 19),
    )

    assert result.events_scanned == 1
    assert result.events_priced == 1
    assert result.events_unpriced == 0
    assert result.complete is True
    assert set(result.by_model) == {"gpt-5.6-terra"}
    assert result.total_estimated_cost_usd is not None


def test_cost_calculation_uses_local_day_at_period_boundary(tmp_path):
    repo = _repo(tmp_path)
    install_official_openai_history(repo)
    _usage(repo, "local-aug18", "gpt-5.6-sol", "2026-08-19T00:10:00Z")

    result = calculate_token_usage_costs(
        repo,
        utc_offset_minutes=-180,
        from_date=date(2026, 8, 18),
        to_date=date(2026, 8, 18),
    )

    assert result.events_scanned == 1
    assert result.events_priced == 1
