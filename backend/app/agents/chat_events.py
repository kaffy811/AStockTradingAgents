"""
chat_events.py — Phase C13-b shared event helpers.

Provides safe_emit() used by ToolRegistry, RAG layer, Skills, and PlannerExecutor
to push real-time execution events without crashing the main flow.
"""
from __future__ import annotations

import logging

log = logging.getLogger(__name__)


async def safe_emit(
    event_callback,
    event_type: str,
    payload: dict | None = None,
) -> None:
    """
    Safely call event_callback(event_type, payload).
    Never raises — failures are silently swallowed.
    No-op if event_callback is None.
    """
    if not event_callback:
        return
    try:
        await event_callback(event_type, payload or {})
    except Exception:
        log.debug("safe_emit: callback error for event_type=%s", event_type)
