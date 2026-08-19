import json
from pathlib import Path

from agentscope.collectors.codex import collect_codex_rollout
from agentscope.costs.calculator import calculate_token_usage_costs
from agentscope.domain.models import NormalizedSession, NormalizedTokenUsage
from agentscope.storage.database import Database
from agentscope.storage.repository import Repository
from agentscope.usage_context import SessionUsageContext, persist_session_usage_context


FIXTURE = Path("tests/fixtures/codex/rollout.jsonl")


def _write_rollout_without_token_count(path: Path) -> None:
    events = [
        {
            "timestamp": "2026-08-18T10:00:00Z",
            "type": "session_meta",
            "payload": {
                "session_id": "fallback-session",
                "timestamp": "2026-08-18T10:00:00Z",
                "cwd": r"C:\work\fallback",
                "originator": "codex_vscode",
                "source": "vscode",
                "model_provider": "headroom",
            },
        },
        {
            "timestamp": "2026-08-18T10:00:01Z",
            "type": "turn_context",
            "payload": {
                "turn_id": "turn-1",
                "model": "gpt-5.6-sol",
            },
        },
        {
            "timestamp": "2026-08-18T10:00:02Z",
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": "Implement a small feature."}],
            },
        },
        {
            "timestamp": "2026-08-18T10:00:03Z",
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": "I implemented the feature."}],
            },
        },
    ]
    path.write_text(
        "\n".join(json.dumps(event) for event in events) + "\n",
        encoding="utf-8",
    )


def test_source_reported_tokens_remain_authoritative():
    data = collect_codex_rollout(FIXTURE)

    assert len(data.token_usage) == 1
    usage = data.token_usage[0]
    assert usage.input_tokens == 18019
    assert usage.cached_input_tokens == 17152
    assert usage.output_tokens == 223
    assert getattr(usage, "token_source", None) == "source_reported"


def test_tiktoken_fallback_is_created_only_when_source_has_no_token_count(tmp_path):
    rollout = tmp_path / "rollout.jsonl"
    _write_rollout_without_token_count(rollout)

    data = collect_codex_rollout(rollout)

    assert len(data.token_usage) == 1
    usage = data.token_usage[0]
    assert getattr(usage, "token_source", None) == "tiktoken_estimate"
    assert usage.input_tokens is not None and usage.input_tokens > 0
    assert usage.output_tokens is not None and usage.output_tokens > 0
    assert usage.total_tokens == usage.input_tokens + usage.output_tokens
    assert usage.cached_input_tokens is None
    assert usage.cache_write_input_tokens is None
    assert usage.reasoning_output_tokens is None
    assert usage.model == "gpt-5.6-sol"


def test_database_migration_adds_token_source_with_source_reported_default(tmp_path):
    db = Database(tmp_path / "agentscope.db")
    db.initialize()

    with db.connect() as conn:
        columns = {str(row[1]) for row in conn.execute("PRAGMA table_info(token_usage)")}
        versions = [
            int(row[0])
            for row in conn.execute(
                "SELECT version FROM schema_migrations ORDER BY version"
            )
        ]

    assert "token_source" in columns
    assert 5 in versions


def test_repository_persists_fallback_provenance_idempotently(tmp_path):
    db = Database(tmp_path / "agentscope.db")
    db.initialize()
    repo = Repository(db)
    session_id = repo.upsert_session(
        NormalizedSession(
            external_session_id="fallback",
            source="codex",
            model="gpt-5.6-sol",
        )
    )
    usage = NormalizedTokenUsage(
        timestamp="2026-08-18T10:00:00Z",
        model="gpt-5.6-sol",
        input_tokens=10,
        output_tokens=5,
        total_tokens=15,
        source_file="fallback.jsonl",
        source_line=0,
    )
    setattr(usage, "token_source", "tiktoken_estimate")

    first = repo.insert_token_usage(session_id, None, usage)
    second = repo.insert_token_usage(session_id, None, usage)

    with db.connect() as conn:
        row = conn.execute(
            "SELECT id, token_source FROM token_usage WHERE id=?",
            (first,),
        ).fetchone()
        count = conn.execute("SELECT COUNT(*) FROM token_usage").fetchone()[0]

    assert second == first
    assert count == 1
    assert row["token_source"] == "tiktoken_estimate"


def test_cost_calculator_never_prices_tiktoken_estimates(tmp_path):
    db = Database(tmp_path / "agentscope.db")
    db.initialize()
    repo = Repository(db)
    with db.connect() as conn:
        columns = {str(row[1]) for row in conn.execute("PRAGMA table_info(token_usage)")}
        if "token_source" not in columns:
            conn.execute(
                "ALTER TABLE token_usage ADD COLUMN token_source TEXT NOT NULL DEFAULT 'source_reported'"
            )

    session_id = repo.upsert_session(
        NormalizedSession(
            external_session_id="estimated-session",
            source="codex",
            provider="headroom",
            model="gpt-5.6-sol",
            started_at="2026-08-18T10:00:00Z",
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
    usage_id = repo.insert_token_usage(
        session_id,
        None,
        NormalizedTokenUsage(
            timestamp="2026-08-18T10:00:00Z",
            model="gpt-5.6-sol",
            input_tokens=1_000,
            cached_input_tokens=0,
            cache_write_input_tokens=0,
            output_tokens=100,
            total_tokens=1_100,
            source_file="estimated.jsonl",
            source_line=1,
        ),
    )
    with db.connect() as conn:
        conn.execute(
            "UPDATE token_usage SET token_source='tiktoken_estimate' WHERE id=?",
            (usage_id,),
        )

    summary = calculate_token_usage_costs(repo, utc_offset_minutes=0)

    assert summary.events_scanned == 1
    assert summary.events_priced == 0
    assert summary.events_unpriced == 1
    assert summary.complete is False
    assert summary.total_estimated_cost_usd is None
    assert summary.unpriced_reasons == {"estimated_token_usage": 1}
