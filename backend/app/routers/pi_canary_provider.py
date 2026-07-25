"""
Pi-canary provider budget probe endpoint — Phase 6V-P1.31.

GET /pi-canary/provider-budget
  Returns sanitized runtime state of provider control plane.
  Never raises — always returns 200 with current state (or safe defaults).
  No credential values exposed — only fingerprint prefix.

This endpoint is used by:
  - Staging probe scripts
  - Canary health checks
  - P1.31+ gate verification
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter

from app.core.config import settings
from app.llm.provider_control.runtime_state import build_runtime_probe

log = logging.getLogger(__name__)

router = APIRouter(prefix="/pi-canary", tags=["pi-canary"])


@router.get("/provider-budget")
async def get_provider_budget() -> dict[str, Any]:
    """
    Sanitized provider control plane state probe.

    Returns current budget, rate limit, concurrency, circuit breaker state,
    and readiness assessment. No credential values are exposed.
    """
    try:
        # In P1.31, Redis control objects are not instantiated (provider is NOT_ACTIVE).
        # The probe reads directly from settings for static configuration,
        # and reports Redis budget state as 0/not_available.
        state = build_runtime_probe(
            settings=settings,
            redis_client=None,
            budget_guard=None,
            cost_accumulator=None,
            rate_limiter=None,
            semaphore=None,
            circuit_breaker=None,
        )
        return {
            "ok": True,
            "phase": "6V-P1.31",
            "probe": state.to_dict(),
        }
    except Exception as exc:
        log.exception("Provider budget probe failed: %s", exc)
        return {
            "ok": False,
            "phase": "6V-P1.31",
            "error": "probe_failed",
            "detail": str(exc),
        }
