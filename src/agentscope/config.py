from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True, frozen=True)
class AgentScopeConfig:
    codex_home: Path
    headroom_home: Path
    database_path: Path
    reports_path: Path
    claude_home: Path | None = None
    copilot_home: Path | None = None
    kimi_home: Path | None = None
    gemini_home: Path | None = None
    safe_mode: bool = True
    timezone: str | None = None
    enabled_sources: frozenset[str] | None = None
    user_display_name: str | None = None
    machine_display_name: str | None = None
    monthly_budget_usd: float | None = None

    @classmethod
    def from_env(
        cls,
        *,
        base_dir: Path | None = None,
        codex_home: Path | None = None,
        headroom_home: Path | None = None,
        claude_home: Path | None = None,
        copilot_home: Path | None = None,
        kimi_home: Path | None = None,
        gemini_home: Path | None = None,
        database_path: Path | None = None,
        reports_path: Path | None = None,
        enabled_sources: frozenset[str] | set[str] | None = None,
        user_display_name: str | None = None,
        machine_display_name: str | None = None,
        monthly_budget_usd: float | None = None,
    ) -> "AgentScopeConfig":
        base = Path(base_dir or Path.cwd())
        user_home = Path(
            os.environ.get("USERPROFILE")
            or os.environ.get("HOME")
            or Path.home()
        )
        codex = Path(
            codex_home
            or os.environ.get("AGENTSCOPE_CODEX_HOME")
            or user_home / ".codex"
        )
        headroom = Path(
            headroom_home
            or os.environ.get("AGENTSCOPE_HEADROOM_HOME")
            or user_home / ".headroom"
        )
        claude = Path(
            claude_home
            or os.environ.get("AGENTSCOPE_CLAUDE_HOME")
            or user_home / ".claude"
        )
        copilot = Path(
            copilot_home
            or os.environ.get("AGENTSCOPE_COPILOT_HOME")
            or os.environ.get("COPILOT_HOME")
            or user_home / ".copilot"
        )
        kimi = Path(
            kimi_home
            or os.environ.get("AGENTSCOPE_KIMI_HOME")
            or os.environ.get("KIMI_CODE_HOME")
            or user_home / ".kimi-code"
        )
        gemini = Path(
            gemini_home
            or os.environ.get("AGENTSCOPE_GEMINI_HOME")
            or user_home / ".gemini"
        )
        database = Path(
            database_path
            or os.environ.get("AGENTSCOPE_DATABASE")
            or base / "data" / "agentscope.db"
        )
        reports = Path(
            reports_path
            or os.environ.get("AGENTSCOPE_REPORTS")
            or base / "reports"
        )
        safe_value = os.environ.get("AGENTSCOPE_SAFE_MODE", "true").strip().lower()
        safe_mode = safe_value not in {"0", "false", "no", "off"}

        configured_sources = enabled_sources
        if configured_sources is None:
            raw_sources = os.environ.get("AGENTSCOPE_SOURCES")
            if raw_sources is not None:
                parsed = {
                    item.strip().lower()
                    for item in raw_sources.split(",")
                    if item.strip()
                }
                configured_sources = frozenset(parsed) if parsed else None

        resolved_user_name = (
            user_display_name
            if user_display_name is not None
            else os.environ.get("AGENTSCOPE_USER_NAME")
        )
        resolved_machine_name = (
            machine_display_name
            if machine_display_name is not None
            else os.environ.get("AGENTSCOPE_MACHINE_NAME")
        )

        resolved_budget = monthly_budget_usd
        if resolved_budget is None:
            raw_budget = os.environ.get("AGENTSCOPE_MONTHLY_BUDGET_USD")
            if raw_budget is not None and raw_budget.strip():
                try:
                    resolved_budget = float(raw_budget)
                except ValueError as exc:
                    raise ValueError("monthly budget must be a valid number") from exc
        if resolved_budget is not None and resolved_budget < 0:
            raise ValueError("monthly budget must be non-negative")

        return cls(
            codex_home=codex,
            headroom_home=headroom,
            database_path=database,
            reports_path=reports,
            claude_home=claude,
            copilot_home=copilot,
            kimi_home=kimi,
            gemini_home=gemini,
            safe_mode=safe_mode,
            timezone=os.environ.get("AGENTSCOPE_TIMEZONE"),
            enabled_sources=(
                frozenset(configured_sources)
                if configured_sources is not None
                else None
            ),
            user_display_name=resolved_user_name,
            machine_display_name=resolved_machine_name,
            monthly_budget_usd=resolved_budget,
        )
