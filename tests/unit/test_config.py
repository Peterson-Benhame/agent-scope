from agentscope.config import AgentScopeConfig


def test_defaults_use_user_home_and_local_project_paths(monkeypatch, tmp_path):
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "user"))
    monkeypatch.delenv("AGENTSCOPE_SOURCES", raising=False)

    config = AgentScopeConfig.from_env(base_dir=tmp_path / "project")

    assert config.codex_home == tmp_path / "user" / ".codex"
    assert config.headroom_home == tmp_path / "user" / ".headroom"
    assert config.database_path == tmp_path / "project" / "data" / "agentscope.db"
    assert config.reports_path == tmp_path / "project" / "reports"
    assert config.safe_mode is True
    assert config.enabled_sources is None


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


def test_enabled_sources_are_parsed_from_environment(monkeypatch, tmp_path):
    monkeypatch.setenv("AGENTSCOPE_SOURCES", " codex, headroom,codex ")

    config = AgentScopeConfig.from_env(base_dir=tmp_path)

    assert config.enabled_sources == frozenset({"codex", "headroom"})


def test_empty_sources_environment_means_all_registered_sources(monkeypatch, tmp_path):
    monkeypatch.setenv("AGENTSCOPE_SOURCES", "   ")

    config = AgentScopeConfig.from_env(base_dir=tmp_path)

    assert config.enabled_sources is None
