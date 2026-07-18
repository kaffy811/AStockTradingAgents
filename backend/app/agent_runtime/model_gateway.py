"""Model gateway abstraction for Pi-compatible runtime."""
from __future__ import annotations

from app.agent_runtime.contracts import ModelRequest, ModelStreamEvent
from app.agent_runtime.errors import AGENT_MODEL_UNAVAILABLE


class DisabledModelGateway:
    """Default gateway for Phase 6V-P1 deterministic agents.

    The first official_report_pdf prototype avoids model calls when evidence is
    already deterministic. Tests inject fakes for loop behavior.
    """

    async def stream(self, request: ModelRequest):
        yield ModelStreamEvent(event_type="error", error_code=AGENT_MODEL_UNAVAILABLE)
