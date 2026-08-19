from agentscope.config import AgentScopeConfig
from agentscope.domain.models import IdentityConfidence
from agentscope.identity import resolve_local_identity


def test_local_identity_uses_separate_stable_user_and_machine_keys(monkeypatch, tmp_path):
    monkeypatch.setattr("agentscope.identity.getpass.getuser", lambda: "peter")
    monkeypatch.setattr("agentscope.identity.platform.node", lambda: "DEV-NOTEBOOK")
    monkeypatch.setattr("agentscope.identity.platform.system", lambda: "Windows")
    monkeypatch.setattr("agentscope.identity.platform.machine", lambda: "AMD64")
    config = AgentScopeConfig.from_env(base_dir=tmp_path)

    user, machine = resolve_local_identity(config)

    assert user.stable_key.startswith("local-user:")
    assert machine.stable_key.startswith("local-machine:")
    assert user.stable_key != machine.stable_key
    assert user.display_name == "peter"
    assert machine.display_name == "DEV-NOTEBOOK"
    assert user.confidence is IdentityConfidence.INFERRED
    assert machine.os == "Windows"


def test_display_overrides_do_not_change_stable_identity(monkeypatch, tmp_path):
    monkeypatch.setattr("agentscope.identity.getpass.getuser", lambda: "peter")
    monkeypatch.setattr("agentscope.identity.platform.node", lambda: "DEV-NOTEBOOK")
    monkeypatch.setattr("agentscope.identity.platform.system", lambda: "Windows")
    monkeypatch.setattr("agentscope.identity.platform.machine", lambda: "AMD64")

    base = AgentScopeConfig.from_env(base_dir=tmp_path)
    renamed = AgentScopeConfig.from_env(
        base_dir=tmp_path,
        user_display_name="Peterson Benhame",
        machine_display_name="Notebook principal",
    )

    base_user, base_machine = resolve_local_identity(base)
    renamed_user, renamed_machine = resolve_local_identity(renamed)

    assert base_user.stable_key == renamed_user.stable_key
    assert base_machine.stable_key == renamed_machine.stable_key
    assert renamed_user.display_name == "Peterson Benhame"
    assert renamed_machine.display_name == "Notebook principal"


def test_identity_display_names_can_come_from_environment(monkeypatch, tmp_path):
    monkeypatch.setenv("AGENTSCOPE_USER_NAME", "Dev A")
    monkeypatch.setenv("AGENTSCOPE_MACHINE_NAME", "Estação A")

    config = AgentScopeConfig.from_env(base_dir=tmp_path)

    assert config.user_display_name == "Dev A"
    assert config.machine_display_name == "Estação A"
