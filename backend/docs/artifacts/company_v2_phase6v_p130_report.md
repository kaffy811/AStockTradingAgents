# Phase 6V-P1.30 — Restricted Real Staging Provider Activation, Cost Safety and 1% Live Canary Verification

**Phase**: 6V-P1.30
**Date**: 2026-07-25
**Branch**: p130/restricted-real-provider → release/demo-staging
**Status**: STATE B — Real provider NOT_EXECUTED (pre-activation gates D/E/F/G/I FAIL)

---

## 1. Base / Worktree

| Field | Value |
|-------|-------|
| worktree | `/private/tmp/tradingagents-p130` |
| branch | `p130/restricted-real-provider` |
| base SHA | `6ee8fc4f693db5f8956901295515f8a2253406de` |
| deployment source SHA | `3a773241fe55535ee6f274473e11ec42459a65a3` |
| evidence SHA | (this commit) |
| push | `origin/release/demo-staging` |

---

## 2. P1.29 Reconciliation

| Item | Finding |
|------|---------|
| Evaluated replay-live gates | PASS (19/19 evaluated) |
| Real-provider gate before P1.30 | NOT_EVALUATED |
| P1.29 v15 proposal | Incorrect — assumes cv=13 and cv=14 were applied; neither was |
| Correct next monotonic cv | cv=13 (from current cv=12) |
| Gate B | PASS |

**Corrected phrasing:** "19/19 evaluated replay-live gates PASS; Gate S = NOT_EVALUATED"  
**P1.30 carries forward:** `replay_live_readiness = PASS; real_provider_readiness = NOT_EVALUATED`

---

## 3. Provider Adapter Audit

| Field | Value |
|-------|-------|
| Provider | DeepSeek |
| SDK | openai (OpenAI-compatible) |
| Adapter | `backend/app/llm/deepseek_client.py` → `DeepSeekClient` |
| API endpoint | `https://api.deepseek.com` |
| Default model | `deepseek-v4-flash` |
| Pro model | `deepseek-v4-pro` |
| Reasoner model | `deepseek-reasoner` |
| Auth env var | `DEEPSEEK_API_KEY` |
| Staging-isolated credential | **NOT FOUND** |
| Token usage captured | **NO** |
| Explicit timeout | **NOT SET** |
| Rate limit handler | **NOT IMPLEMENTED** |

Pipeline integrity: Analysis Agent → Review Agent → live arbitration → legacy fallback. Architecture correct. Implementation gaps prevent safe activation.

---

## 4. Pre-Activation Gate Assessment

| Gate | Name | Status | Finding |
|------|------|--------|---------|
| D | Credential Isolation | **FAIL** | No `DEEPSEEK_API_KEY_STAGING`. Cannot confirm staging isolation. |
| E | Pricing Verification | **FAIL** | No pricing config in codebase. Cannot compute cost without verified per-token prices. |
| F | Request Budget | **FAIL** | `PI_REAL_PROVIDER_MAX_REQUESTS` not in Settings or runtime code. |
| G | Cost Budget | **FAIL** | `PI_REAL_PROVIDER_MAX_COST_CNY` not in Settings. Token usage not captured. |
| I | Provider Fail-Closed | **FAIL** | `PI_REAL_PROVIDER_ENABLED` flag not in Settings. P1.29 design artifact only; never implemented. |

**Result: State B — real provider execution = NOT_EXECUTED**

---

## 5. Controls

| Control | Status |
|---------|--------|
| Request cap (max 100) | NOT_IMPLEMENTED |
| Cost cap (max ¥100) | NOT_IMPLEMENTED |
| Actual real requests | 0 |
| Actual real cost | ¥0 |
| Concurrency limiter | NOT_IMPLEMENTED |
| Rate limit handler | NOT_IMPLEMENTED |
| Provider timeout | NOT_SET (SDK default 600s) |
| Circuit breaker | NOT_IMPLEMENTED |

---

## 6. Runtime Versions

| Stage | Config Version | Provider Mode | Real Provider |
|-------|---------------|---------------|---------------|
| Before | 12 | staging_replay | false |
| Active (real provider) | N/A | NOT_EXECUTED | NOT_EXECUTED |
| After (restoration) | 12 | staging_replay | false |

No version change. cv=12 maintained throughout.

---

## 7. R1–R8 Windows

| Window | Planned | Actual Real Calls | Status |
|--------|---------|-------------------|--------|
| R1 connectivity | 5 | 0 | NOT_EXECUTED |
| R2 approved answers | 45 | 0 | NOT_EXECUTED |
| R3 data gap | 10 | 0 | NOT_EXECUTED |
| R4 safety rejection | 10 | 0 | NOT_EXECUTED |
| R5 multi-turn | 10 | 0 | NOT_EXECUTED |
| R6 concurrency | 5 | 0 | NOT_EXECUTED |
| R7 timeout/error | 5 | 0 | NOT_EXECUTED |
| R8 final stable | 10 | 0 | NOT_EXECUTED |
| **Total** | **100** | **0** | **NOT_EXECUTED** |

---

## 8. Cost

| Metric | Value |
|--------|-------|
| Input tokens | 0 |
| Output tokens | 0 |
| Reported cost | ¥0 |
| Estimated cost | ¥0 |
| Total cost | ¥0 |
| Budget remaining | N/A (budget guard not implemented) |
| Request cap remaining | N/A |

---

## 9. Safety / Fallback

| Metric | Value |
|--------|-------|
| Approved Pi visible (real) | NOT_EXECUTED |
| Rejected Pi visible | NOT_EXECUTED |
| Timeout Pi visible | NOT_EXECUTED |
| Error Pi visible | NOT_EXECUTED |
| Budget-blocked Pi visible | NOT_EXECUTED |
| Fallback success (replay continued) | 1.0 |
| Duplicates | 0 |
| Terminal violations | 0 |

Replay-live safety maintained: continued observation of 5000 requests, 42 live-selected, 0 violations.

---

## 10. Browser E2E

| Metric | Value |
|--------|-------|
| Total cases | 50 |
| Passed | 50 |
| Failed | 0 |
| Real-provider cases | NOT_EXECUTED |
| Credential leakage | 0 |
| Provider metadata leakage | 0 |
| Duplicate assistant messages | 0 |

---

## 11. Tests

| Suite | Collected | Passed | Failed | Skipped | Exit |
|-------|-----------|--------|--------|---------|------|
| P1.30 targeted | 231 | 231 | 0 | 0 | 0 |
| P1.29 regression | 312 | 312 | 0 | 0 | 0 |
| P1.28 regression | 187 | 187 | 0 | 0 | 0 |
| Entire backend | 7904 | 7862 | 0 | 42 | 0 |
| Frontend vitest | — | 414 | 0 | — | 0 |
| Frontend build | — | — | — | 195 modules | 0 |
| Browser E2E | 50 | 50 | 0 | 0 | 0 |

---

## 12. Gate A–U

| Gate | Name | Status |
|------|------|--------|
| A | Repository Integrity | PASS |
| B | P1.29 Gate Reconciliation | PASS |
| C | Runtime Version Integrity | PASS |
| D | Credential Isolation | **FAIL** |
| E | Pricing Verification | **FAIL** |
| F | Request Budget | **FAIL** |
| G | Cost Budget | **FAIL** |
| H | Concurrency and Rate Limit | NOT_EVALUATED |
| I | Provider Fail-Closed | **FAIL** |
| J | Activation Integrity | NOT_EVALUATED |
| K | Real Provider Connectivity | NOT_EVALUATED |
| L | Review and Safety | NOT_EVALUATED |
| M | Legacy Fallback (real provider) | NOT_EVALUATED |
| N | Exactly-Once UX (real provider) | NOT_EVALUATED |
| O | Performance | NOT_EVALUATED |
| P | Resources | NOT_EVALUATED |
| Q | Browser E2E | PARTIAL (50/50 replay PASS; real NOT_EXECUTED) |
| R | Provider Kill Switch | NOT_EVALUATED |
| S | Canonical Tests | PASS |
| T | Replay Restoration | PASS |
| U | Production Boundary | PASS |

**6 PASS · 5 FAIL · 1 PARTIAL · 10 NOT_EVALUATED**

---

## 13. Final Decision

| Field | Value |
|-------|-------|
| Real provider executed | NO |
| Real provider validation passed | NO |
| Real provider requests | 0 |
| Real provider cost | ¥0 |
| Shadow rollout | 100% |
| Live rollout | 1% |
| Config version | 12 (unchanged) |
| Provider mode | staging_replay |
| Real provider enabled | false |
| Continue 1% live | YES |
| Expand live authorized | NO |
| Production | false |
| Ordinary external users | 0 |

---

## 14. Implementation Required Before P1.31

| # | Item | File |
|---|------|------|
| 1 | `DEEPSEEK_API_KEY_STAGING` credential provisioned | `.env.staging.local` / secret injection |
| 2 | `deepseek_api_key_staging` field in Settings | `backend/app/core/config.py` |
| 3 | `pi_real_provider_enabled` setting (default: false) | `backend/app/core/config.py` |
| 4 | `pi_real_provider_max_requests` setting | `backend/app/core/config.py` |
| 5 | `pi_real_provider_max_cost_cny` setting | `backend/app/core/config.py` |
| 6 | Token usage capture in `DeepSeekClient` | `backend/app/llm/deepseek_client.py` |
| 7 | Explicit timeout on OpenAI client (≤30s) | `backend/app/llm/deepseek_client.py` |
| 8 | `RateLimitError` → `legacy_pi_failed` fallback | `backend/app/llm/deepseek_client.py` |
| 9 | `RequestBudgetGuard` (Redis atomic INCR) | `backend/app/agent_runtime/provider_budget_guard.py` |
| 10 | `CostAccumulator` (Redis INCRBYFLOAT) | `backend/app/agent_runtime/provider_budget_guard.py` |
| 11 | `ProviderCircuitBreaker` | `backend/app/agent_runtime/provider_budget_guard.py` |
| 12 | Budget guard wired into Pi agent call path | `backend/app/agents/financial_agent.py` |
| 13 | Verified pricing table for `deepseek-v4-flash` and `deepseek-v4-pro` | `backend/app/llm/pricing/deepseek_prices.json` |
| 14 | `pi_real_provider_audit` DB table migration | new Alembic migration |
| 15 | `GET /pi-canary/provider-budget` probe endpoint | `backend/app/routers/` |

---

## 15. 下一阶段

**Phase 6V-P1.31 — 实现 Budget Guard 基础设施 + 受限真实 Provider 激活**

P1.31 首先必须完成上述 15 项实现，通过独立验证后，再申请项目负责人显式授权真实 Provider 激活。

P1.31 明确不得自动：
- 扩大 live 比例超过 1%
- 启用 production
- 接入普通外部用户
- 关闭 legacy fallback
- 修改 stable shadow/live salt

**需要项目负责人显式授权方可推进 P1.31 真实 Provider 激活。**
