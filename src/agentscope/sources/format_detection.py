from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class FormatSupport:
    supported: bool
    version: str | None
    diagnostic: str | None = None


def require_known_version(
    observed: str | None,
    supported: set[str] | frozenset[str],
    source: str,
) -> FormatSupport:
    if observed is None or not str(observed).strip():
        return FormatSupport(
            supported=False,
            version=None,
            diagnostic=f"{source} missing format version",
        )

    version = str(observed).strip()
    if version not in supported:
        return FormatSupport(
            supported=False,
            version=version,
            diagnostic=f"{source} unsupported format version: {version}",
        )

    return FormatSupport(supported=True, version=version)
