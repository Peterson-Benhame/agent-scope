from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from agentscope.diagnostics.codex_origin import classify_codex_client
from agentscope.domain.models import NormalizedSession
from agentscope.storage.repository import Repository


_USAGE_CONTEXT_SCHEMA = """
CREATE TABLE IF NOT EXISTS session_usage_context (
    session_id INTEGER PRIMARY KEY REFERENCES sessions(id) ON DELETE CASCADE,
    provider TEXT NOT NULL,
    product TEXT NOT NULL,
    client TEXT NOT NULL DEFAULT 'unknown',
    billing_mode TEXT NOT NULL DEFAULT 'unknown',
    client_confidence TEXT NOT NULL DEFAULT 'unknown',
    billing_confidence TEXT NOT NULL DEFAULT 'unknown',
    evidence_json TEXT NOT NULL DEFAULT '[]',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_session_usage_context_client
    ON session_usage_context(client);
CREATE INDEX IF NOT EXISTS idx_session_usage_context_billing_mode
    ON session_usage_context(billing_mode);
"""


@dataclass(frozen=True, slots=True)
class SessionUsageContext:
    provider: str
    product: str
    client: str = "unknown"
    billing_mode: str = "unknown"
    client_confidence: str = "unknown"
    billing_confidence: str = "unknown"
    evidence: tuple[str, ...] = ()
    metadata: dict[str, Any] | None = None


def _billing_classification(metadata: dict[str, Any]) -> tuple[str, str, tuple[str, ...]]:
    """Classify billing only from explicit local metadata; never infer from client."""
    keys = ("billing_mode", "auth_mode", "authentication_mode", "login_method")
    api_values = {"api", "api_key", "openai_api_key"}
    plan_values = {
        "chatgpt",
        "chatgpt_login",
        "chatgpt_plan",
        "codex_plan",
        "subscription",
    }
    for key in keys:
        raw = metadata.get(key)
        if not isinstance(raw, str) or not raw.strip():
            continue
        normalized = raw.strip().lower().replace("-", "_").replace(" ", "_")
        if normalized in api_values:
            return "api", "explicit", (f"{key}={raw}",)
        if normalized in plan_values:
            return "chatgpt_codex_plan", "explicit", (f"{key}={raw}",)
    return "unknown", "unknown", ()


def infer_codex_usage_context(session: NormalizedSession) -> SessionUsageContext:
    metadata = session.metadata if isinstance(session.metadata, dict) else {}
    source = metadata.get("source")
    thread_source = metadata.get("thread_source")
    client = classify_codex_client(
        originator=session.originator,
        metadata_source=str(source) if source is not None else None,
        thread_source=str(thread_source) if thread_source is not None else None,
    )
    billing_mode, billing_confidence, billing_evidence = _billing_classification(metadata)
    return SessionUsageContext(
        provider="openai",
        product="codex",
        client=client.client,
        billing_mode=billing_mode,
        client_confidence="explicit" if client.evidence else "unknown",
        billing_confidence=billing_confidence,
        evidence=client.evidence + billing_evidence,
        metadata={
            "model_provider": session.provider,
            "originator": session.originator,
            "source": source,
            "thread_source": thread_source,
        },
    )


def ensure_usage_context_schema(repository: Repository) -> None:
    with repository.database.connect() as conn:
        conn.executescript(_USAGE_CONTEXT_SCHEMA)


def persist_session_usage_context(
    repository: Repository,
    session_id: int,
    context: SessionUsageContext,
) -> None:
    ensure_usage_context_schema(repository)
    with repository.database.connect() as conn:
        conn.execute(
            """
            INSERT INTO session_usage_context(
                session_id, provider, product, client, billing_mode,
                client_confidence, billing_confidence, evidence_json, metadata_json
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(session_id) DO UPDATE SET
                provider=excluded.provider,
                product=excluded.product,
                client=excluded.client,
                billing_mode=excluded.billing_mode,
                client_confidence=excluded.client_confidence,
                billing_confidence=excluded.billing_confidence,
                evidence_json=excluded.evidence_json,
                metadata_json=excluded.metadata_json,
                updated_at=CURRENT_TIMESTAMP
            """,
            (
                session_id,
                context.provider,
                context.product,
                context.client,
                context.billing_mode,
                context.client_confidence,
                context.billing_confidence,
                json.dumps(context.evidence, ensure_ascii=False),
                json.dumps(context.metadata or {}, ensure_ascii=False),
            ),
        )
