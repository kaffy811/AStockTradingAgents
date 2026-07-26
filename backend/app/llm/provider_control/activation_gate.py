"""
Provider activation gate — Phase 6V-P1.31.

Enforces all pre-activation checks before a real provider call is attempted.
Any gate failure → raises appropriate ProviderControlError → legacy_pi_failed fallback.

Gate evaluation order (fail-fast, fail-closed):
  I1. Kill switch check
  I2. Enabled flag check
  D.  Credential isolation check
  F.  Request budget check
  G.  Cost budget check (estimated)
  H1. Rate limit check
  H2. Concurrency check
  I3. Circuit breaker check
"""
from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any

from .errors import (
    CredentialGateError,
    KillSwitchError,
    BudgetExhaustedError,
    RateLimitExceededError,
    ConcurrencyLimitError,
    CircuitOpenError,
)

log = logging.getLogger(__name__)


class ProviderActivationGate:
    """
    Checks all pre-activation gates before allowing a real provider call.

    All control objects are optional — if not provided, the corresponding gate
    is skipped (for replay mode where controls are not instantiated).
    """

    def __init__(
        self,
        *,
        settings: Any,
        budget_guard: Any | None = None,
        cost_accumulator: Any | None = None,
        rate_limiter: Any | None = None,
        semaphore: Any | None = None,
        circuit_breaker: Any | None = None,
    ) -> None:
        self._settings = settings
        self._budget_guard = budget_guard
        self._cost_accumulator = cost_accumulator
        self._rate_limiter = rate_limiter
        self._semaphore = semaphore
        self._circuit_breaker = circuit_breaker

    def check_all(self, *, estimated_cost_cny: Decimal = Decimal("0")) -> None:
        """
        Run all activation gate checks.
        Raises ProviderControlError subclass on first failure.
        """
        self._check_kill_switch()
        self._check_enabled()
        self._check_credential()
        self._check_request_budget()
        self._check_cost_budget(estimated_cost_cny)
        self._check_rate_limit()
        self._check_concurrency()
        self._check_circuit_breaker()

    def _check_kill_switch(self) -> None:
        kill_switch = getattr(self._settings, "pi_real_provider_kill_switch", True)
        if kill_switch:
            raise KillSwitchError(
                "Real provider kill switch is active (pi_real_provider_kill_switch=True). "
                "Set to False with explicit project owner authorization."
            )

    def _check_enabled(self) -> None:
        enabled = getattr(self._settings, "pi_real_provider_enabled", False)
        if not enabled:
            raise KillSwitchError(
                "Real provider is disabled (pi_real_provider_enabled=False). "
                "Enable only with explicit project owner authorization."
            )

    def _check_credential(self) -> None:
        staging_key = getattr(self._settings, "deepseek_api_key_staging", None)
        if not staging_key:
            raise CredentialGateError(
                "DEEPSEEK_API_KEY_STAGING is not provisioned. "
                "Cannot isolate staging credential from production key. "
                "Provision staging-only key before enabling real provider. "
                "MUST NOT fall back to DEEPSEEK_API_KEY."
            )

    def _check_request_budget(self) -> None:
        if self._budget_guard is None:
            return
        if not self._budget_guard.try_reserve():
            used = self._budget_guard.get_count()
            max_req = self._budget_guard._max
            raise BudgetExhaustedError(
                f"Request budget exhausted: {used}/{max_req} requests used.",
                budget_type="request",
            )

    def _check_cost_budget(self, estimated_cny: Decimal) -> None:
        if self._cost_accumulator is None:
            return
        if not self._cost_accumulator.try_reserve_cost(estimated_cny):
            used = self._cost_accumulator.get_cost_cny()
            max_cost = self._cost_accumulator._max
            raise BudgetExhaustedError(
                f"Cost budget exhausted: ¥{used}/{max_cost} CNY used.",
                budget_type="cost",
            )

    def _check_rate_limit(self) -> None:
        if self._rate_limiter is None:
            return
        if not self._rate_limiter.try_acquire():
            raise RateLimitExceededError(
                "Per-minute rate limit exceeded for real provider.",
                retry_after_seconds=60.0,
            )

    def _check_concurrency(self) -> None:
        if self._semaphore is None:
            return
        acquired, owner, slot_idx = self._semaphore.try_acquire()
        if not acquired:
            active = self._semaphore.get_active_count()
            max_slots = self._semaphore._max
            raise ConcurrencyLimitError(
                f"Max concurrency reached: {active}/{max_slots} slots occupied.",
                active_slots=active,
            )
        # Note: caller is responsible for releasing the slot after the call

    def _check_circuit_breaker(self) -> None:
        if self._circuit_breaker is None:
            return
        if self._circuit_breaker.is_open():
            state = self._circuit_breaker.get_state()
            raise CircuitOpenError(
                "Provider circuit breaker is OPEN. All real provider calls blocked.",
                recovery_at=str(state.recovery_at_epoch) if state.recovery_at_epoch else None,
            )
