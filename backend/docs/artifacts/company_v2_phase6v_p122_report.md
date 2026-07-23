# Phase 6V-P1.22: Sustained 75% Shadow Soak — Final Report

**Phase:** 6V-P1.22  
**Date:** 2026-07-23  
**Base SHA:** 43130fcf8e348b6c8dbdb27accee1e304638b95d (P1.21 final)  
**Rollout:** 75% shadow (config_version=8, stable_bucket_salt=pi_v1)  
**Live:** false | **Production enabled:** false | **Dry-run:** true  

---

## Summary

Phase 6V-P1.22 executed a sustained 10-window (U1–U10) shadow soak at 75% rollout. Across 14,034 eligible requests, 10,526 were selected (75.01%), with zero safety violations, zero reliability failures, and Pi_p95 remaining below the 4,800ms review threshold in all windows. Cumulative totals from P1.8 through P1.22 stand at 45,373 selected with 0 violations across the entire program.

**Final decision: continue 75% shadow — 100% promotion NOT authorized (Gate C = UNKNOWN).**

---

## Gate Results (A–M)

| Gate | Name | Status | Key Evidence |
|---|---|---|---|
| A | Repository Integrity | PASS | SHA verified; P1.21 artifacts intact |
| B | Configuration Integrity | PASS | rollout=75, config_version=8, live=false |
| C | Runtime Provenance | UNKNOWN | Loader integration verified; deployed probe not accessible |
| D | Sustained Observation | PASS | 10 windows, 10,526 selected, all diversity gates met |
| E | Bucket Stability | PASS | P1.21 ↔ P1.22 cohort identity replay verified |
| F | 100% Policy Readiness | PASS | 75% ⊆ 100% superset verified offline; not applied |
| G | Safety | PASS | correctness=1.0, violations=0, pi_leakage=0 |
| H | Reliability | PASS | timeout=0.0, fallback=0.0, terminal_completion=1.0 |
| I | Performance | PASS | pi_p95 4743–4781ms; burst U5 recovers by U10; no review |
| J | Resources | PASS | CPU max 52% (burst), memory max 403MB; U10 recovery confirmed |
| K | Browser / UI | PASS | 24/24 browser regression; vitest 688/688; build clean |
| L | Test Evidence | PASS | 6372/6387 PASS (15 known skips), 0 failures, secret scan clean |
| M | Rollback Readiness | PASS | 75/v8 → 50/v9 rollback verified offline; not applied |

**12 PASS | 1 UNKNOWN | 0 FAIL**

---

## Observation Windows

| Window | Type | Eligible | Selected | Rate | Pi_p95 | CPU | Memory | FD |
|---|---|---|---|---|---|---|---|---|
| U1 | standard_warm | 1404 | 1053 | 75.00% | 4743ms | 31% | 390MB | 431 |
| U2 | post_restart | 1401 | 1051 | 75.02% | 4748ms | 30% | 389MB | 430 |
| U3 | multi_turn_heavy | 1407 | 1055 | 74.98% | 4752ms | 33% | 393MB | 435 |
| U4 | gap_stale_revised | 1398 | 1049 | 75.03% | 4746ms | 32% | 391MB | 432 |
| U5 | concurrency_burst | 1412 | 1059 | 75.00% | 4781ms | 52% | 403MB | 476 |
| U6 | dry_run_parallel | 1403 | 1052 | 74.98% | 4749ms | 31% | 391MB | 432 |
| U7 | long_running_a | 1406 | 1055 | 75.03% | 4754ms | 33% | 394MB | 434 |
| U8 | worker_rotation | 1400 | 1050 | 75.00% | 4748ms | 30% | 390MB | 430 |
| U9 | long_running_b | 1404 | 1053 | 75.00% | 4756ms | 33% | 395MB | 435 |
| U10 | final_stable | 1399 | 1049 | 74.98% | 4743ms | 30% | 391MB | 430 |
| **Total** | — | **14034** | **10526** | **75.01%** | — | — | — | — |

---

## Critical Findings

### Performance (Gate I)
All 10 windows remained in the warning band (4700–4799ms). The burst spike in U5 (pi_p95=4781ms, CPU=52%) is attributable to the concurrency burst scenario and resolves fully by U10 (pi_p95=4743ms), matching the U1 baseline. No window exceeded the 4800ms review threshold, and pi>5s=0, pi>6s=0 across the entire soak.

### Runtime Provenance (Gate C — UNKNOWN)
The snapshot function `get_effective_shadow_config_snapshot()` was added to `app/canary_policy.py` and wired into the application lifespan startup. It calls `load_canary_config(settings)` using real Pydantic Settings, formally verifying the loader integration. However, the deployed staging runtime was not probed directly. Gate C remains UNKNOWN — not PASS, not FAIL.

This is the sole gate blocking 100% promotion authorization.

### Bucket Stability
The 75% cohort (bucket < 7500/10000) from P1.21 is identical to P1.22 (same salt `pi_v1`, same algorithm), verified by identity replay. Restart (U2) and worker rotation (U8) both confirmed cohort preservation. Long-running windows U7 and U9 show only +1MB / +1 FD delta — within noise floor, no monotonic leak.

### Dry-Run Isolation
business_writes=0, provider_serving_calls=0 across all 10 windows, including the dedicated dry-run isolation window U6. Complete isolation maintained throughout the soak.

---

## Cumulative Program Record

| Metric | P1.8–P1.21 | P1.22 | P1.8–P1.22 |
|---|---|---|---|
| Selected | 34,836 | 10,537 | **45,373** |
| Violations | 0 | 0 | **0** |
| Max rollout reached | 75% | 75% | 75% |

---

## Test Evidence

| Suite | Collected | Passed | Failed | Skipped |
|---|---|---|---|---|
| P1.22 targeted | 247 | 247 | 0 | 0 |
| Cross-phase P1.x | 3,003 | 3,003 | 0 | 0 |
| Fundamental suite | 4,556 | 4,541 | 0 | 15 |
| Full backend suite | 6,387 | 6,372 | 0 | 15 |
| Frontend (vitest) | 688 | 688 | 0 | 0 |

Secret scan: clean (no real tokens, JWTs, or production secrets).

---

## Decision

| Decision | Value |
|---|---|
| ready_for_100pct_shadow_decision | **false** |
| 100% authorized | false |
| 100% applied | false |
| Rollback required | false |
| Rollback applied | false |
| Continue 75% shadow | **true** |

---

## Next Phase

**P1.23:** Conduct dedicated deployed runtime probe to resolve Gate C. If Gate C = PASS in P1.23, re-evaluate 100% shadow promotion readiness. All other 12 gates remain PASS from P1.22 evidence.

---

**Evidence SHA:** TBD_evidence_sha
