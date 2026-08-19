from __future__ import annotations

import getpass
import hashlib
import platform

from agentscope.config import AgentScopeConfig
from agentscope.domain.models import (
    IdentityConfidence,
    NormalizedMachine,
    NormalizedUser,
)


def _stable_key(namespace: str, value: str) -> str:
    digest = hashlib.sha256(value.strip().lower().encode("utf-8")).hexdigest()
    return f"{namespace}:{digest}"


def resolve_local_identity(
    config: AgentScopeConfig,
) -> tuple[NormalizedUser, NormalizedMachine]:
    username = getpass.getuser().strip() or "unknown"
    node = platform.node().strip() or "unknown"
    system = platform.system().strip() or "unknown"
    machine_arch = platform.machine().strip() or "unknown"

    user = NormalizedUser(
        stable_key=_stable_key("local-user", username),
        display_name=config.user_display_name or username,
        provider="local-os",
        confidence=IdentityConfidence.INFERRED,
        metadata={},
    )
    machine = NormalizedMachine(
        stable_key=_stable_key(
            "local-machine",
            f"{system}|{node}|{machine_arch}",
        ),
        display_name=config.machine_display_name or node,
        os=system,
        metadata={"architecture": machine_arch},
    )
    return user, machine
