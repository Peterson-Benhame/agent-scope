from agentscope.analytics.service import AnalyticsService
from agentscope.domain.models import NormalizedMachine, NormalizedSession, NormalizedUser
from agentscope.reporting.export import export_datasets
from agentscope.reporting.html_report import generate_html_report
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
                session_id, timestamp, input_tokens, total_tokens, event_key
            ) VALUES(?, '2026-08-18T10:01:00Z', 1000, 1000, 'token-a')
            """,
            (session_id,),
        )
    return repo


def test_html_report_contains_user_and_machine_sections(tmp_path):
    repo = populated_identity_db(tmp_path)
    target = tmp_path / "report.html"

    generate_html_report(repo, AnalyticsService(repo), target)
    text = target.read_text(encoding="utf-8")

    assert "Usuários" in text
    assert "Máquinas" in text
    assert "Dev A" in text
    assert "Notebook A" in text


def test_safe_export_includes_identity_dimensions_without_raw_paths(tmp_path):
    repo = populated_identity_db(tmp_path)
    output = tmp_path / "reports"

    created = export_datasets(repo, AnalyticsService(repo), output)
    names = {path.name for path in created}

    assert "usage_by_user.csv" in names
    assert "usage_by_machine.csv" in names
    sessions = (output / "sessions.csv").read_text(encoding="utf-8")
    users = (output / "usage_by_user.csv").read_text(encoding="utf-8")
    machines = (output / "usage_by_machine.csv").read_text(encoding="utf-8")
    assert "Dev A" in sessions
    assert "Notebook A" in sessions
    assert "user-a" in sessions
    assert "machine-a" in sessions
    assert "Dev A" in users
    assert "Notebook A" in machines
    assert str(tmp_path) not in sessions
