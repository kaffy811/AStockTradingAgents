"""Immutable correlation envelope for Pi shadow acceptance runs.

The acceptance runner pre-generates a correlation envelope per user turn and
sends it via an HTTP header.  The chat router places it into a ContextVar so
that the fire-and-forget shadow task and the diagnostics sink can attach the
exact acceptance_run/case/turn/shadow_run identity to every record.

Production safety:
- The header is only honored when the Pi shadow executor mode is active.
- Absent header => empty correlation => behavior identical to before.
- No sensitive values are carried (ids and hashes only), and nothing here
  performs any database write.
"""
from __future__ import annotations

import json
from contextvars import ContextVar
from typing import Any

from app.core.config import settings


SHADOW_CORRELATION_HEADER = "x-pi-shadow-correlation"

_ALLOWED_KEYS = (
    "acceptance_run_id",
    "case_id",
    "case_attempt",
    "session_id",
    "turn_id",
    "request_trace_id",
    "legacy_run_id",
    "shadow_run_id",
    "input_snapshot_hash",
)
_MAX_VALUE_LEN = 80

_current_correlation: ContextVar[dict[str, Any] | None] = ContextVar(
    "pi_shadow_correlation", default=None
)


def shadow_correlation_enabled() -> bool:
    return (
        str(getattr(settings, "agent_executor_mode", "legacy") or "legacy").strip().lower()
        == "pi_compatible_shadow"
    )


def parse_correlation_header(raw: str | None) -> dict[str, Any]:
    """Parse and sanitize the correlation header. Unknown keys are dropped."""
    if not raw:
        return {}
    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, TypeError, ValueError):
        return {}
    if not isinstance(payload, dict):
        return {}
    envelope: dict[str, Any] = {}
    for key in _ALLOWED_KEYS:
        value = payload.get(key)
        if value is None:
            continue
        if key == "case_attempt":
            try:
                envelope[key] = max(1, int(value))
            except (TypeError, ValueError):
                continue
        else:
            text = str(value)[:_MAX_VALUE_LEN]
            if text:
                envelope[key] = text
    return envelope


def set_correlation_from_header(raw: str | None):
    """Set correlation for the current context.  Returns a reset token."""
    if not shadow_correlation_enabled():
        return _current_correlation.set(None)
    envelope = parse_correlation_header(raw)
    return _current_correlation.set(envelope or None)


def current_correlation() -> dict[str, Any]:
    value = _current_correlation.get()
    return dict(value) if isinstance(value, dict) else {}


def reset_correlation(token) -> None:
    try:
        _current_correlation.reset(token)
    except Exception:  # noqa: BLE001 - token may belong to another context
        _current_correlation.set(None)
