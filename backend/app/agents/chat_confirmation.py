"""
C5 ConfirmationManager — pending action lifecycle helpers.

Confirmation dict format (stored in ChatMessage.confirmation JSONB):
{
    "id":           "confirm_add_watchlist_1718700000000_abc123",
    "type":         "add_watchlist" | "create_analysis_run" | "create_compare",
    "text":         "User-facing confirmation prompt",
    "params":       {...},
    "status":       "pending" | "confirmed" | "cancelled" | "expired"
                    | "executing" | "executed" | "failed",
    "created_at":   "2026-06-18T12:00:00.000000+00:00",
    "expires_at":   "2026-06-18T12:10:00.000000+00:00",  # 10 minutes
    "confirmed_at": null | ISO string,
    "executed_at":  null | ISO string,
    "error":        null | error message string,
}
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

_EXPIRY_MINUTES = 10


def make_confirmation(
    action_type: str,
    text: str,
    params: dict,
) -> dict:
    """
    Build a fresh confirmation dict with status=pending and 10-minute expiry.
    Replaces the old _confirm_id() + inline dict approach from C4.
    """
    now = datetime.now(timezone.utc)
    suffix = uuid.uuid4().hex[:6]
    return {
        "id":           f"confirm_{action_type}_{int(now.timestamp() * 1000)}_{suffix}",
        "type":         action_type,
        "text":         text,
        "params":       params,
        "status":       "pending",
        "created_at":   now.isoformat(),
        "expires_at":   (now + timedelta(minutes=_EXPIRY_MINUTES)).isoformat(),
        "confirmed_at": None,
        "executed_at":  None,
        "error":        None,
    }


def is_expired(conf: dict) -> bool:
    """Return True if the confirmation's expires_at is in the past."""
    expires_at_str = conf.get("expires_at")
    if not expires_at_str:
        return False
    try:
        expires_at = datetime.fromisoformat(expires_at_str)
        return datetime.now(timezone.utc) > expires_at
    except (ValueError, TypeError):
        return False


def is_executable(conf: dict) -> bool:
    """Return True if status == 'pending' and not yet expired."""
    return conf.get("status") == "pending" and not is_expired(conf)
