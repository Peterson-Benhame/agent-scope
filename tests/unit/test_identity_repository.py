from agentscope.domain.models import (
    IdentityConfidence,
    NormalizedMachine,
    NormalizedSession,
    NormalizedUser,
)
from agentscope.storage.database import Database
from agentscope.storage.repository import Repository


def test_user_and_machine_upserts_are_stable_by_key(tmp_path):
    db = Database(tmp_path / "agentscope.db")
    db.initialize()
    repo = Repository(db)

    first_user = repo.upsert_user(
        NormalizedUser(
            stable_key="user-1",
            display_name="Peterson",
            confidence=IdentityConfidence.INFERRED,
        )
    )
    second_user = repo.upsert_user(
        NormalizedUser(
            stable_key="user-1",
            display_name="Peterson B.",
            confidence=IdentityConfidence.INFERRED,
        )
    )
    first_machine = repo.upsert_machine(
        NormalizedMachine(stable_key="machine-1", display_name="Notebook")
    )
    second_machine = repo.upsert_machine(
        NormalizedMachine(stable_key="machine-1", display_name="Notebook novo")
    )

    assert first_user == second_user
    assert first_machine == second_machine
    with db.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 1
        assert conn.execute("SELECT display_name FROM users").fetchone()[0] == "Peterson B."
        assert conn.execute("SELECT COUNT(*) FROM machines").fetchone()[0] == 1
        assert conn.execute("SELECT display_name FROM machines").fetchone()[0] == "Notebook novo"


def test_session_identity_association_keeps_user_and_machine_separate(tmp_path):
    db = Database(tmp_path / "agentscope.db")
    db.initialize()
    repo = Repository(db)
    session_id = repo.upsert_session(
        NormalizedSession(external_session_id="s1", source="codex")
    )
    user_id = repo.upsert_user(NormalizedUser(stable_key="user-1"))
    machine_id = repo.upsert_machine(NormalizedMachine(stable_key="machine-1"))

    repo.associate_session_identity(session_id, user_id, machine_id)

    with db.connect() as conn:
        row = conn.execute(
            "SELECT user_id, machine_id FROM sessions WHERE id=?", (session_id,)
        ).fetchone()
    assert row[0] == user_id
    assert row[1] == machine_id
    assert user_id != machine_id or row[0] is not row[1]
