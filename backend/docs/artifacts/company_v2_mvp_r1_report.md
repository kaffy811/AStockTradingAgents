# Phase MVP-R1 — Invite-Only MVP Launch

**Phase**: MVP-R1  
**Date**: 2026-07-26  
**Branch**: mvp-r1/invite-only-launch → release/demo-staging  
**Status**: **INVITE_ONLY_LEGACY_MVP_READY — State B**

---

## 1. P0 Blockers Resolved

| Blocker | Resolution |
|---|---|
| P0-1: Gate C — only 3/8 checks in call path | ProviderControlPlane wires all 8 checks (5 Redis-backed) |
| P0-2: PricingRegistry reads empty `"pricing"` key → Decimal("0") | deepseek_prices.json updated with official CNY `"pricing"` key |

---

## 2. P1.33 Partial Gates → PASS

| Gate | Before | After |
|---|---|---|
| C (Call Path Budget Controls) | PARTIAL (3/8) | **PASS** (8/8) |
| G (Budget Guard Currency) | PARTIAL (CNY estimate from USD) | **PASS** (official CNY, no FX) |

---

## 3. Official CNY Pricing

| Model | Cache Hit Input | Cache Miss Input | Output | Reasoning |
|---|---|---|---|---|
| deepseek-v4-flash | ¥0.02/1M | ¥1/1M | ¥2/1M | ¥2/1M |
| deepseek-v4-pro | ¥0.025/1M | ¥3/1M | ¥6/1M | ¥6/1M |

Cost per request (deepseek-v4-flash, 2000 input + 500 output, no cache): ≈ ¥0.003.  
30 requests ≈ ¥0.09 — well within ¥20 budget.

---

## 4. Launch Gate Assessment

| Gate | Status |
|---|---|
| L1 — Core User Flow | **PASS** |
| L2 — Invite-Only Access | **PASS** |
| L3 — Data Source and Freshness | **PASS** |
| L4 — Chat and Multi-Turn | **PASS** |
| L5 — Review and Disclaimer | **PASS** |
| L6 — Legacy Fallback | **PASS** |
| L7 — No Duplicate or Session Mix-Up | **PASS** |
| L8 — Feedback | **PASS** |
| L9 — Analytics | **PASS** |
| L10 — Monitoring | **PASS** |
| L11 — Quota and Abuse Protection | **PASS** |
| L12 — Kill Switches | **PASS** |
| L13 — Canonical Tests | **PASS** |
| L14 — Secret Protection | **PASS** |

**14 PASS · 0 FAIL**

| RP Gate | Status |
|---|---|
| RP1 — Formal Control Path | **PASS** |
| RP2 — Staging Credential | NOT_EXECUTED |
| RP3 — Real Connectivity | NOT_EXECUTED |
| RP4 — Usage and Cost | NOT_EXECUTED |
| RP5 — Safety and Fallback | NOT_EXECUTED |
| RP6 — Replay Restoration | **PASS** |

---

## 5. State B

| Field | Value |
|---|---|
| Real provider calls | 0 |
| Real provider cost | ¥0 |
| Config version | 12 (unchanged) |
| Provider mode | staging_replay |
| Staging credential | NOT_SET |

---

## 6. Final Decision

| Field | Value |
|---|---|
| invite_only_legacy_mvp | **READY** |
| real_provider_feature_visible | false |
| Invite users may be added | **true** |
| Real AI provider may be advertised | false |
| Public production authorized | false |

---

## 7. Week-1 Plan

1. Invite 20–50 users
2. Monitor daily: questions, success rate, fallback rate, feedback
3. Day-7 Week-1 Review
4. Pick 3 highest-priority issues
5. Real provider activation in parallel (when credential provisioned)
