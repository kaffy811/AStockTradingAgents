# Phase 6V-P1.21: 75% Shadow Promotion Report

**Date:** 2026-07-23
**Base SHA:** 7cbc4b57d420e6c43f062f8131544c2ef7dae9be
**Phase:** 6V-P1.21
**Status:** COMPLETE — All 12 gates PASS

---

## Phase Overview

Phase P1.21 promotes the Pi shadow rollout from 50% to 75% via
`staging_test_fixture_override` (config_version 7→8). This phase includes a
critical bucket stability fix: `stable_bucket_salt='pi_v1'` is now used for SHA256
hashing instead of `config_version`, ensuring cohort stability across config version
bumps.

---

## Promotion Details

| Field | Before (P1.20) | After (P1.21) |
|---|---|---|
| rollout_percent | 50 | 75 |
| config_version | 7 | 8 |
| stable_bucket_salt | pi_v1 | pi_v1 (unchanged) |
| Mechanism | — | staging_test_fixture_override |
| Live serving | false | false |
| Production | false | false |

**Bucket migration:** 50% cohort (5006) ⊆ 75% cohort (7539) out of 10000 test
identities. The promotion does not re-bucket existing 50% users.

---

## Key Metrics

| Metric | P1.21 (75%) | P1.20 (50%) | Delta |
|---|---|---|---|
| Total eligible | 14049 | 13769 | +280 |
| Total selected | 10537 | 6902 | +3635 |
| Selection rate | 74.99% | 50.13% | +24.86pp |
| tool p95 | 3262ms | 3253ms | +9ms (+0.28%) |
| Pi p95 | 4758ms | 4742ms | +16ms (+0.34%) |
| Pi p99 | 4955ms | 4936ms | +19ms |
| Pi max | 4992ms | 4987ms | +5ms |
| Pi >5s rate | 0.0% | 0.0% | — |
| Pi >6s count | 0 | 0 | — |
| Safety correctness | 1.0 | 1.0 | — |
| Zero-tolerance violations | 0 | 0 | — |
| Unique symbols | 100 | 100 | — |
| Query styles | 14 | 14 | — |
| Multi-turn count | 577 | 447 | +130 |

**Cumulative P1.8–P1.21:** 34836 selected, 0 violations.

---

## Window Summary (T1–T8)

| Window | Type | Eligible | Selected | Pi p95 (ms) | CPU p95 | FD Peak | Gate |
|---|---|---|---|---|---|---|---|
| T1 | standard_warm | 1748 | 1311 | 4748 | 33% | 436 | PASS |
| T2 | post_restart | 1731 | 1298 | 4763 | 39% | 441 | PASS |
| T3 | multi_turn_heavy | 1719 | 1290 | 4771 | 42% | 448 | PASS |
| T4 | gap_stale_revised | 1762 | 1322 | 4751 | 34% | 439 | PASS |
| T5 | concurrency_burst | 1784 | 1338 | 4778 | 51% | 473 | PASS |
| T6 | dry_run_parallel | 1768 | 1326 | 4767 | 44% | 461 | PASS |
| T7 | long_running | 1791 | 1343 | 4752 | 36% | 444 | PASS |
| T8 | final_stable | 1746 | 1309 | 4741 | 31% | 432 | PASS |

**Pi p95 trend:** 4748→4763→4771→4751→4778(burst)→4767→4752→4741
- All windows: warning triggered (>4700ms), review NOT triggered (<4800ms)
- T5 burst peak 4778ms — highest, still below 4800ms review threshold
- T8 4741ms — full recovery, near T1 baseline

**Resource recovery:** Memory 389MB (T8) = 389MB (T1). FD 432 (T8) ≈ 436 (T1).
T5 burst (FD=473) attributed to 75% concurrency; confirms recovery by T8.

---

## Gate Results (12/12 PASS)

| Gate | Result |
|---|---|
| A: Repository Integrity | PASS |
| B: Configuration Integrity | PASS |
| C: Bucket Migration | PASS |
| D: Runtime Verification | PASS |
| E: Safety | PASS |
| F: Reliability | PASS |
| G: Performance | PASS |
| H: Resources | PASS |
| I: Data Regression | PASS |
| J: Browser Isolation | PASS |
| K: Dry-Run Isolation | PASS |
| L: Test & Rollback Evidence | PASS |

---

## Non-Blocking Risks

- **Pi p95 >4700ms all windows:** Consistent warning threshold breach across all 8
  windows. Attributed to LLM_latency (primary) and queue_wait (T5 burst only). Not
  monotonically increasing; T8 recovers. No review triggered. No rollback triggered.

---

## Next Steps

1. **Continue 75% shadow** for additional soak (P1.22 or extended P1.21)
2. **Monitor T5-class burst windows** at 75% load; CPU 51% is elevated but within
   safe operating range (no pool exhaustion, no errors)
3. **100% promotion** requires separate owner authorization — not yet authorized
4. **Live serving** remains false — no change authorized
5. **Production** remains false — no change authorized

---

## Safety Invariants (Confirmed Throughout)

- `live = false`
- `production_enabled = false`
- `recommended_for_live_serving = false`
- `recommended_for_production = false`
- `provider_calls_serving = 0`
- `canary_mode = shadow`
- `stable_bucket_salt = "pi_v1"` (unchanged from P1.20)
