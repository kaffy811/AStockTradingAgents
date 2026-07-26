# Phase 6V-P1.32 — MVP Release Candidate

**Phase**: 6V-P1.32  
**Date**: 2026-07-26  
**Branch**: p132/real-provider-mvp-release → release/demo-staging  
**Status**: MVP Release Candidate — **State B (Real Provider NOT_EXECUTED)**

---

## 1. Base / Worktree

| Field | Value |
|---|---|
| worktree | `/private/tmp/tradingagents-p132` |
| branch | `p132/real-provider-mvp-release` |
| base SHA | `d7ccdf955a96303f3559f5883773b12f0c8661e8` |
| base branch | `origin/release/demo-staging` |

---

## 2. P1.31 Reconciliation

| Item | Finding |
|---|---|
| P1.31 final SHA | `d7ccdf9` |
| P1.31 gate passes | 12 PASS |
| P1.31 call path gap | Gate wired in P1.32 via `check_real_provider_gate()` |
| P1.32 resolves | Gate J (call path wiring), Gate S (invite), Gate U (feedback), Gate V (analytics), Gate W (monitoring) |

---

## 3. P1.32 Implementation Summary

### Provider Control Plane Wiring

| Item | Before P1.32 | After P1.32 |
|---|---|---|
| ProviderActivationGate in call path | NOT WIRED | **WIRED** (factory.py) |
| Gate result logged | NO | **YES** (log.warning on block) |
| Fail-closed by default | YES (module-level) | **YES (call path level)** |

### New MVP Features

| Feature | Table | Migration | Endpoints |
|---|---|---|---|
| Invite-only access | `mvp_invite` | `n2o3p4q5r6s7` | check / redeem / create |
| Answer feedback | `chat_feedback` | `n2o3p4q5r6s7` | POST /chat/feedback |
| Analytics events | `mvp_analytics_event` | `n2o3p4q5r6s7` | POST /mvp/analytics/event |
| MVP health probe | — | — | GET /mvp/health |

---

## 4. Gate Assessment

| Gate | Name | Status |
|---|---|---|
| A | Repository Integrity | **PASS** |
| B | Provider Control Plane | **PASS** |
| C | Official Model Verification | NOT_EVALUATED |
| D | Pricing Verification | NOT_EVALUATED |
| E | Staging Credential Isolation | NOT_EVALUATED |
| F | Request Budget | **PASS** |
| G | Cost Budget | **PASS** |
| H | Real Provider Connectivity | NOT_EVALUATED |
| I | Provider Usage Capture | NOT_EVALUATED |
| J | Provider Safety Review | **PASS** |
| K | Legacy Fallback | **PASS** |
| L | Provider Kill Switch | **PASS** |
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

**20 PASS · 0 FAIL · 6 NOT_EVALUATED**

Gates C/D/E/H/I require `DEEPSEEK_API_KEY_STAGING` → deferred to P1.33.

---

## 5. Tests

| Suite | Collected | Passed | Failed | Exit |
|---|---|---|---|---|
| P1.32 targeted | 119 | 119 | 0 | 0 |
| P1.31 regression | 176 | 176 | 0 | 0 |
| P1.30 regression | 231 | 231 | 0 | 0 |
| P1.29 regression | 312 | 312 | 0 | 0 |
| **Combined regression** | **719** | **719** | **0** | **0** |

---

## 6. State B — Real Provider

| Field | Value |
|---|---|
| Real provider executed | NO |
| Real provider calls | 0 |
| Real provider cost | ¥0 |
| Config version | 12 (unchanged) |
| Provider mode | staging_replay |
| Staging credential | NOT_SET |
| Gate D (credential) | NOT_EVALUATED |
| Gate E (pricing) | NOT_EVALUATED |

---

## 7. Runtime Final State

| Field | Value |
|---|---|
| Config version | 12 |
| Provider mode | staging_replay |
| Shadow rollout | 100% / pi_v1 |
| Live rollout | 1% / pi_live_v1 |
| Real provider enabled | false |
| Kill switch | true (default) |
| Production | false |
| Ordinary external users | 0 |
| Cumulative live requests | 708 |
| Cumulative violations | 0 |

---

## 8. MVP Core Flow

| Step | Status |
|---|---|
| Login | PASS |
| Invite-only access | **PASS (P1.32)** |
| Stock search | PASS |
| Company financial page | PASS |
| Chat single-turn | PASS |
| Chat multi-turn | PASS |
| Review Agent gate | PASS |
| Legacy fallback | PASS |
| Disclaimer | PASS |
| Data source attribution | PASS |
| History sessions | PASS |
| Answer feedback | **PASS (P1.32)** |

---

## 9. Final Decision

| Field | Value |
|---|---|
| Real provider validation passed | NO (State B) |
| MVP core flow passed | YES |
| Invite-only passed | YES |
| Feedback passed | YES |
| Analytics passed | YES |
| Monitoring passed | YES |
| **mvp_release_candidate** | **true** |
| Invite-only launch recommended | YES |
| Public production authorized | NO |
| Continue pre-launch optimization | **NO** |

---

## 10. Next Phase

**MVP-R1 — Invite-Only MVP Launch**

1. Invite 20–50 initial users
2. Set per-user daily quota (10 questions/day)
3. Set total cost budget (¥50/week)
4. Monitor daily via `mvp_analytics_event` queries
5. Weekly feedback review from `chat_feedback`
6. One-week retrospective before expanding

**P1.33 — Real Provider Activation** (when DEEPSEEK_API_KEY_STAGING provisioned)

Prerequisites: staging key + pricing verification + explicit project owner authorization  
Scope: ≤100 real requests, ≤¥100 CNY, restore replay after (cv: 12→13→14)
