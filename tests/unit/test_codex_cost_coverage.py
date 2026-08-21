from __future__ import annotations

import pytest

from agentscope.costs.calculator import calculate_token_usage_costs
from agentscope.storage.database import Database
from agentscope.storage.repository import Repository
from agentscope.usage_context_backfill import backfill_usage_context


def _repo_with_codex_usage(tmp_path, model: str) -> Repository:
    db = Database(tmp_path / f"{model.replace('/', '-')}.db")
    db.initialize()
    repo = Repository(db)
    with db.connect() as conn:
        conn.execute("INSERT INTO sources(name, type) VALUES('codex', 'agent')")
        source_id = conn.execute(
            "SELECT id FROM sources WHERE name='codex'"
        ).fetchone()[0]
        conn.execute(
            "INSERT INTO models(provider, name) VALUES('openai', ?)",
            (model,),
        )
        model_id = conn.execute(
            "SELECT id FROM models WHERE name=?",
            (model,),
        ).fetchone()[0]
        conn.execute(
            """
            INSERT INTO sessions(
                source_id, external_session_id, started_at, ended_at,
                model_id, provider, metadata_json
            ) VALUES(?, ?, ?, ?, ?, NULL, '{}')
            """,
            (
                source_id,
                f"session-{model}",
                "2026-08-20T10:00:00Z",
                "2026-08-20T10:10:00Z",
                model_id,
            ),
        )
        session_id = conn.execute(
            "SELECT id FROM sessions WHERE external_session_id=?",
            (f"session-{model}",),
        ).fetchone()[0]
        conn.execute(
            """
            INSERT INTO token_usage(
                session_id, timestamp, model_id,
                input_tokens, cached_input_tokens, cache_write_input_tokens,
                output_tokens, total_tokens, event_key
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session_id,
                "2026-08-20T10:05:00Z",
                model_id,
                1_000_000,
                200_000,
                0,
                100_000,
                1_100_000,
                f"usage-{model}",
            ),
        )
    return repo


@pytest.mark.parametrize(
    ("model", "expected_cost"),
    [
        ("gpt-5.4", 3.55),
        ("gpt-5.5", 7.10),
        ("gpt-5.4-mini", 1.065),
        ("gpt-5.3-codex", 2.835),
        ("codex-auto-review", 3.55),
    ],
)
def test_codex_models_are_priced_after_context_backfill(tmp_path, model, expected_cost):
    repo = _repo_with_codex_usage(tmp_path, model)

    backfill = backfill_usage_context(repo, sources=frozenset({"codex"}))
    result = calculate_token_usage_costs(
        repo,
        utc_offset_minutes=0,
    )

    assert backfill.sessions_updated == 1
    assert result.events_scanned == 1
    assert result.events_priced == 1
    assert result.events_unpriced == 0
    assert result.by_model[model] == pytest.approx(expected_cost)

    with repo.database.connect() as conn:
        row = conn.execute(
            """
            SELECT c.estimated_raw_cost_usd, c.pricing_source, c.pricing_version,
                   m.name AS local_model
            FROM costs c
            JOIN models m ON m.id=c.model_id
            WHERE c.event_key=?
            """,
            (f"token_usage_cost:{1}",),
        ).fetchone()

    assert row is not None
    assert row["estimated_raw_cost_usd"] == pytest.approx(expected_cost)
    assert row["pricing_source"]
    assert row["pricing_version"]
    assert row["local_model"] == model


def test_auto_review_keeps_activity_label_but_uses_gpt54_price_provenance(tmp_path):
    repo = _repo_with_codex_usage(tmp_path, "codex-auto-review")
    backfill_usage_context(repo, sources=frozenset({"codex"}))

    calculate_token_usage_costs(repo, utc_offset_minutes=0)

    with repo.database.connect() as conn:
        row = conn.execute(
            """
            SELECT c.pricing_source, c.pricing_version, m.name AS local_model
            FROM costs c
            JOIN models m ON m.id=c.model_id
            LIMIT 1
            """
        ).fetchone()

    assert row["local_model"] == "codex-auto-review"
    assert "gpt-5-4" in str(row["pricing_version"]).lower()
