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
    safe_mode: bool = True
    timezone: str | None = None

    @classmethod
    def from_env(
        cls,
        *,
        base_dir: Path | None = None,
        codex_home: Path | None = None,
        headroom_home: Path | None = None,
        database_path: Path | None = None,
        reports_path: Path | None = None,
    ) -> "AgentScopeConfig":
        base = Path(base_dir or Path.cwd())
        user_home = Path(os.environ.get("USERPROFILE") or os.environ.get("HOME") or Path.home())
        codex = Path(codex_home or os.environ.get("AGENTSCOPE_CODEX_HOME") or user_home / ".codex")
        headroom = Path(headroom_home or os.environ.get("AGENTSCOPE_HEADROOM_HOME") or user_home / ".headroom")
        database = Path(database_path or os.environ.get("AGENTSCOPE_DATABASE") or base / "data" / "agentscope.db")
        reports = Path(reports_path or os.environ.get("AGENTSCOPE_REPORTS") or base / "reports")
        safe_value = os.environ.get("AGENTSCOPE_SAFE_MODE", "true").strip().lower()
        safe_mode = safe_value not in {"0", "false", "no", "off"}
        return cls(
            codex_home=codex,
            headroom_home=headroom,
            database_path=database,
            reports_path=reports,
            safe_mode=safe_mode,
            timezone=os.environ.get("AGENTSCOPE_TIMEZONE"),
        )
