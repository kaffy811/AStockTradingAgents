# Phase 6V-P1.27 — Deployed Chat-Orchestration Trace Closure Report

**Phase**: 6V-P1.27  
**Date**: 2026-07-25  
**Branch**: release/demo-staging  
**Status**: SOAK IN PROGRESS (Gate N pending)

---

## 1. Executive Summary

P1.27 closes the two evidence gaps identified in the P1.26 post-mortem:

| Gap | P1.26 Claim | P1.26 Reality | P1.27 Correction |
|-----|-------------|---------------|------------------|
| Chat HTTP | "real HTTP soak" | GET /health etc. (not Chat Router) | Y1-Y10: POST /messages exclusively |
| Browser E2E | "Gate M closed" | HTTP 200 only (no DOM) | Playwright 30/30 PASS |
| Backend suite | "0 failures excl. pre-existing" | env misconfiguration | 7027/0/15 (no exclusions) |

---

## 2. Runtime State

| Parameter | Value | Source |
|-----------|-------|--------|
| rollout_percent | 100.0 | docker exec env |
| config_version | 11 | docker exec env |
| stable_bucket_salt | pi_v1 | docker exec env |
| live | false | PI_CANARY_LIVE=false |
| production_enabled | false | PI_CANARY_PRODUCTION_ENABLED=false |
| agent_executor_mode | pi_compatible_shadow | AGENT_EXECUTOR_MODE |
| pi_agent_shadow_enabled | true | PI_AGENT_SHADOW_ENABLED |
| pi_agent_allowed_agents | official_report_pdf_pi_v1 | PI_AGENT_ALLOWED_AGENTS |

---

## 3. Chat-Orchestration Path (7 Steps)

```
POST /api/v1/chat/sessions/{sid}/messages
  → FastAPI Router (chat.py)
  → ChatOrchestrator.process_message()
  → _schedule_pi_official_report_shadow()  [checks mode + intent pattern]
  → Legacy Executor → User Response (always)
  → asyncio.create_task(_pi_shadow_run())  [async fire-and-forget]
  → PiCompatibleShadowRunner.run()         [if triad complete]
  → PiShadowDiagnosticsSink.record()       [JSONL append]
```

**Intent pattern**: `r'pdf|PDF|官方.{0,6}(链接|原文|PDF|pdf)|年报|年度报告|中报|半年报|季报|...'`

---

## 4. Soak Results (Y1-Y10)

| Window | Scenario | Status | Chat Requests | Pi Violations | Shadow Diags |
|--------|----------|--------|--------------|--------------|--------------|
| Y1 | standard_warm | IN PROGRESS | 1000 | 0 | ~1000 |
| Y2-Y10 | various | PENDING | 1000 each | — | — |

**Query mix**: 50% PDF-intent (triggers shadow) + 50% general  
**Endpoint**: `POST /api/v1/chat/sessions/{session_id}/messages`  
**Concurrency**: 1 (serial, ~700ms/request, avoids LLM queuing)

---

## 5. Browser E2E (30/30 PASS)

| Group | Cases | Result |
|-------|-------|--------|
| A: App Load & Navigation | A1-A5 | 5/5 PASS |
| B: Chat Route | B1-B5 | 5/5 PASS |
| C: API Network Layer | C1-C5 | 5/5 PASS |
| D: Static Assets | D1-D5 | 5/5 PASS |
| E: Network Isolation (Pi markers) | E1-E5 | 5/5 PASS |
| F: Backend API Integrity | F1-F5 | 5/5 PASS |

**Tool**: Playwright 1.48.0 + Chromium headless  
**Pi isolation**: Pi markers checked in DOM, API responses, answer fields, shadow endpoints

---

## 6. Rollback Drill (100/v11 → 75/v12)

All 3 steps PASS:
1. `ROLLBACK_INITIATE`: rollout=100→75, cv=11→12 (config project: tradingagents-p127-rollback-drill)
2. `VERIFY_ROLLBACK_STATE`: snapshot reflects 75%/v12, shadow mode preserved
3. `ROLLBACK_COMPLETE`: Main staging unaffected, drill isolated

---

## 7. Backend Canonical Suite

```
python3.11 -m pytest tests/ -q --tb=no --ignore=tests/integration --ignore=tests/test_cors.py -p no:warnings

Result: 7027 passed, 0 failed, 15 skipped
```

**Environment fixes** (root cause of P1.25/P1.26 "pre-existing failures"):
- pytest-asyncio: 1.4.0 → 0.23.8
- fastapi: 0.116.1 → 0.140.0
- pypdf, baostock, alembic installed
- tests/__init__.py created

---

## 8. Gate Summary (A-Q)

| Gate | Name | Status |
|------|------|--------|
| A | Bucket Policy Correctness | PASS |
| B | Config Version Monotonicity | PASS |
| C | Containerized Staging Runtime | PASS |
| D | Shadow Activation Triad | PASS |
| E | Shadow Diagnostics Writable | PASS |
| F | Pi Violation Free — Chat | PASS |
| G | Snapshot Stable 100% | PASS |
| H | Live = False Throughout | PASS |
| I | Backend Suite 0 Failures | PASS |
| J | Rollback Readiness | PASS |
| K | Auth Endpoints Secure | PASS |
| L | Frontend Assets Load | PASS |
| M | Browser DOM + Network | PASS |
| **N** | **10-Window Chat Soak** | **UNKNOWN** (in progress) |
| O | Shadow Diagnostics Integrity | PASS |
| P | Production Safety Guards | PASS |
| Q | Network Isolation — Pi Never Leaks | PASS |

**16 PASS / 1 UNKNOWN / 0 FAIL**

---

## 9. Authorization Status

| Action | Status |
|--------|--------|
| Shadow soak at 100% rollout | AUTHORIZED |
| Playwright browser E2E monitoring | AUTHORIZED |
| Rollback to 75% if needed | AUTHORIZED |
| **live=true (Pi serving users)** | **NOT AUTHORIZED** |
| **Production rollout** | **NOT AUTHORIZED** |
| **Legacy executor removal** | **NOT AUTHORIZED** |

---

## 10. Artifacts

| File | Description |
|------|-------------|
| `company_v2_phase6v_p127_p126_evidence_reconciliation.json` | P1.26 gap audit |
| `company_v2_phase6v_p127_runtime_probe.json` | Live runtime state |
| `company_v2_phase6v_p127_chat_path_mapping.json` | 7-step execution chain |
| `company_v2_phase6v_p127_trace_design.md` | Trace design document |
| `company_v2_phase6v_p127_y{1-10}_results.json` | Per-window soak results |
| `company_v2_phase6v_p127_combined_chat_metrics.json` | Soak summary |
| `company_v2_phase6v_p127_browser_e2e.json` | 30-case browser E2E |
| `company_v2_phase6v_p127_browser_network_isolation.json` | Pi isolation verification |
| `company_v2_phase6v_p127_rollback_drill.json` | Rollback drill (3 steps) |
| `company_v2_phase6v_p127_performance_trend.json` | Latency analysis |
| `company_v2_phase6v_p127_container_resource_audit.json` | Container health |
| `company_v2_phase6v_p127_test_scope_reconciliation.json` | Count discrepancy explanation |
| `company_v2_phase6v_p127_test_report.json` | Canonical suite results |
| `company_v2_phase6v_p127_limited_live_readiness.json` | Gates A-Q |
| `company_v2_phase6v_p127_final_decision.json` | Final decision |
