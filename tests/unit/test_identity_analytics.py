from agentscope.analytics.filters import AnalyticsFilter
from agentscope.analytics.service import AnalyticsService
from agentscope.domain.models import NormalizedMachine, NormalizedSession, NormalizedUser
from agentscope.storage.database import Database
from agentscope.storage.repository import Repository


def populated_identity_db(tmp_path):
    db = Database(tmp_path / "agentscope.db")
    db.initialize()
    repo = Repository(db)
    user_id = repo.upsert_user(
        NormalizedUser(stable_key="user-a", display_name="Dev A")
    )
    machine_id = repo.upsert_machine(
        NormalizedMachine(stable_key="machine-a", display_name="Notebook A")
    )
    session_id = repo.upsert_session(
        NormalizedSession(
            external_session_id="session-a",
            source="codex",
            started_at="2026-08-18T10:00:00Z",
        )
    )
    repo.associate_session_identity(session_id, user_id, machine_id)
    with db.connect() as conn:
        conn.execute(
            """
            INSERT INTO token_usage(
                session_id, timestamp, input_tokens, cached_input_tokens,
                output_tokens, total_tokens, event_key
            ) VALUES(?, '2026-08-18T10:01:00Z', 1000, 800, 200, 1200, 'token-a')
            """,
            (session_id,),
        )
        conn.execute(
            """
            INSERT INTO costs(session_id, period_start, observed_cost_usd, event_key)
            VALUES(?, '2026-08-18T10:00:00Z', 1.25, 'cost-a')
            """,
            (session_id,),
        )
    return repo


def test_usage_can_be_grouped_by_user_and_machine(tmp_path):
    repo = populated_identity_db(tmp_path)
    analytics = AnalyticsService(repo)

    users = analytics.by_user()
    machines = analytics.by_machine()

    assert users == [
        {
            "user": "Dev A",
            "sessions": 1,
            "input_tokens": 1000,
            "cached_input_tokens": 800,
            "output_tokens": 200,
            "total_tokens": 1200,
            "observed_cost_usd": 1.25,
        }
    ]
    assert machines == [
        {
            "machine": "Notebook A",
            "sessions": 1,
            "input_tokens": 1000,
            "cached_input_tokens": 800,
            "output_tokens": 200,
            "total_tokens": 1200,
            "observed_cost_usd": 1.25,
        }
    ]


def test_user_and_machine_filters_apply_to_summary(tmp_path):
    repo = populated_identity_db(tmp_path)

    matching = AnalyticsService(
        repo,
        AnalyticsFilter(user="Dev A", machine="Notebook A"),
    ).summary()
    missing_user = AnalyticsService(
        repo,
        AnalyticsFilter(user="Missing"),
    ).summary()
    missing_machine = AnalyticsService(
        repo,
        AnalyticsFilter(machine="Missing"),
    ).summary()

    assert matching.input_tokens == 1000
    assert matching.observed_cost_usd == 1.25
    assert missing_user.input_tokens == 0
    assert missing_machine.input_tokens == 0
