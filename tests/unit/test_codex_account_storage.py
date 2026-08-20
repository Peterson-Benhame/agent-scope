from agentscope.codex_account.models import AttributionConfidence, BillingSource
from agentscope.storage.database import Database


def test_codex_account_schema_is_additive_and_secret_free(tmp_path):
    db = Database(tmp_path / "agentscope.db")
    db.initialize()
    with db.connect() as conn:
        versions = {row[0] for row in conn.execute("SELECT version FROM schema_migrations")}
        account_cols = {
            row[1]
            for row in conn.execute("PRAGMA table_info(codex_account_usage_snapshots)")
        }
        thread_cols = {
            row[1]
            for row in conn.execute("PRAGMA table_info(codex_thread_usage_snapshots)")
        }
        group_cols = {
            row[1]
            for row in conn.execute("PRAGMA table_info(codex_thread_usage_groups)")
        }

    assert 6 in versions
    assert {
        "captured_at",
        "plan_type",
        "credits_balance",
        "primary_used_percent",
    } <= account_cols
    assert {
        "thread_id",
        "session_id",
        "estimated_usage_credits_micros",
        "estimated_usage_usd_micros",
    } <= thread_cols
    assert {"model", "cached_input_tokens", "output_tokens", "total_tokens"} <= group_cols
    forbidden = {
        "access_token",
        "refresh_token",
        "cookie",
        "api_key",
        "email",
        "raw_json",
        "raw_response",
    }
    assert not forbidden.intersection(account_cols | thread_cols | group_cols)
    assert BillingSource.UNKNOWN.value == "unknown"
    assert AttributionConfidence.INFERRED_HIGH.value == "inferred_high"
