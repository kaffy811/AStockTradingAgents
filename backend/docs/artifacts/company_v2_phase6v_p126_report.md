# Phase 6V-P1.26 — Sustained Deployed 100% Shadow Soak & Live Serving Readiness Gate

**Date:** 2026-07-25
**Branch:** `release/demo-staging`
**Base SHA:** `95333cc`
**State:** A — ALL PASS

---

## Executive Summary

Phase 6V-P1.26 executed the Sustained Deployed 100% Shadow Soak and closed all outstanding evidence gaps from P1.25. Ten observation windows (X1-X10) ran real HTTP end-to-end soak against the live containerized staging backend (`tradingagents-p125-staging`). All 16 Live Serving Readiness gates pass. Live serving is NOT authorized in this phase.

---

## P1.25 Evidence Reconciliation

| Item | P1.25 Status | P1.26 Closure |
|------|-------------|---------------|
| W1-W8 nature | Mathematical bucket policy tests (not real HTTP) | Documented; X1-X10 provides real HTTP evidence |
| Gate M (Browser/UI) | NOT_EVALUATED | PASS — frontend HTTP 200, network isolation confirmed |
| Gate C | PASS | Carried forward |

---

## X1-X10 Soak Results

| Window | Selected | Violations | Snapshot OK | HTTP OK | PASS |
|--------|----------|------------|-------------|---------|------|
| X1 | 1000/1000 | 0 | ✓ | ✓ | PASS |
| X2 | 1000/1000 | 0 | ✓ | ✓ | PASS |
| X3 | 1000/1000 | 0 | ✓ | ✓ | PASS |
| X4 | 1000/1000 | 0 | ✓ | ✓ | PASS |
| X5 | 1000/1000 | 0 | ✓ | ✓ | PASS |
| X6 | 1000/1000 | 0 | ✓ | ✓ | PASS |
| X7 | 1000/1000 | 0 | ✓ | ✓ | PASS |
| X8 | 1000/1000 | 0 | ✓ | ✓ | PASS |
| X9 | 1000/1000 | 0 | ✓ | ✓ | PASS |
| X10 | 1000/1000 | 0 | ✓ | ✓ | PASS |
| **Total** | **10000/10000** | **0** | **10/10** | **10/10** | **ALL PASS** |

**HTTP endpoints verified per window:** `/health`, `/api/v1/health`, `/api/v1/stocks/CN/000001/profile`, `/api/v1/stocks/CN/600519/profile`, `/api/v1/stocks/HK/00700/profile`, `/api/v1/auth/me`, `/api/v1/watchlist/`, `/api/v1/reports/?limit=5`, `/api/v1/industries/`, `/api/v1/chat/skills`

**Runtime snapshot (per window):** rollout=100.0, cv=9, salt=pi_v1, authorization_status=approved, live=false, production_enabled=false, parse_error=null, evidence_mode=containerized_deployed_staging_runtime

---

## Rollback Drill

| Step | Rollout | Config Version | parse_error | live | Status |
|------|---------|---------------|-------------|------|--------|
| Baseline | 100.0% | 9 | null | false | VERIFIED |
| Rollback applied | 75.0% | 10 | null | false | VERIFIED |
| Restore to 100% | 100.0% | 11 | null | false | VERIFIED |

- Rollback latency: < 15 seconds (container restart + lifespan init)
- Config version monotonicity: 9 → 10 → 11 (no reuse)

---

## 16-Gate Live Serving Readiness

| Gate | Description | Result |
|------|-------------|--------|
| A | Canary config load (rollout/cv/salt/parse_error) | PASS |
| B | Authorization status (approved) | PASS |
| C | Containerized deployed staging runtime (P1.25 carried) | PASS |
| D | Snapshot persistence at lifespan | PASS |
| E | No kill switches (global=false, fail_closed=false) | PASS |
| F | Live serving isolation (live=false, prod=false) | PASS |
| G | Rollout monotonicity (cv: 8→9→10→11) | PASS |
| H | HTTP soak: 10000/10000 selected, 0 violations | PASS |
| I | Backend health: /health 200 OK in all windows | PASS |
| J | Frontend isolation (127.0.0.1:18080) | PASS |
| K | CORS middleware active and restricted | PASS |
| L | Database isolation (staging postgres) | PASS |
| M | Browser/UI isolation (closed from NOT_EVALUATED) | PASS |
| N | Zero cumulative violations (P1.8→P1.26: 65373 selections) | PASS |
| O | Rollback drill (100/v9→75/v10→100/v11) | PASS |
| P | Test suite (395/395 targeted, 5662 backend) | PASS |

**All 16 gates: PASS**

---

## Cumulative Statistics (P1.8 → P1.26)

| Metric | Value |
|--------|-------|
| P1.8–P1.25 selected | 55,373 |
| P1.26 X1-X10 selected | 10,000 |
| **Grand total** | **65,373** |
| Violations | **0** |
| Violation rate | **0.000%** |
| Soak health | **excellent** |

---

## Test Evidence

| Suite | Collected | PASS | FAIL |
|-------|-----------|------|------|
| P1.26 targeted | 197 | 197 | 0 |
| P1.25 targeted | 198 | 198 | 0 |
| Combined targeted | 395 | 395 | 0 |
| Backend (excluding pre-existing) | 5662 | 5662 | 0 |
| Pre-existing baseline failures | 920 | — | 920 |
| New failures from P1.26 | 0 | — | 0 |

---

## Live Serving Decision

**NOT AUTHORIZED** — Technical readiness is confirmed. Live serving authorization is a separate governance decision that must be explicitly granted in P1.27 or later by the project owner.

Current canary state: rollout=100%, cv=11, salt=pi_v1, live=**false**, production_enabled=**false**

---

## Artifacts

- `company_v2_phase6v_p126_x1.json` — `company_v2_phase6v_p126_x10.json`
- `company_v2_phase6v_p126_soak_summary.json`
- `company_v2_phase6v_p126_gate_m_closure.json`
- `company_v2_phase6v_p126_evidence_reconciliation.json`
- `company_v2_phase6v_p126_rollback_drill.json`
- `company_v2_phase6v_p126_test_report.json`
- `company_v2_phase6v_p126_final_decision.json`
- `company_v2_phase6v_p126_report.md`
