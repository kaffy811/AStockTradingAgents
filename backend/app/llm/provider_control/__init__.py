"""
Provider Control Plane — Phase 6V-P1.31

Implements safety controls for restricted real staging provider activation:
- Fail-closed defaults (real_provider_enabled=False, kill_switch=True)
- Atomic request/cost budget via Redis Lua scripts
- Cross-worker rate limiter (sliding window)
- Cross-worker concurrency semaphore (lease-based)
- Circuit breaker (closed/open/half_open)
- Sanitized runtime probe (no credential exposure)
- Audit trail (hash-only fields)
- Fake provider harness (blocks real HTTP in tests)

NO real provider calls are authorized in P1.31.
Real provider activation requires explicit project owner authorization (P1.32+).
"""

from .models import (
    ProviderControlState,
    ProviderCallOutcome,
    BudgetState,
    RateLimitState,
    ConcurrencyState,
    CircuitBreakerState,
)
from .errors import (
    CredentialGateError,
    KillSwitchError,
    BudgetExhaustedError,
    RateLimitExceededError,
    ConcurrencyLimitError,
    CircuitOpenError,
    PricingUnverifiedError,
)

__all__ = [
    "ProviderControlState",
    "ProviderCallOutcome",
    "BudgetState",
    "RateLimitState",
    "ConcurrencyState",
    "CircuitBreakerState",
    "CredentialGateError",
    "KillSwitchError",
    "BudgetExhaustedError",
    "RateLimitExceededError",
    "ConcurrencyLimitError",
    "CircuitOpenError",
    "PricingUnverifiedError",
]
