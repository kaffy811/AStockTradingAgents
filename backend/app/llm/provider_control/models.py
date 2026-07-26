"""Data models for provider control plane — Phase 6V-P1.31."""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from typing import Any


class ProviderCallOutcome(str, Enum):
    SUCCESS = "success"
    TIMEOUT = "timeout"
    RATE_LIMITED = "rate_limited"
    CREDENTIAL_INVALID = "credential_invalid"
    MALFORMED_RESPONSE = "malformed_response"
    CIRCUIT_OPEN = "circuit_open"
    BUDGET_EXHAUSTED = "budget_exhausted"
    CONCURRENCY_LIMIT = "concurrency_limit"
    KILL_SWITCH = "kill_switch"
    LEGACY_FALLBACK = "legacy_fallback"
    NOT_EXECUTED = "not_executed"


class CircuitBreakerStatus(str, Enum):
    CLOSED = "closed"       # normal operation
    OPEN = "open"           # blocking all calls
    HALF_OPEN = "half_open" # probe mode


@dataclass
class BudgetState:
    requests_used: int = 0
    requests_max: int = 100
    cost_used_cny: Decimal = field(default_factory=lambda: Decimal("0"))
    cost_max_cny: Decimal = field(default_factory=lambda: Decimal("100"))
    namespace: str = "pi_provider_staging"

    @property
    def requests_remaining(self) -> int:
        return max(0, self.requests_max - self.requests_used)

    @property
    def cost_remaining_cny(self) -> Decimal:
        return max(Decimal("0"), self.cost_max_cny - self.cost_used_cny)

    @property
    def requests_exhausted(self) -> bool:
        return self.requests_used >= self.requests_max

    @property
    def cost_exhausted(self) -> bool:
        return self.cost_used_cny >= self.cost_max_cny


@dataclass
class RateLimitState:
    requests_in_window: int = 0
    window_seconds: int = 60
    limit_per_window: int = 60
    namespace: str = "pi_provider_rate"

    @property
    def available(self) -> bool:
        return self.requests_in_window < self.limit_per_window


@dataclass
class ConcurrencyState:
    active_slots: int = 0
    max_slots: int = 2
    namespace: str = "pi_provider_concurrency"

    @property
    def available(self) -> bool:
        return self.active_slots < self.max_slots

    @property
    def slots_remaining(self) -> int:
        return max(0, self.max_slots - self.active_slots)


@dataclass
class CircuitBreakerState:
    status: CircuitBreakerStatus = CircuitBreakerStatus.CLOSED
    consecutive_failures: int = 0
    failure_threshold: int = 5
    recovery_at_epoch: float | None = None
    namespace: str = "pi_provider_circuit"

    @property
    def is_open(self) -> bool:
        return self.status == CircuitBreakerStatus.OPEN

    @property
    def is_closed(self) -> bool:
        return self.status == CircuitBreakerStatus.CLOSED


@dataclass
class ProviderControlState:
    """Sanitized snapshot of all control plane state — safe to expose in probe endpoint."""
    timestamp: str = ""
    # Credential (no key value exposed — fingerprint only)
    credential_present: bool = False
    credential_fingerprint_prefix: str = ""  # e.g. "sk-xxxx..." (first 8 chars only)
    # Provider config
    real_provider_enabled: bool = False
    kill_switch_active: bool = True
    provider_name: str = "deepseek"
    provider_model: str = "deepseek-v4-flash"
    provider_mode: str = "staging_replay"
    config_version: int = 12
    # Pricing
    pricing_version: str = "unverified"
    pricing_verified: bool = False
    pricing_mode: str = "test_fixture"
    # Budget
    budget: BudgetState = field(default_factory=BudgetState)
    # Rate limit
    rate_limit: RateLimitState = field(default_factory=RateLimitState)
    # Concurrency
    concurrency: ConcurrencyState = field(default_factory=ConcurrencyState)
    # Circuit breaker
    circuit_breaker: CircuitBreakerState = field(default_factory=CircuitBreakerState)
    # Readiness
    ready_for_real_provider: bool = False
    blocking_gates: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "credential": {
                "present": self.credential_present,
                "fingerprint_prefix": self.credential_fingerprint_prefix,
            },
            "provider": {
                "real_provider_enabled": self.real_provider_enabled,
                "kill_switch_active": self.kill_switch_active,
                "name": self.provider_name,
                "model": self.provider_model,
                "mode": self.provider_mode,
                "config_version": self.config_version,
            },
            "pricing": {
                "version": self.pricing_version,
                "verified": self.pricing_verified,
                "mode": self.pricing_mode,
            },
            "budget": {
                "requests_used": self.budget.requests_used,
                "requests_max": self.budget.requests_max,
                "requests_remaining": self.budget.requests_remaining,
                "cost_used_cny": str(self.budget.cost_used_cny),
                "cost_max_cny": str(self.budget.cost_max_cny),
                "cost_remaining_cny": str(self.budget.cost_remaining_cny),
                "namespace": self.budget.namespace,
            },
            "rate_limit": {
                "requests_in_window": self.rate_limit.requests_in_window,
                "window_seconds": self.rate_limit.window_seconds,
                "limit_per_window": self.rate_limit.limit_per_window,
                "available": self.rate_limit.available,
            },
            "concurrency": {
                "active_slots": self.concurrency.active_slots,
                "max_slots": self.concurrency.max_slots,
                "slots_remaining": self.concurrency.slots_remaining,
                "available": self.concurrency.available,
            },
            "circuit_breaker": {
                "status": self.circuit_breaker.status.value,
                "consecutive_failures": self.circuit_breaker.consecutive_failures,
                "failure_threshold": self.circuit_breaker.failure_threshold,
                "recovery_at_epoch": self.circuit_breaker.recovery_at_epoch,
            },
            "readiness": {
                "ready_for_real_provider": self.ready_for_real_provider,
                "blocking_gates": self.blocking_gates,
            },
        }
