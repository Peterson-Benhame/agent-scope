from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

from agentscope.analytics.filters import AnalyticsFilter
from agentscope.storage.repository import Repository


TEAM_BUNDLE_SCHEMA = "agentscope-team-bundle"
TEAM_BUNDLE_VERSION = 1


def canonical_bundle_payload(bundle: dict) -> bytes:
    payload = {
        key: value
        for key, value in bundle.items()
        if key not in {"generated_at", "bundle_id"}
    }
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def compute_bundle_id(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def build_team_bundle(
    repository: Repository,
    analytics_filter: AnalyticsFilter | None = None,
    organization: str | None = None,
    team: str | None = None,
) -> dict:
    del repository, analytics_filter
    bundle = {
        "schema": TEAM_BUNDLE_SCHEMA,
        "version": TEAM_BUNDLE_VERSION,
        "bundle_id": "",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "organization": organization,
        "team": team,
        "records": {},
    }
    bundle["bundle_id"] = compute_bundle_id(canonical_bundle_payload(bundle))
    return bundle
