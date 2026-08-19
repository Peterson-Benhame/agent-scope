from agentscope.config import AgentScopeConfig
from agentscope.importer import default_source_registry, discovery_context


def test_provider_homes_default_under_user_home(monkeypatch, tmp_path):
    user_home = tmp_path / "user"
    monkeypatch.setenv("USERPROFILE", str(user_home))
    monkeypatch.delenv("COPILOT_HOME", raising=False)

    config = AgentScopeConfig.from_env(base_dir=tmp_path / "project")

    assert config.codex_home == user_home / ".codex"
    assert config.headroom_home == user_home / ".headroom"
    assert config.claude_home == user_home / ".claude"
    assert config.copilot_home == user_home / ".copilot"
    assert config.kimi_home == user_home / ".kimi-code"
    assert config.gemini_home == user_home / ".gemini"


def test_copilot_home_honors_official_environment_override(monkeypatch, tmp_path):
    monkeypatch.setenv("COPILOT_HOME", str(tmp_path / "official-copilot-home"))

    config = AgentScopeConfig.from_env(base_dir=tmp_path)

    assert config.copilot_home == tmp_path / "official-copilot-home"


def test_default_registry_contains_all_supported_sources_in_order():
    registry = default_source_registry()

    assert registry.source_names == (
        "codex",
        "headroom",
        "claude_code",
        "github_copilot",
        "kimi",
        "gemini",
    )


def test_discovery_context_contains_all_provider_overrides(tmp_path):
    config = AgentScopeConfig.from_env(
        base_dir=tmp_path,
        codex_home=tmp_path / "codex",
        headroom_home=tmp_path / "headroom",
        claude_home=tmp_path / "claude",
        copilot_home=tmp_path / "copilot",
        kimi_home=tmp_path / "kimi",
        gemini_home=tmp_path / "gemini",
    )

    context = discovery_context(config)

    assert context.overrides == {
        "codex": tmp_path / "codex",
        "headroom": tmp_path / "headroom",
        "claude_code": tmp_path / "claude",
        "github_copilot": tmp_path / "copilot",
        "kimi": tmp_path / "kimi",
        "gemini": tmp_path / "gemini",
    }
