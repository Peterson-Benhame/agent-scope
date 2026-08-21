from datetime import date

import pytest

from agentscope.analytics.dashboard import DashboardAnalyticsService
from agentscope.analytics.filters import AnalyticsFilter
from agentscope.domain.models import NormalizedSession, NormalizedTokenUsage
from agentscope.storage.database import Database
from agentscope.storage.repository import Repository
from agentscope.usage_context import SessionUsageContext, persist_session_usage_context


def _repo(tmp_path):
    db = Database(tmp_path / "agentscope.db")
    db.initialize()
    repo = Repository(db)

    def add_session(external_id, client, tokens, hour, project="demo"):
        session_id = repo.upsert_session(
            NormalizedSession(
                external_session_id=external_id,
                source="codex",
                project_path=f"/work/{project}",
                model="gpt-5.6-sol",
                started_at=f"2026-08-18T{hour:02d}:00:00Z",
            )
        )
        if client is not None:
            persist_session_usage_context(
                repo,
                session_id,
                SessionUsageContext(
                    provider="openai",
                    product="codex",
                    client=client,
                    client_confidence="explicit",
                ),
            )
        repo.insert_token_usage(
            session_id,
            None,
            NormalizedTokenUsage(
                timestamp=f"2026-08-18T{hour:02d}:05:00Z",
                model="gpt-5.6-sol",
                input_tokens=tokens,
                cached_input_tokens=0,
                cache_write_input_tokens=0,
                output_tokens=0,
                total_tokens=tokens,
                source_file=f"{external_id}.jsonl",
                source_line=1,
            ),
        )

    add_session("vscode-1", "vscode", 100, 10)
    add_session("vscode-2", "vscode", 300, 11)
    add_session("cli-1", "cli", 100, 12)
    add_session("unknown-1", None, 500, 13)
    add_session("excluded", "web", 1_000, 14, project="other")
    return repo


def _filters():
    return AnalyticsFilter(
        from_date=date(2026, 8, 18),
        to_date=date(2026, 8, 18),
        project="demo",
        source="codex",
        utc_offset_minutes=0,
    )


def test_client_breakdown_uses_persisted_client_and_keeps_unknown_context(tmp_path):
    rows = DashboardAnalyticsService(_repo(tmp_path), _filters()).by_client()
    by_client = {row["client"]: row for row in rows}

    assert by_client["vscode"] == {
        "client": "vscode",
        "sessions": 2,
        "total_tokens": 400,
        "share": pytest.approx(0.4),
    }
    assert by_client["cli"] == {
        "client": "cli",
        "sessions": 1,
        "total_tokens": 100,
        "share": pytest.approx(0.1),
    }
    assert by_client["unknown"] == {
        "client": "unknown",
        "sessions": 1,
        "total_tokens": 500,
        "share": pytest.approx(0.5),
    }
    assert "web" not in by_client
    assert sum(row["total_tokens"] for row in rows) == 1_000
    assert sum(row["share"] for row in rows) == pytest.approx(1.0)


def test_client_breakdown_respects_model_filter(tmp_path):
    repo = _repo(tmp_path)
    rows = DashboardAnalyticsService(
        repo,
        AnalyticsFilter(
            from_date=date(2026, 8, 18),
            to_date=date(2026, 8, 18),
            project="demo",
            source="codex",
            model="gpt-5.6-sol",
            utc_offset_minutes=0,
        ),
    ).by_client()

    assert {row["client"] for row in rows} == {"vscode", "cli", "unknown"}
