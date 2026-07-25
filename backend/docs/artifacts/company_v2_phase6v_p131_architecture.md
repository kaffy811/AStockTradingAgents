# Phase 6V-P1.31 — Provider Control Plane Architecture

**Phase**: 6V-P1.31  
**Date**: 2026-07-26  
**Status**: IMPLEMENTATION COMPLETE — No real provider calls authorized

---

## Overview

P1.31 implements the provider control plane infrastructure required for safe real provider
activation in a future phase (P1.32+). All components are fail-closed by default.

```
Settings (config.py)
├── deepseek_api_key_staging = None         # Gate D: staging-only credential slot
├── pi_real_provider_enabled = False        # Gate I: master enable (fail-closed)
├── pi_real_provider_kill_switch = True     # Gate I: kill switch (fail-closed)
├── pi_real_provider_max_requests = 100     # Gate F: request cap
├── pi_real_provider_max_cost_cny = 100.0   # Gate G: cost cap (CNY)
├── pi_real_provider_max_concurrency = 2    # Gate H: max concurrent calls
├── pi_real_provider_rate_limit_per_minute = 60  # Gate H: rate limit
├── pi_real_provider_timeout_seconds = 30.0  # DeepSeekClient explicit timeout
└── pi_canary_provider_mode = "staging_replay"  # Provider mode flag

backend/app/llm/provider_control/
├── __init__.py           # Package exports
├── errors.py             # Error hierarchy (ProviderControlError subclasses)
├── models.py             # Data models (BudgetState, CircuitBreakerState, etc.)
├── pricing.py            # PricingRegistry (Decimal, verified=false, test_fixture)
├── usage.py              # ProviderUsageResult (OpenAI-compatible usage capture)
├── budget.py             # RequestBudgetGuard + CostAccumulator + ProviderCircuitBreaker
├── rate_limit.py         # SlidingWindowRateLimiter (Redis, cross-worker)
├── concurrency.py        # LeaseSemaphore (Redis lease, cross-worker)
├── circuit_breaker.py    # Re-export of ProviderCircuitBreaker
├── runtime_state.py      # Sanitized probe builder (no credential exposure)
├── audit.py              # ProviderAuditLogger (hash-only fields)
├── activation_gate.py    # ProviderActivationGate (all gates checked)
└── fake_provider.py      # FakeDeepSeekClient (12 scenarios, zero real calls)

backend/app/llm/pricing/
└── deepseek_prices.json  # Pricing table (test_fixture, verified=false)

backend/app/routers/
└── pi_canary_provider.py # GET /pi-canary/provider-budget probe endpoint

backend/alembic/versions/
└── 2026_07_26_0001-m1n2o3p4q5r6_pi_real_provider_audit.py  # DB migration
```

---

## Control Flow (P1.31 — all calls blocked)

```
Request → ProviderActivationGate.check_all()
  ├── Kill switch check (pi_real_provider_kill_switch=True) → KillSwitchError ✗
  ├── Enabled flag check (pi_real_provider_enabled=False)  → KillSwitchError ✗
  ├── Credential check (deepseek_api_key_staging=None)     → CredentialGateError ✗
  ├── Request budget check (RequestBudgetGuard)             → BudgetExhaustedError ✗
  ├── Cost budget check (CostAccumulator)                  → BudgetExhaustedError ✗
  ├── Rate limit check (SlidingWindowRateLimiter)          → RateLimitExceededError ✗
  ├── Concurrency check (LeaseSemaphore)                   → ConcurrencyLimitError ✗
  └── Circuit breaker check (ProviderCircuitBreaker)       → CircuitOpenError ✗

All errors → legacy_pi_failed fallback (replay continues)
```

---

## Redis Key Layout

```
Namespace: pi_provider_staging (configurable)

{ns}:request_count          — integer, atomic INCR (RequestBudgetGuard)
{ns}:cost_cny               — string decimal, Lua atomic (CostAccumulator)
{ns}:window:{epoch/60}      — integer per minute, Lua atomic (SlidingWindowRateLimiter)
{ns}:slot:0                 — owner token, TTL=60s (LeaseSemaphore slot 0)
{ns}:slot:1                 — owner token, TTL=60s (LeaseSemaphore slot 1)
pi_provider_circuit:status  — "closed"/"open"/"half_open" (ProviderCircuitBreaker)
pi_provider_circuit:failures — consecutive failure count
pi_provider_circuit:recovery_at — epoch timestamp for half-open transition
```

---

## Fail-Closed Guarantees

| Control | Default | Effect |
|---------|---------|--------|
| `pi_real_provider_enabled` | `False` | No real calls without explicit authorization |
| `pi_real_provider_kill_switch` | `True` | Immediate block regardless of enabled flag |
| `deepseek_api_key_staging` | `None` | Credential gate blocks activation |
| `pi_canary_provider_mode` | `staging_replay` | Provider operates in replay mode |
| `pi_canary_config_version` | `1` (env: 12) | Version unchanged from P1.30 |

---

## What P1.31 Does NOT Do

- Does NOT make any real DeepSeek API calls
- Does NOT change config_version (stays at 12)
- Does NOT expand live rollout (stays at 1%)
- Does NOT enable production
- Does NOT provision DEEPSEEK_API_KEY_STAGING
- Does NOT verify pricing from authoritative source
- Does NOT authorize real provider activation (P1.32+ requires explicit authorization)
