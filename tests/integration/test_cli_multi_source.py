from pathlib import Path

from typer.testing import CliRunner

from agentscope.cli import app


runner = CliRunner()
CLAUDE_FIXTURE = Path("tests/fixtures/claude_code/session.jsonl")


def test_collect_uses_default_multi_provider_registry(monkeypatch, tmp_path):
    user_home = tmp_path / "user"
    claude_home = user_home / ".claude"
    project = claude_home / "projects" / "-work-claude-demo"
    project.mkdir(parents=True)
    target = project / "claude-session-1.jsonl"
    target.write_text(CLAUDE_FIXTURE.read_text(encoding="utf-8"), encoding="utf-8")

    monkeypatch.setenv("USERPROFILE", str(user_home))
    monkeypatch.setenv("AGENTSCOPE_SOURCES", "claude_code")
    monkeypatch.setenv("AGENTSCOPE_CLAUDE_HOME", str(claude_home))
    db = tmp_path / "agentscope.db"

    result = runner.invoke(app, ["collect", "--database", str(db)])

    assert result.exit_code == 0, result.output
    assert "Fonte detectada: Claude_code" in result.output
    assert "sessions_imported=1" in result.output


def test_status_and_collect_show_unsupported_provider_diagnostic(monkeypatch, tmp_path):
    user_home = tmp_path / "user"
    claude_home = user_home / ".claude"
    project = claude_home / "projects" / "-future"
    project.mkdir(parents=True)
    (project / "future.jsonl").write_text(
        '{"type":"future_record","formatVersion":99}\n',
        encoding="utf-8",
    )

    monkeypatch.setenv("USERPROFILE", str(user_home))
    monkeypatch.setenv("AGENTSCOPE_SOURCES", "claude_code")
    monkeypatch.setenv("AGENTSCOPE_CLAUDE_HOME", str(claude_home))
    db = tmp_path / "agentscope.db"

    status = runner.invoke(app, ["status", "--database", str(db)])
    collect = runner.invoke(app, ["collect", "--database", str(db)])

    assert status.exit_code == 0, status.output
    assert "source=claude_code detected=no artifacts=0" in status.output
    assert "unsupported" in status.output.lower()
    assert collect.exit_code == 0, collect.output
    assert "unsupported" in collect.output.lower()
