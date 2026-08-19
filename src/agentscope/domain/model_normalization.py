from __future__ import annotations


_NON_MODEL_LABELS = {
    "revisão automática do codex",
    "revisao automatica do codex",
    "automatic codex review",
    "codex automatic review",
}


def normalize_model_name(value: str | None) -> str | None:
    if value is None:
        return None

    normalized = value.strip().lower()
    if not normalized:
        return None
    if normalized in _NON_MODEL_LABELS:
        return None
    return normalized
