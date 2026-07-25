# Phase 6V-P1.29 — Real Provider Control Design

## Purpose

Gate the transition from `provider_mode=staging_replay` (zero cost) to `provider_mode=staging_real` (actual API calls, real cost) with a hardware circuit breaker, budget hard cap, and kill switch. This document records the control design evaluated for P1.29.

---

## Environment Variables

| Variable | P1.29 Value | Notes |
|----------|-------------|-------|
| `PI_REAL_PROVIDER_ENABLED` | `false` | Must be explicitly set to `true` to activate real provider |
| `PI_REAL_PROVIDER_MAX_REQUESTS` | `100` | Hard cap: circuit breaker opens after 100 real calls |
| `PI_REAL_PROVIDER_MAX_COST_CNY` | `100` | Hard cap: circuit breaker opens when estimated cost exceeds ¥100 |
| `PI_CANARY_LIVE_ENABLED` | `true` | Unchanged; live canary remains active |
| `PI_CANARY_CONFIG_VERSION` | `12` | Unchanged for provider mode change |
| `provider_mode` | `staging_replay` → evaluated only, not activated in P1.29 | P1.29 evaluates but does NOT activate real provider calls |

---

## Fail-Closed Design

```
live_selected(request)
    ↓
PI_REAL_PROVIDER_ENABLED == true?
    NO  → staging_replay (current; zero cost)
    YES →
        budget_guard(current_requests, current_cost)
            OVER BUDGET → circuit_breaker_open → legacy_fallback
            UNDER BUDGET → real_provider_call(staging credentials)
```

The default path (disabled) routes all Pi live executions through the replay provider. No accidental real calls possible.

---

## Budget Accounting

- Request counter: atomic increment in Redis (`pi_real_provider:request_count`)
- Cost estimate: per-model token pricing * estimated tokens per request
- Counters reset: manual only (not time-based) — prevents reset-race attacks
- Circuit breaker state: persisted in Redis; survives container restart

---

## Staging-Only Credentials

- Real provider uses `DEEPSEEK_API_KEY_STAGING` (separate from prod key)
- Staging key rate-limited at source to 100 RPM
- Key rotation: independent of production key
- Audit trail: all real provider calls logged to `pi_real_provider_audit` table (migration required before activation)

---

## Provider Kill Switch

```
PI_REAL_PROVIDER_ENABLED=false  →  circuit breaker forces staging_replay
                                    no new real calls
                                    in-flight real calls complete (no abort)
                                    config_version unchanged
```

Provider kill switch is independent of canary kill switch (`PI_CANARY_LIVE_ENABLED`). Both can be operated independently.

---

## P1.29 Evaluation Conclusion

P1.29 **evaluates** this design (control design artifact, fail-closed verification, budget guard logic) but does **NOT activate** real provider calls. Activation requires:

1. Explicit project owner authorization for real provider activation
2. `pi_real_provider_audit` migration deployed
3. Staging credentials provisioned and isolated
4. Budget counters initialized to 0
5. New config_version (cv=13 if kill switch used, cv=15 for live provider activation)

**P1.29 Gate S (Real Provider) = NOT_EVALUATED** — real provider activation is a P1.30 decision.

---

## What IS Verified in P1.29

- `PI_REAL_PROVIDER_ENABLED=false` → 0 real calls across all S1-S12 (confirmed)
- Budget guard logic unit-tested (see test_phase6v_p129_sustained_live.py)
- Fail-closed circuit breaker unit-tested
- Provider control design reviewed and documented

**Gate S status: DEFERRED to P1.30 (requires explicit authorization)**
