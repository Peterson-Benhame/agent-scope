from __future__ import annotations

import hashlib
from pathlib import Path

from agentscope.collectors.headroom import collect_headroom
from agentscope.correlation import correlate_optimization
from agentscope.sources.base import (
    CollectRequest,
    DiscoveryContext,
    SourceCapabilities,
    SourceCollectionSummary,
    SourceDiscovery,
)


_SUPPORTED_FILES = (
    "proxy_savings.json",
    "savings.jsonl",
    "savings_events.jsonl",
    "session_stats.jsonl",
)


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _unchanged(repository, path: Path, digest: str) -> bool:
    state = repository.get_import_state("headroom", str(path))
    return bool(
        state
        and state.get("content_hash") == digest
        and state.get("size") == path.stat().st_size
    )


def _save_state(repository, path: Path, digest: str) -> None:
    stat = path.stat()
    repository.save_import_state(
        "headroom",
        str(path),
        size=stat.st_size,
        modified_at=stat.st_mtime,
        content_hash=digest,
        last_offset=stat.st_size,
        status="complete",
    )


class HeadroomAdapter:
    source_name = "headroom"

    def discover(self, context: DiscoveryContext) -> SourceDiscovery:
        root = context.overrides.get("headroom", context.user_home / ".headroom")
        artifacts = tuple(
            root / name
            for name in _SUPPORTED_FILES
            if (root / name).exists()
        ) if root.exists() else ()
        return SourceDiscovery(
            source=self.source_name,
            detected=bool(artifacts),
            roots=(root,),
            format_version="headroom-local-state" if artifacts else None,
            artifacts=artifacts,
            diagnostic=None if artifacts else "No supported Headroom state files found",
        )

    def capabilities(self) -> SourceCapabilities:
        return SourceCapabilities(
            cache=True,
            costs=True,
            optimizations=True,
        )

    def collect(self, request: CollectRequest) -> SourceCollectionSummary:
        summary = SourceCollectionSummary()
        repository = request.repository
        artifacts = tuple(request.discovery.artifacts)
        if not artifacts:
            return summary

        digests: dict[Path, str] = {}
        changed = request.full_rescan
        for path in artifacts:
            summary.files_seen += 1
            digest = _hash_file(path)
            digests[path] = digest
            if request.full_rescan or not _unchanged(repository, path, digest):
                changed = True
            else:
                summary.files_skipped += 1

        if not changed:
            return summary

        try:
            home = request.discovery.roots[0]
            data = collect_headroom(home)
            candidates = repository.session_candidates()
            for optimization in data.optimizations:
                correlation = correlate_optimization(optimization, candidates)
                optimization.confidence = correlation.confidence
                optimization.session_external_id = correlation.session_external_id
                session_id = (
                    repository.session_id_by_external(correlation.session_external_id)
                    if correlation.session_external_id
                    else None
                )
                repository.insert_optimization(optimization, session_id=session_id)
                summary.optimizations_imported += 1

            if data.lifetime:
                compression = data.lifetime.get("compression_savings_usd")
                cache = data.lifetime.get("cache_savings_usd")
                observed = data.lifetime.get("total_input_cost_usd")
                total_savings = (
                    float(compression or 0) + float(cache or 0)
                    if compression is not None or cache is not None
                    else None
                )
                repository.insert_cost(
                    session_id=None,
                    model_id=None,
                    estimated_raw_cost_usd=None,
                    observed_cost_usd=(
                        float(observed) if observed is not None else None
                    ),
                    compression_savings_usd=(
                        float(compression) if compression is not None else None
                    ),
                    cache_savings_usd=(
                        float(cache) if cache is not None else None
                    ),
                    total_savings_usd=total_savings,
                    pricing_source="headroom:lifetime",
                    pricing_version="proxy_savings",
                    snapshot_key="headroom:lifetime",
                )

            for path, digest in digests.items():
                _save_state(repository, path, digest)
            summary.files_imported = len(artifacts)
            summary.files_skipped = 0
        except Exception as exc:
            summary.errors += 1
            repository.record_import_error(
                "headroom",
                str(request.discovery.roots[0]),
                None,
                "import",
                str(exc),
            )
        return summary
