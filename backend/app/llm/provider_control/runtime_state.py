"""
Sanitized runtime probe — Phase 6V-P1.31.

Builds a ProviderControlState snapshot from live Settings + Redis state.
MUST NOT expose credential values — only fingerprint prefix (first 8 chars).
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from .models import (
    ProviderControlState,
    BudgetState,
    RateLimitState,
    ConcurrencyState,
    CircuitBreakerState,
    CircuitBreakerStatus,
)


def _fingerprint(key: str | None) -> str:
    """Return first 8 chars of key as fingerprint, or empty string."""
    if not key:
        return ""
    sanitized = str(key)[:8] + "..."
    return sanitized


def build_runtime_probe(
    *,
    settings: Any,
    redis_client: Any | None = None,
    budget_guard: Any | None = None,
    cost_accumulator: Any | None = None,
    rate_limiter: Any | None = None,
    semaphore: Any | None = None,
    circuit_breaker: Any | None = None,
) -> ProviderControlState:
    """
    Build sanitized runtime probe state.

    If Redis is unavailable, returns default (fail-safe) state.
    Never raises — probe endpoint must always return 200.
    """
    timestamp = datetime.now(timezone.utc).isoformat()

    # Credential (sanitized)
    staging_key = getattr(settings, "deepseek_api_key_staging", None)
    credential_present = bool(staging_key)
    fingerprint = _fingerprint(staging_key)

    # Provider config
    real_provider_enabled = getattr(settings, "pi_real_provider_enabled", False)
    kill_switch = getattr(settings, "pi_real_provider_kill_switch", True)
    provider_name = getattr(settings, "pi_real_provider_name", "deepseek")
    provider_model = getattr(settings, "pi_real_provider_model", "deepseek-v4-flash")
    provider_mode = getattr(settings, "pi_canary_provider_mode", "staging_replay")
    config_version = getattr(settings, "pi_canary_config_version", 12)
    pricing_version = getattr(settings, "pi_real_provider_pricing_version", "unverified")
    budget_ns = getattr(settings, "pi_real_provider_budget_namespace", "pi_provider_staging")

    # Budget state
    budget_state = BudgetState(namespace=budget_ns)
    if budget_guard is not None and cost_accumulator is not None:
        try:
            budget_state = cost_accumulator.get_state(budget_guard)
        except Exception:
            pass
    elif redis_client is not None:
        # Attempt direct Redis read without control objects
        try:
            req_raw = redis_client.get(f"{budget_ns}:request_count")
            cost_raw = redis_client.get(f"{budget_ns}:cost_cny")
            max_req = getattr(settings, "pi_real_provider_max_requests", 100)
            max_cost = Decimal(str(getattr(settings, "pi_real_provider_max_cost_cny", 100)))
            budget_state = BudgetState(
                requests_used=int(req_raw) if req_raw else 0,
                requests_max=max_req,
                cost_used_cny=Decimal(str(cost_raw.decode() if isinstance(cost_raw, bytes) else cost_raw)) if cost_raw else Decimal("0"),
                cost_max_cny=max_cost,
                namespace=budget_ns,
            )
        except Exception:
            pass

    # Rate limit state
    rate_state = RateLimitState()
    if rate_limiter is not None:
        try:
            rate_state = rate_limiter.get_state()
        except Exception:
            pass

    # Concurrency state
    conc_state = ConcurrencyState(
        max_slots=getattr(settings, "pi_real_provider_max_concurrency", 2)
    )
    if semaphore is not None:
        try:
            conc_state = semaphore.get_state()
        except Exception:
            pass

    # Circuit breaker state
    cb_state = CircuitBreakerState()
    if circuit_breaker is not None:
        try:
            cb_state = circuit_breaker.get_state()
        except Exception:
            pass

    # Determine blocking gates
    blocking_gates: list[str] = []
    if not credential_present:
        blocking_gates.append("D: DEEPSEEK_API_KEY_STAGING not provisioned")
    pricing_verified = False  # All P1.31 pricing is test_fixture
    if not pricing_verified:
        blocking_gates.append("E: Pricing not verified from authoritative source")
    if budget_state.requests_exhausted:
        blocking_gates.append("F: Request budget exhausted")
    if budget_state.cost_exhausted:
        blocking_gates.append("G: Cost budget exhausted")
    if kill_switch:
        blocking_gates.append("I: Kill switch active (pi_real_provider_kill_switch=True)")
    if not real_provider_enabled:
        blocking_gates.append("I: pi_real_provider_enabled=False")
    if cb_state.is_open:
        blocking_gates.append("I: Circuit breaker OPEN")

    ready = (
        credential_present
        and pricing_verified
        and not budget_state.requests_exhausted
        and not budget_state.cost_exhausted
        and not kill_switch
        and real_provider_enabled
        and not cb_state.is_open
    )

    return ProviderControlState(
        timestamp=timestamp,
        credential_present=credential_present,
        credential_fingerprint_prefix=fingerprint,
        real_provider_enabled=real_provider_enabled,
        kill_switch_active=kill_switch,
        provider_name=provider_name,
        provider_model=provider_model,
        provider_mode=provider_mode,
        config_version=config_version,
        pricing_version=pricing_version,
        pricing_verified=pricing_verified,
        pricing_mode="test_fixture",
        budget=budget_state,
        rate_limit=rate_state,
        concurrency=conc_state,
        circuit_breaker=cb_state,
        ready_for_real_provider=ready,
        blocking_gates=blocking_gates,
    )
