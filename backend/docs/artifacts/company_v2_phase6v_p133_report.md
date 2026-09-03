# Phase 6V-P1.33 — Final MVP Gate

**Phase**: 6V-P1.33
**Date**: 2026-07-26
**Branch**: p133/restricted-deepseek-final-mvp-gate -> release/demo-staging
**Status**: MVP Gate Complete — **State B (Real Provider NOT_EXECUTED)**

---

## 1. Scope

P1.33 is the final pre-launch technical gate phase. It resolves outstanding verification items from P1.32:

| Item | Status |
|---|---|
| P1.32 mvp_release_candidate reconciliation | COMPLETE |
| Official DeepSeek model ID verification | PASS |
| Official DeepSeek pricing verification | PASS |
| Provider call path audit | COMPLETE (Gap documented) |
| Fail-closed preflight | PASS |
| Real provider activation | NOT_EXECUTED (State B) |
| Replay restoration | PASS (nothing changed) |

---

## 2. P1.32 Release Reconciliation

P1.32 `mvp_release_candidate=true` describes **product closure readiness** (invite-only demo, feedback, analytics, monitoring all implemented), NOT real provider readiness. Gates C/D/E/H/I were NOT_EVALUATED in P1.32. P1.33 resolves E (model), F (pricing), H (fail-closed) and documents D (credential) and C (path gap) honestly.

---

## 3. Verified Findings

### Official Model IDs (Gate E: PASS)
- `deepseek-v4-flash` — official current API ID (NOT alias)
- `deepseek-v4-pro` — official current API ID
- `deepseek-chat` — DEPRECATED 2026-07-24 (maps to deepseek-v4-flash)
- `deepseek-reasoner` — DEPRECATED 2026-07-24 (maps to deepseek-v4-flash thinking)
- `config.py deepseek_default_model="deepseek-v4-flash"` — already correct, no change needed

### Official Pricing (Gate F: PASS)
Source: `api-docs.deepseek.com/quick_start/pricing` (2026-07-26)

| Model | Input (cache miss) | Cache hit | Output |
|---|---|---|---|
| deepseek-v4-flash | $0.14/1M | $0.0028/1M | $0.28/1M |
| deepseek-v4-pro | $0.435/1M | $0.003625/1M | $0.87/1M |

`deepseek_prices.json` updated: `pricing_mode=official`, `verified=true`, `currency=USD`.

### Budget Guard Currency (Gate G: PARTIAL)
Budget guard uses CNY (`pi_real_provider_max_cost_cny=100.0`). Verified prices are USD. Exchange rate estimate: 7.20 CNY/USD. Conservative floor: 7.0 CNY/USD for budget guard. 100 requests approximately CNY 0.121 — well within budget.

### Provider Call Path (Gate C: PARTIAL)
`check_real_provider_gate()` in factory.py checks: kill_switch + enabled + credential (3/8 checks). Budget/concurrency/rate-limit require Redis clients not currently injected. **Risk: LOW in State B** — credential gate blocks all real calls before budget checks needed. Remediation documented.

---

## 4. Gate Assessment

| Gate | Name | Status |
|---|---|---|
| A | Repository Integrity | **PASS** |
| B | Provider Control Plane | **PASS** |
| C | Call Path Budget Controls | **PARTIAL** |
| D | Staging Credential | NOT_EVALUATED |
| E | Official Model Verification | **PASS** |
| F | Official Pricing Verification | **PASS** |
| G | Budget Guard Currency | **PARTIAL** |
| H | Fail-Closed Preflight | **PASS** |
| I | Real Provider Connectivity | NOT_EXECUTED |
| J | Real Provider Results | NOT_EXECUTED |
| K | Usage Capture | NOT_EXECUTED |
| L | Cost Verification | NOT_EXECUTED |
| M | Replay Restoration | **PASS** |
| N | Core Stock Flow | **PASS** |
| O | Core Chat Flow | **PASS** |
| P | Multi-Turn Context | **PASS** |
| Q | Data Source and Freshness | **PASS** |
| R | Disclaimer and Compliance | **PASS** |
| S | Invite-Only Access | **PASS** |
| T | User Quota | **PASS** |
| U | Feedback Loop | **PASS** |
| V | Product Analytics | **PASS** |
| W | Error Monitoring | **PASS** |
| X | Browser E2E | **PASS** |
| Y | Canonical Tests | **PASS** |
| Z | Production Boundary | **PASS** |

**19 PASS · 2 PARTIAL · 1 NOT_EVALUATED · 4 NOT_EXECUTED · 0 FAIL**

---

## 5. Tests

| Suite | Collected | Passed | Failed |
|---|---|---|---|
| P1.33 targeted | 112 | 112 | 0 |

---

## 6. State B — Real Provider

| Field | Value |
|---|---|
| Real provider executed | NO |
| Real provider calls | 0 |
| Real provider cost | $0 / CNY 0 |
| Config version | 12 (unchanged) |
| Provider mode | staging_replay |
| Staging credential | NOT_SET |

---

## 7. Final Decision

| Field | Value |
|---|---|
| Model verification passed | YES |
| Pricing verification passed | YES |
| Fail-closed verified | YES |
| Provider path audited | YES |
| Real provider validation | NOT_EXECUTED (State B) |
| **mvp_release_candidate** | **true** |
| Invite-only launch authorized | **YES** |
| Public production authorized | NO |
| Real provider authorized | NO |
| **Continue pre-launch phases** | **NO** |

---

## 8. Next Steps

**MVP-R1 — Invite-only Launch** (immediate)
1. Invite 20-50 initial users
2. Set per-user daily quota (10 questions/day)
3. Monitor via mvp_analytics_event
4. Weekly feedback review from chat_feedback

**Real Provider Activation** (when ready, parallel to MVP-R1)
- Provision DEEPSEEK_API_KEY_STAGING
- Inject Redis clients into budget/concurrency guards (Gate C remediation)
- Validate exchange rate for budget guard (Gate G remediation)
- Obtain explicit project owner authorization
- Proceed as P1.33.5 or equivalent: 100 requests max, CNY 100 budget cap
