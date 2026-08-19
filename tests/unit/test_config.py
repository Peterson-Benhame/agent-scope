from agentscope.config import AgentScopeConfig


def test_defaults_use_user_home_and_local_project_paths(monkeypatch, tmp_path):
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "user"))
    config = AgentScopeConfig.from_env(base_dir=tmp_path / "project")
    assert config.codex_home == tmp_path / "user" / ".codex"
    assert config.headroom_home == tmp_path / "user" / ".headroom"
    assert config.database_path == tmp_path / "project" / "data" / "agentscope.db"
    assert config.reports_path == tmp_path / "project" / "reports"
    assert config.safe_mode is True


def test_explicit_paths_override_environment(monkeypatch, tmp_path):
    monkeypatch.setenv("AGENTSCOPE_CODEX_HOME", str(tmp_path / "env-codex"))
    config = AgentScopeConfig.from_env(
        base_dir=tmp_path,
        codex_home=tmp_path / "explicit-codex",
        headroom_home=tmp_path / "explicit-headroom",
        database_path=tmp_path / "custom.db",
    )
    assert config.codex_home == tmp_path / "explicit-codex"
    assert config.headroom_home == tmp_path / "explicit-headroom"
    assert config.database_path == tmp_path / "custom.db"
