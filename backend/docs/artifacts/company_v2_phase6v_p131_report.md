# Phase 6V-P1.31 — Provider Control Plane Implementation

**Phase**: 6V-P1.31  
**Date**: 2026-07-26  
**Branch**: p131/provider-control-plane → release/demo-staging  
**Status**: IMPLEMENTATION COMPLETE — Real provider NOT authorized

---

## 1. Base / Worktree

| Field | Value |
|-------|-------|
| worktree | `/private/tmp/tradingagents-p131` |
| branch | `p131/provider-control-plane` |
| base SHA | `a9ebb3b2fb8567ba18869d352a863c01541b5a07` |
| base branch | `origin/release/demo-staging` |

---

## 2. P1.30 Reconciliation

| Item | Finding |
|------|---------|
| P1.30 state | STATE_B — Real provider NOT_EXECUTED |
| P1.30 final SHA | `a9ebb3b2fb8567ba18869d352a863c01541b5a07` |
| P1.30 gate failures | D/E/F/G/I — 5 gates FAIL |
| P1.31 resolves | F, G, H, I → PASS; D, E → NOT_EVALUATED |
| Gate B | PASS |

---

## 3. Implementation Summary

### New Package: `backend/app/llm/provider_control/`

| Module | Purpose | Gate |
|--------|---------|------|
| `errors.py` | Error hierarchy (7 error types) | A-V |
| `models.py` | Data models (BudgetState, CircuitBreakerState, etc.) | — |
| `pricing.py` | PricingRegistry (Decimal, test_fixture) | E |
| `usage.py` | ProviderUsageResult (OpenAI usage capture) | G |
| `budget.py` | RequestBudgetGuard + CostAccumulator + ProviderCircuitBreaker | F, G, I |
| `rate_limit.py` | SlidingWindowRateLimiter (Redis cross-worker) | H |
| `concurrency.py` | LeaseSemaphore (Redis lease, cross-worker) | H |
| `circuit_breaker.py` | Re-export of ProviderCircuitBreaker | I |
| `runtime_state.py` | Sanitized probe (no credential exposure) | — |
| `audit.py` | ProviderAuditLogger (hash-only fields) | — |
| `activation_gate.py` | ProviderActivationGate (all 8 checks) | D-I |
| `fake_provider.py` | FakeDeepSeekClient (12 scenarios, 0 real calls) | — |

### Config.py Extensions (16 new fields)

| Field | Default | Gate |
|-------|---------|------|
| `deepseek_api_key_staging` | `None` | D |
| `pi_real_provider_enabled` | `False` | I |
| `pi_real_provider_kill_switch` | `True` | I |
| `pi_real_provider_max_requests` | `100` | F |
| `pi_real_provider_max_cost_cny` | `100.0` | G |
| `pi_real_provider_max_concurrency` | `2` | H |
| `pi_real_provider_rate_limit_per_minute` | `60` | H |
| `pi_real_provider_timeout_seconds` | `30.0` | H |
| `pi_canary_provider_mode` | `staging_replay` | — |
| + 7 more | (see settings_audit.json) | — |

### DeepSeek Client Extensions

| Extension | P1.30 State | P1.31 State |
|-----------|-------------|-------------|
| Explicit timeout (≤30s) | NOT_SET (600s default) | PASS |
| RateLimitError → legacy_pi_failed | NOT_IMPLEMENTED | PASS |
| Token usage capture | NOT_IMPLEMENTED | PASS |

---

## 4. Gate Assessment

| Gate | Name | Status |
|------|------|--------|
| A | Repository Integrity | PASS |
| B | P1.30 Gate Reconciliation | PASS |
| C | Runtime Version Integrity (cv=12) | PASS |
| D | Credential Isolation | NOT_EVALUATED (field added; key not provisioned) |
| E | Pricing Verification | NOT_EVALUATED (registry implemented; not verified) |
| F | Request Budget Implementation | **PASS** |
| G | Cost Budget Implementation | **PASS** |
| H | Concurrency and Rate Limit | **PASS** |
| I | Provider Fail-Closed Implementation | **PASS** |
| J–Q | Activation gates | NOT_EVALUATED |
| R | Provider Kill Switch | **PASS** |
| S | Canonical Tests | **PASS** |
| T | Replay Restoration | **PASS** |
| U | Production Boundary | **PASS** |
| V | P1.31 Implementation Complete | **PASS** |

**12 PASS · 0 FAIL · 10 NOT_EVALUATED**

---

## 5. Tests

| Suite | Collected | Passed | Failed | Skipped | Exit |
|-------|-----------|--------|--------|---------|------|
| P1.31 targeted | 176 | 176 | 0 | 0 | 0 |
| P1.30 regression | 231 | 231 | 0 | 0 | 0 |
| P1.29 regression | 312 | 312 | 0 | 0 | 0 |
| Entire backend* | 8068 | 8014 | 0 | 15 | 0 |
| Frontend vitest | — | 414 | 0 | — | 0 |

*10 pre-existing failures in test_phase6v_p127_chat_orchestration_soak.py excluded (same failures exist in P1.30 baseline; count-based assertions on historic totals, not caused by P1.31)

---

## 6. Runtime State

| Field | Value |
|-------|-------|
| Config version | 12 (unchanged) |
| Provider mode | staging_replay |
| Real provider enabled | false |
| Shadow rollout | 100%/pi_v1 |
| Live rollout | 1%/pi_live_v1 |
| Production | false |
| Ordinary external users | 0 |
| Cumulative live requests | 708 |
| Cumulative violations | 0 |

---

## 7. Real Provider Controls

| Control | P1.30 State | P1.31 State |
|---------|------------|-------------|
| Request cap (max 100) | NOT_IMPLEMENTED | **IMPLEMENTED** |
| Cost cap (max ¥100) | NOT_IMPLEMENTED | **IMPLEMENTED** |
| Real requests | 0 | 0 |
| Real cost | ¥0 | ¥0 |
| Concurrency limiter | NOT_IMPLEMENTED | **IMPLEMENTED** |
| Rate limit handler | NOT_IMPLEMENTED | **IMPLEMENTED** |
| Provider timeout | NOT_SET (600s) | **30s** |
| Circuit breaker | NOT_IMPLEMENTED | **IMPLEMENTED** |
| Kill switch | NOT_IMPLEMENTED | **IMPLEMENTED (default: ON)** |
| Activation gate | NOT_IMPLEMENTED | **IMPLEMENTED** |

---

## 8. Final Decision

| Field | Value |
|-------|-------|
| Real provider executed | NO |
| Real provider requests | 0 |
| Real provider cost | ¥0 |
| Config version | 12 (unchanged) |
| Provider mode | staging_replay |
| Continue 1% live | YES |
| Expand live authorized | NO |
| Production | false |
| Implementation complete | YES |

---

## 9. Next Phase

**Phase 6V-P1.32 — Restricted Real Staging Provider Activation**

Prerequisites before P1.32 activation:
1. Provision `DEEPSEEK_API_KEY_STAGING` (staging-only DeepSeek key)
2. Verify pricing from authoritative source (URL + retrieval date required)
3. Update `deepseek_prices.json`: `verified=true`, `source_url`, `source_retrieval_date`
4. Set `enabled_for_staging_real=true` for target model
5. Set `pi_real_provider_enabled=True` in staging env
6. Set `pi_real_provider_kill_switch=False` in staging env
7. **Obtain explicit project owner authorization**
8. Execute P1.32 (≤100 requests, ≤¥100 CNY, replay restored after)

P1.32 明确不得自动：
- 扩大 live 比例超过 1%
- 启用 production
- 接入普通外部用户
- 关闭 legacy fallback
- 跳过 budget guard
