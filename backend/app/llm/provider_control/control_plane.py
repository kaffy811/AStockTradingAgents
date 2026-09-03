"""
Provider Control Plane — Phase MVP-R1.

Wires all 8 Redis-backed gate checks into the formal provider call path.
Creates and injects: RequestBudgetGuard, CostAccumulator, SlidingWindowRateLimiter,
LeaseSemaphore, ProviderCircuitBreaker into ProviderActivationGate.

Usage:
    plane = get_provider_control_plane()
    result = plane.check_gate()  # returns ProviderGateDecision

The plane is created once per process (lazy singleton). If Redis is unavailable,
the plane operates in degraded mode: only the 3 synchronous checks run (kill_switch,
enabled, credential). This preserves State B fail-closed behavior even without Redis.
"""
from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

log = logging.getLogger(__name__)


@dataclass
class ProviderGateDecision:
    allowed: bool
    blocked_reason: str | None = None
    error_class: str | None = None  # ProviderControlError subclass name for backward compat
    reservation_id: str | None = None
    budget_snapshot: dict = field(default_factory=dict)
    credential_source: str = "staging-only"
    pricing_version: str = "unknown"
    gate_checks_performed: list[str] = field(default_factory=list)
    gate_checks_skipped: list[str] = field(default_factory=list)


class ProviderControlPlane:
    """
    Full 8-check provider gate with Redis-backed runtime controls.

    Instantiated once at application startup (or on first call) via
    get_provider_control_plane(). Accepts a redis_client; if None,
    operates with only synchronous checks (3/8 — degraded safe mode).
    """

    def __init__(
        self,
        settings: Any,
        redis_client: Any | None = None,
    ) -> None:
        from .activation_gate import ProviderActivationGate
        from .pricing import get_pricing_registry

        self._settings = settings
        self._redis = redis_client
        self._pricing_registry = get_pricing_registry()

        # Build Redis-backed guards (None if no Redis)
        self._budget_guard = self._make_budget_guard()
        self._cost_accumulator = self._make_cost_accumulator()
        self._rate_limiter = self._make_rate_limiter()
        self._semaphore = self._make_semaphore()
        self._circuit_breaker = self._make_circuit_breaker()

        # Build the gate with all guards injected
        self._gate = ProviderActivationGate(
            settings=settings,
            budget_guard=self._budget_guard,
            cost_accumulator=self._cost_accumulator,
            rate_limiter=self._rate_limiter,
            semaphore=self._semaphore,
            circuit_breaker=self._circuit_breaker,
        )

        checks_present = sum([
            self._budget_guard is not None,
            self._cost_accumulator is not None,
            self._rate_limiter is not None,
            self._semaphore is not None,
            self._circuit_breaker is not None,
        ])
        log.info(
            "pi_canary: ProviderControlPlane initialized — %d/5 Redis guards injected "
            "(3 synchronous checks always active)",
            checks_present,
        )

    # ── Guard factories ───────────────────────────────────────────────────────

    def _make_budget_guard(self) -> Any | None:
        if self._redis is None:
            return None
        try:
            from .budget import RequestBudgetGuard
            max_req = getattr(self._settings, "pi_real_provider_max_requests", 30)
            return RequestBudgetGuard(
                self._redis,
                namespace="pi_provider_staging",
                max_requests=max_req,
            )
        except Exception as exc:
            log.warning("pi_canary: RequestBudgetGuard init failed: %s", exc)
            return None

    def _make_cost_accumulator(self) -> Any | None:
        if self._redis is None:
            return None
        try:
            from .budget import CostAccumulator
            max_cost = Decimal(str(getattr(self._settings, "pi_real_provider_max_cost_cny", "20")))
            return CostAccumulator(
                self._redis,
                namespace="pi_provider_staging",
                max_cost_cny=max_cost,
            )
        except Exception as exc:
            log.warning("pi_canary: CostAccumulator init failed: %s", exc)
            return None

    def _make_rate_limiter(self) -> Any | None:
        if self._redis is None:
            return None
        try:
            from .rate_limit import SlidingWindowRateLimiter
            rpm = getattr(self._settings, "pi_real_provider_max_rpm", 10)
            return SlidingWindowRateLimiter(
                self._redis,
                namespace="pi_provider_staging",
                max_per_window=rpm,
            )
        except Exception as exc:
            log.warning("pi_canary: SlidingWindowRateLimiter init failed: %s", exc)
            return None

    def _make_semaphore(self) -> Any | None:
        if self._redis is None:
            return None
        try:
            from .concurrency import LeaseSemaphore
            max_conc = getattr(self._settings, "pi_real_provider_max_concurrency", 2)
            return LeaseSemaphore(
                self._redis,
                namespace="pi_provider_staging",
                max_slots=max_conc,
            )
        except Exception as exc:
            log.warning("pi_canary: LeaseSemaphore init failed: %s", exc)
            return None

    def _make_circuit_breaker(self) -> Any | None:
        if self._redis is None:
            return None
        try:
            from .budget import ProviderCircuitBreaker
            return ProviderCircuitBreaker(
                self._redis,
                namespace="pi_provider_staging",
            )
        except Exception as exc:
            log.warning("pi_canary: ProviderCircuitBreaker init failed: %s", exc)
            return None

    # ── Public API ────────────────────────────────────────────────────────────

    def check_gate(
        self,
        *,
        estimated_cost_cny: Decimal = Decimal("0"),
    ) -> ProviderGateDecision:
        """
        Run all active gate checks. Returns ProviderGateDecision.
        Never raises — failures are captured in the decision.
        """
        from .errors import ProviderControlError

        checks_active = ["kill_switch", "enabled", "credential"]
        checks_skipped = []
        if self._budget_guard is not None:
            checks_active.append("request_budget")
        else:
            checks_skipped.append("request_budget")
        if self._cost_accumulator is not None:
            checks_active.append("cost_budget")
        else:
            checks_skipped.append("cost_budget")
        if self._rate_limiter is not None:
            checks_active.append("rate_limit")
        else:
            checks_skipped.append("rate_limit")
        if self._semaphore is not None:
            checks_active.append("concurrency")
        else:
            checks_skipped.append("concurrency")
        if self._circuit_breaker is not None:
            checks_active.append("circuit_breaker")
        else:
            checks_skipped.append("circuit_breaker")

        try:
            self._gate.check_all(estimated_cost_cny=estimated_cost_cny)
        except ProviderControlError as exc:
            log.warning(
                "pi_canary: ProviderControlPlane gate BLOCKED [%s]: %s",
                type(exc).__name__, exc,
            )
            return ProviderGateDecision(
                allowed=False,
                blocked_reason=str(exc),
                error_class=type(exc).__name__,
                pricing_version=self._pricing_registry.pricing_version,
                gate_checks_performed=checks_active,
                gate_checks_skipped=checks_skipped,
            )
        except Exception as exc:
            log.error("pi_canary: ProviderControlPlane unexpected gate error: %s", exc)
            return ProviderGateDecision(
                allowed=False,
                blocked_reason=f"Unexpected gate error: {type(exc).__name__}: {exc}",
                error_class=type(exc).__name__,
                pricing_version=self._pricing_registry.pricing_version,
                gate_checks_performed=checks_active,
                gate_checks_skipped=checks_skipped,
            )

        reservation_id = str(uuid.uuid4())
        return ProviderGateDecision(
            allowed=True,
            reservation_id=reservation_id,
            pricing_version=self._pricing_registry.pricing_version,
            gate_checks_performed=checks_active,
            gate_checks_skipped=checks_skipped,
        )

    @property
    def redis_guards_active(self) -> int:
        """Number of Redis-backed guards actually injected (0–5)."""
        return sum([
            self._budget_guard is not None,
            self._cost_accumulator is not None,
            self._rate_limiter is not None,
            self._semaphore is not None,
            self._circuit_breaker is not None,
        ])

    @property
    def total_checks_active(self) -> int:
        """Total gate checks active (always 3 synchronous + redis_guards_active)."""
        return 3 + self.redis_guards_active


# ── Module-level singleton ────────────────────────────────────────────────────

_control_plane: ProviderControlPlane | None = None


def get_provider_control_plane(
    *,
    redis_client: Any | None = None,
    force_new: bool = False,
) -> ProviderControlPlane:
    """
    Return the module-level ProviderControlPlane singleton.

    On first call, creates the plane with the provided redis_client.
    Subsequent calls return the cached instance (unless force_new=True).

    In test environments, pass force_new=True to get a fresh instance.
    """
    global _control_plane
    if _control_plane is None or force_new:
        from app.core.config import settings as _settings
        _control_plane = ProviderControlPlane(
            settings=_settings,
            redis_client=redis_client,
        )
    return _control_plane


def reset_provider_control_plane() -> None:
    """Reset the singleton (for testing only)."""
    global _control_plane
    _control_plane = None
