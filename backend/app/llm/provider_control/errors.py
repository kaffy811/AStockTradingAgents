"""Provider control plane error hierarchy — Phase 6V-P1.31."""
from __future__ import annotations


class ProviderControlError(Exception):
    """Base class for all provider control plane errors."""
    gate: str = "unknown"


class CredentialGateError(ProviderControlError):
    """Raised when staging-isolated credential is not provisioned."""
    gate = "D"


class KillSwitchError(ProviderControlError):
    """Raised when kill switch is active (pi_real_provider_kill_switch=True)."""
    gate = "I"


class BudgetExhaustedError(ProviderControlError):
    """Raised when request or cost budget is exhausted."""
    gate = "F_G"

    def __init__(self, message: str, *, budget_type: str = "request") -> None:
        super().__init__(message)
        self.budget_type = budget_type  # "request" | "cost"


class RateLimitExceededError(ProviderControlError):
    """Raised when per-minute rate limit is exceeded."""
    gate = "H"

    def __init__(self, message: str, *, retry_after_seconds: float = 60.0) -> None:
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds


class ConcurrencyLimitError(ProviderControlError):
    """Raised when max concurrency slots are full."""
    gate = "H"

    def __init__(self, message: str, *, active_slots: int = 0) -> None:
        super().__init__(message)
        self.active_slots = active_slots


class CircuitOpenError(ProviderControlError):
    """Raised when circuit breaker is in OPEN state."""
    gate = "I"

    def __init__(self, message: str, *, recovery_at: str | None = None) -> None:
        super().__init__(message)
        self.recovery_at = recovery_at


class PricingUnverifiedError(ProviderControlError):
    """Raised when pricing cannot be verified from authoritative source."""
    gate = "E"
