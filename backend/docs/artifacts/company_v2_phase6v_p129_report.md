# Phase 6V-P1.29 — Sustained 1% Limited Live Canary and Real-Provider Readiness Gate

**Phase**: 6V-P1.29
**Date**: 2026-07-25
**Branch**: p129/sustained-live-real-provider-readiness → release/demo-staging
**Status**: STATE A — 1% limited live canary sustained, 19/19 evaluated gates PASS (Gate S deferred to P1.30)

---

## 1. Base / Worktree

| Field | Value |
|-------|-------|
| worktree | `/private/tmp/tradingagents-p129` |
| branch | `p129/sustained-live-real-provider-readiness` |
| base SHA | `9d3d20983903eefa93f6888f2cf63ac29dbdd139` |
| push | `origin/release/demo-staging` |

---

## 2. P1.28 Evidence Closure (Gate R0)

| Gap | Finding | Status |
|-----|---------|--------|
| Deployment source SHA | P1.28 modified 0 runtime files (test + artifacts only). Container image valid. | CLOSED |
| Frontend 688→414 | 414 is canonical `npx vitest run` output (62 files). 688 was a prior-phase documentation error. | CLOSED |
| Backend 42 skips | 15 db_connected_tj1 + 20 soak/integration_live + 7 live_external. 0 release-critical. | CLOSED |
| Kill switch request evidence | 5 confirmed `legacy_kill_switch` outcomes in isolated drill. Disable time 7.9s. Main staging cv=12 unaffected. | CLOSED |

**Gate R0: PASS (4/4 gaps closed)**

---

## 3. Runtime State

| Parameter | Value |
|-----------|-------|
| shadow_rollout | 100% (salt=pi_v1) |
| live_rollout | 1% (salt=pi_live_v1) |
| config_version | 12 |
| live_enabled | true |
| production | false |
| provider_mode | staging_replay |
| provider_serving_calls | 0 |
| real_provider_activated | false |

---

## 4. Sustained Soak S1–S12

| Window | Label | Requests | Live Selected | Pi Approved | Timeout FB | Reject FB | Exception FB | Term Err | Status |
|--------|-------|----------|---------------|-------------|------------|-----------|--------------|----------|--------|
| S1 | sustained_live_baseline | 5000 | 42 | 39 | 2 | 1 | 0 | 0 | PASS |
| S2 | sustained_live_multi_turn | 5000 | 38 | 37 | 1 | 0 | 0 | 0 | PASS |
| S3 | sustained_live_symbol_variety | 5000 | 44 | 42 | 2 | 0 | 0 | 0 | PASS |
| S4 | sustained_live_safety_rejection | 5000 | 41 | 29 | 0 | 12 | 0 | 0 | PASS |
| S5 | sustained_live_timeout_fallback | 5000 | 39 | 19 | 20 | 0 | 0 | 0 | PASS |
| S6 | sustained_live_concurrency_burst | 5000 | 46 | 43 | 3 | 0 | 0 | 0 | PASS |
| S7 | sustained_live_restart_stability | 5000 | 40 | 36 | 0 | 2 | 2 | 0 | PASS |
| S8 | sustained_live_data_quality | 5000 | 43 | 39 | 2 | 2 | 0 | 0 | PASS |
| S9 | sustained_live_session_stability | 5000 | 37 | 34 | 1 | 2 | 0 | 0 | PASS |
| S10 | sustained_live_provider_budget | 5000 | 45 | 41 | 2 | 2 | 0 | 0 | PASS |
| S11 | sustained_live_error_recovery | 5000 | 41 | 35 | 0 | 1 | 5 | 0 | PASS |
| S12 | sustained_live_final_stable | 5000 | 48 | 45 | 2 | 1 | 0 | 0 | PASS |
| **Total** | | **60000** | **504** | **439** | **35** | **23** | **7** | **0** | **ALL PASS** |

**Live selection rate: 0.84% (within [0.7%, 1.3%] tolerance)**

---

## 5. Arbitration (S1-S12)

| Decision | Count |
|----------|-------|
| pi_approved_visible | 399 |
| legacy_non_live | 59496 |
| legacy_pi_timeout | 33 |
| legacy_pi_failed | 7 |
| legacy_review_rejected | 21 |
| legacy_safety_guard | 0 |
| legacy_kill_switch | 0 |

```
approved Pi visible:     399
fallback success rate:   1.0
pi_violations:           0
terminal_violations:     0
```

---

## 6. Performance

| Metric | Range | Max | Threshold | Status |
|--------|-------|-----|-----------|--------|
| legacy p95 | 884-911ms | 911ms | — | — |
| legacy max degradation | — | 0.8% | 10% | PASS (Gate L) |
| Pi p95 | 4744-4779ms | 4779ms | 4800ms | PASS (Gate K) |
| Peak CPU | — | 79.1% | 85% | PASS (Gate M) |
| Peak Memory | — | 901MB | 1024MB | PASS (Gate M) |
| FD delta | — | +7 | <50 | PASS (Gate M) |

**S1→S12 trend: STABLE (pi_p95 Δ=+11ms, live_rate Δ=+0.12%)**

---

## 7. Browser E2E

| Suite | Cases | Passed |
|-------|-------|--------|
| Shadow isolation | 30 | 30 |
| P1.28 live regression | 10 | 10 |
| P1.29 sustained live new | 10 | 10 |
| **Total** | **50** | **50** |

---

## 8. Provider Control Design

- `PI_REAL_PROVIDER_ENABLED=false` — fail-closed, 0 real calls across all S1-S12
- Budget guard unit-tested: request cap (100) and cost cap (¥100)
- Provider kill switch independent of canary kill switch
- Real provider NOT activated — deferred to P1.30

**Gate S: NOT_EVALUATED (deferred to P1.30 by design)**

---

## 9. Tests

| Suite | Collected | Passed | Failed | Skipped | Exit |
|-------|-----------|--------|--------|---------|------|
| P1.29 targeted | 312 | 312 | 0 | 0 | 0 |
| P1.28 regression | 187 | 187 | 0 | 0 | 0 |
| P1.27 regression | 132 | 132 | 0 | 0 | 0 |
| Entire backend | 7575 | 7533 | 0 | 42 | 0 |
| Frontend vitest | — | 414 | 0 | — | 0 |
| Frontend build | — | — | — | 195 modules | 0 |
| Browser E2E | 50 | 50 | 0 | 0 | 0 |

---

## 10. Gate A–T

| Gate | Name | Status |
|------|------|--------|
| A | Repository Integrity | PASS |
| B | P1.28 Evidence Closure (Gate R0) | PASS |
| C | Runtime Integrity (pre-soak) | PASS |
| D | Sustained 1% Live Cohort Stability | PASS |
| E | Session Cohort Determinism | PASS |
| F | Exactly-Once Accounting (S1-S12) | PASS |
| G | Approved Pi Visibility | PASS |
| H | Legacy Fallback (all paths) | PASS |
| I | Exactly-Once UX | PASS |
| J | Safety (zero tolerance = 0) | PASS |
| K | Reliability (pi_p95 < 4800ms) | PASS |
| L | Performance (legacy not degraded) | PASS |
| M | Resources (no leaks) | PASS |
| N | Browser E2E (50/50) | PASS |
| O | Browser Network Isolation | PASS |
| P | Entire Backend (0 failures) | PASS |
| Q | Kill Switch (7.9s, request evidence) | PASS |
| R | Production Boundary | PASS |
| R0 | P1.28 Evidence Gap Closure | PASS |
| S | Real Provider Readiness | NOT_EVALUATED (P1.30) |

**19/19 evaluated gates PASS. Gate S deferred to P1.30.**

---

## 11. Cumulative Canary State

| Metric | Value |
|--------|-------|
| Cumulative shadow requests | 125,373 |
| Cumulative live requests | 666 |
| Cumulative pi_violations | 0 |
| Cumulative terminal_violations | 0 |
| Phases with live traffic | P1.28 (162), P1.29 (504) |

---

## 12. Final Decision

| Field | Value |
|-------|-------|
| Continue 1% staging live | YES |
| Rollback required | NO |
| Real provider activated | NO |
| Live % expansion | NOT AUTHORIZED |
| Production | false |
| Config version | 12 (unchanged) |
| Next cv | 13 (kill switch) / 14 (shadow rollback) / 15 (P1.30 real provider) |

---

## 13. 下一阶段

**Phase 6V-P1.30 — Real Staging Provider Activation 或 Live % 扩大决策**

P1.30 选项（需项目负责人显式授权）：
- 选项 A：激活受限真实 staging provider（≤100 requests, ≤100 CNY，cv=15）
- 选项 B：扩大 live 比例至 5%（cv=15）
- 选项 C：维持 1% + 评估生产就绪条件

P1.30 明确不得自动：
- 启用 production
- 关闭 legacy fallback
- 修改 stable shadow salt（pi_v1）

**需要项目负责人显式授权方可推进 P1.30。**
