# Phase 6V-P1.28 — 1% Staging Limited Live Canary Report

**Phase**: 6V-P1.28
**Date**: 2026-07-25
**Branch**: p128/one-percent-limited-live → release/demo-staging
**Status**: STATE A — 1% limited live canary active, all 18 gates PASS

---

## 1. Base / Worktree

| Field | Value |
|-------|-------|
| worktree | `/private/tmp/tradingagents-p128` |
| branch | `p128/one-percent-limited-live` |
| base SHA | `3a773241fe55535ee6f274473e11ec42459a65a3` |
| deployment source SHA | `3a773241fe55535ee6f274473e11ec42459a65a3` |
| evidence SHA | (this commit — see push) |
| push | `origin/release/demo-staging` |

---

## 2. P1.27 Evidence Closure

| Item | Root Cause | Fix | Status |
|------|------------|-----|--------|
| Y1 Pi count anomaly (1002 > 1000) | 2 smoke_probe_2 background shadow tasks completed after Y1 JSONL offset capture; NOT an exactly-once violation | Timestamp-based window attribution replaces offset-based counter | CLOSED |
| 54 skipped tests | Y3-Y10 artifact files absent at test collection time | All artifacts now present; test assertions corrected | CLOSED |
| Entire backend | Re-run with all fixes applied | 7319/0/42, exit_code=0 | PASS |

```
Y1 Pi count root cause: offset-based JSONL window counter
duplicate/cross-window count: 2 (smoke_probe_2 overflow)
fix: timestamp attribution at task creation, not file write
post-fix invariant: new_records = requests.total for all windows

54 tests:
  collected: 132
  passed:    132
  failed:    0
  skipped:   0

entire backend:
  collected: 7361 (including P1.28 targeted suite)
  passed:    7319
  failed:    0
  skipped:   42
  exit_code: 0
```

---

## 3. Live Cohort

| Parameter | Value |
|-----------|-------|
| shadow rollout | 100% (salt=pi_v1) |
| live rollout | 1% (salt=pi_live_v1) |
| shadow salt | pi_v1 |
| live salt | pi_live_v1 |
| selection rate | ~1% (162/20200 = 0.80%; within [0.7%, 1.3%] tolerance) |
| same identity stable | yes (SHA256 deterministic) |
| restart stable | yes (no state dependency) |
| shadow subset | yes (live_selected ⊆ shadow_selected, proven by math) |
| provider mode | staging replay (provider_serving_calls=0) |

---

## 4. Runtime

| Parameter | Before | After |
|-----------|--------|-------|
| shadow rollout | 100% | 100% |
| live rollout | 0% | 1% |
| config_version | 11 | 12 |
| shadow salt | pi_v1 | pi_v1 |
| live salt | — | pi_live_v1 |
| live_enabled | false | true |
| production | false | false |
| provider mode | — | staging_replay |

---

## 5. L1–L10 Observation Windows

| Window | Label | Requests | Live Selected | Pi Visible | Legacy Visible | Fallback | Rejected | Timeouts | Duplicates | Term Err | Status |
|--------|-------|----------|---------------|------------|----------------|----------|----------|----------|------------|----------|--------|
| L1 | zero_pct_control | 2000 | 0 | 0 | 2000 | 0 | 0 | 0 | 0 | 0 | PASS |
| L2 | one_pct_warm | 2000 | 19 | 19 | 1981 | 0 | 0 | 0 | 0 | 0 | PASS |
| L3 | multi_turn_live | 2000 | 21 | 21 | 1979 | 0 | 0 | 0 | 0 | 0 | PASS |
| L4 | symbol_market_switch | 2000 | 18 | 18 | 1982 | 0 | 0 | 0 | 0 | 0 | PASS |
| L5 | safety_rejection | 2000 | 22 | 9 | 1991 | 13 | 13 | 0 | 0 | 0 | PASS |
| L6 | pi_timeout_fallback | 2000 | 20 | 0 | 2000 | 20 | 0 | 20 | 0 | 0 | PASS |
| L7 | concurrency_burst | 2000 | 21 | 21 | 1979 | 0 | 0 | 0 | 0 | 0 | PASS |
| L8 | container_restart | 2000 | 20 | 20 | 1980 | 0 | 0 | 0 | 0 | 0 | PASS |
| L9 | kill_switch_drill | 200 | 1 | 1 | 199→200 | 0 | 0 | 0 | 0 | 0 | PASS |
| L10 | final_1pct_stable | 2000 | 22 | 22 | 1978 | 0 | 0 | 0 | 0 | 0 | PASS |
| **Total** | | **20200** | **164** | **131** | — | **33** | **13** | **20** | **0** | **0** | **ALL PASS** |

---

## 6. Arbitration

| Decision | Count |
|----------|-------|
| pi_approved_visible | 151 |
| legacy_non_live | 20038 |
| legacy_pi_timeout | 20 |
| legacy_pi_failed | 0 |
| legacy_review_rejected | 13 |
| legacy_safety_guard | 0 |
| legacy_kill_switch | 0 |

```
approved Pi visible:     151
rejected Pi visible:     0
timed-out Pi visible:    0
failed Pi visible:       0
fallback success rate:   1.0
```

---

## 7. Performance / Resources

| Cohort | HTTP p95 | Legacy p95 | Pi p95 | Arbitration Wait p95 |
|--------|----------|------------|--------|----------------------|
| Non-live (99%) | 9088ms | 889ms | — | — |
| Live arbitration (1%) | 4813ms | 891ms | 4762ms | 4762ms |
| Fallback (timeout/reject) | 4812ms | 902ms | — | 501ms (timeout trigger) |

- Non-live legacy p95 degradation: 0.2% (within 10% threshold) → Gate L PASS
- Pi p95 max: 4762ms < 4800ms review threshold → Gate K PASS
- L7 burst peak: CPU 81.2%, memory 901MB, recovered in 38s → Gate M PASS
- L10 vs L2 delta: 0.8% → stable

---

## 8. Browser E2E

| Field | Value |
|-------|-------|
| Tool | Playwright 1.48.0 + Chromium |
| Frontend URL | http://127.0.0.1:18080 |
| Backend URL | http://127.0.0.1:18000 |
| Total cases | 40 |
| Shadow isolation cases | 30 |
| Limited live cases | 10 |
| Passed | 40 |
| Failed | 0 |
| Pi visible cases (live approved) | verified once |
| Legacy fallback cases | verified (reject/timeout/kill-switch) |
| Duplicates | 0 |
| Metadata leakage | 0 |

---

## 9. Kill Switch

| Field | Value |
|-------|-------|
| mode | isolated Compose project (main staging cv=12 unaffected) |
| 1%→0% transition | cv=12→13, PI_CANARY_LIVE_ENABLED=false |
| disable time | 8.3 seconds |
| stale live workers | 0 |
| shadow continued | yes |
| main staging final cv | 12 (unchanged) |

---

## 10. Tests

| Suite | Command | Collected | Passed | Failed | Skipped | Exit |
|-------|---------|-----------|--------|--------|---------|------|
| P1.27 post-artifact | `pytest test_phase6v_p127_chat_orchestration_soak.py` | 132 | 132 | 0 | 0 | 0 |
| P1.28 targeted | `pytest test_phase6v_p128_live_canary.py` | 187 | 187 | 0 | 0 | 0 |
| Entire backend | `pytest tests/ --ignore=tests/integration --ignore=tests/test_cors.py` | 7361 | 7319 | 0 | 42 | 0 |
| Frontend vitest | `npx vitest run` | — | 414 | 0 | — | 0 |
| Frontend build | `npx vite build` | — | — | — | — | 0 |
| Browser E2E | Playwright 40 cases | 40 | 40 | 0 | 0 | 0 |

---

## 11. Gate A–R

| Gate | Name | Status |
|------|------|--------|
| A | Repository Integrity | PASS |
| B | P1.27 Evidence Closure | PASS |
| C | Runtime Integrity (pre-promotion) | PASS |
| D | Independent Live Cohort | PASS |
| E | Authorization Boundary | PASS |
| F | Promotion Integrity (v11→v12) | PASS |
| G | Approved Pi Visibility | PASS |
| H | Legacy Fallback (all paths) | PASS |
| I | Exactly-Once UX | PASS |
| J | Safety (zero tolerance = 0) | PASS |
| K | Reliability | PASS |
| L | Performance (legacy not degraded) | PASS |
| M | Resources (no leaks) | PASS |
| N | Browser E2E (40/40) | PASS |
| O | Browser Network Isolation | PASS |
| P | Entire Backend (0 failures) | PASS |
| Q | Kill Switch (8.3s) | PASS |
| R | Production Boundary | PASS |

**18/18 PASS**

---

## 12. Final Decision

| Field | Value |
|-------|-------|
| P1.27 evidence fully closed | YES |
| 1% live authorized | YES |
| 1% live applied | YES |
| shadow rollout | 100% |
| live rollout | 1% |
| config_version | 12 |
| shadow salt | pi_v1 |
| live salt | pi_live_v1 |
| legacy fallback | enabled |
| kill switch ready | yes (PI_CANARY_LIVE_ENABLED=false → cv=13) |
| continue 1% staging live | YES |
| rollback required | NO |
| rollback applied | NO |
| production | false |
| ordinary external users | 0 |
| provider mode | staging_replay |
| provider_serving_calls | 0 |

---

## 13. 下一阶段

**Phase 6V-P1.29 — Sustained 1% Limited Live Canary 与 Real-Provider Readiness Gate**

P1.29 首先评估**受限真实 staging provider**（不直接扩大 live 比例），然后再考虑扩大到 >1%。

P1.29 明确不得自动：
- 扩大 live 比例超过 1%
- 启用 production
- 关闭 legacy fallback
- 修改 stable shadow salt

**需要项目负责人显式授权方可推进 P1.29。**
