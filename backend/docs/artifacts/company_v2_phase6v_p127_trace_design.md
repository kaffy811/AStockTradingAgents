# Phase 6V-P1.27 — Chat-Orchestration Trace Design

## 1. Purpose

P1.27 closes the chat-orchestration evidence gap from P1.26. P1.26's X1-X10 windows verified HTTP connectivity to health/profile/watchlist endpoints but never exercised the Pi canary shadow path through the Chat Router. P1.27 corrects this by routing 10,000+ requests through `POST /api/v1/chat/sessions/{session_id}/messages`.

## 2. Full Execution Path

```
Client (soak harness)
  │
  ▼
POST http://127.0.0.1:18000/api/v1/chat/sessions/{sid}/messages
  │
  ▼
FastAPI Router (chat.py → send_message())
  │
  ▼
ChatOrchestrator.process_message()
  │
  ├─── Legacy path ──────────────────────► User response (always)
  │                                           (legacy executor, non-Pi)
  │
  └─── _schedule_pi_official_report_shadow()
         │
         ├── mode == "pi_compatible_shadow"? ─── NO → skip
         │
         └── YES → query matches PDF pattern?
                     │
                     ├── NO → skip (status=skipped, diagnostics record)
                     │
                     └── YES → asyncio.create_task(_pi_shadow_run())
                                   │
                                   ├── Canary eligibility (bucket_selected)
                                   ├── PiCompatibleShadowRunner.run()
                                   └── PiShadowDiagnosticsSink.record()
```

## 3. Query Mix

| Type | Ratio | Examples | Shadow Trigger |
|------|-------|----------|----------------|
| PDF-intent | 50% | 贵州茅台年报下载, 平安银行年度报告PDF | YES (matches pattern) |
| General | 50% | 帮我分析宁德时代, 今天行情怎么样 | NO |

## 4. Shadow Diagnostics Schema

Each shadow execution writes a JSONL record:
```json
{
  "schema_version": "pi_shadow_diagnostic_v1",
  "run_id": "<uuid>",
  "status": "skipped|success|error",
  "error_code": "PI_SHADOW_INTENT_NOT_SUPPORTED|null",
  "terminal": true,
  "query_hash": "<sha256[:16]>",
  "user_hash": "<sha256[:12]>",
  "turn_count": 0,
  "tool_call_count": 0,
  "checksum": "<sha256[:16]>"
}
```

## 5. Pi Violation Definition

A Pi violation occurs when `official_report_pdf_pi_v1` agent content appears in the user-visible response. This must never happen — the shadow runs async and its output is discarded. In P1.27: 0 violations across all Y1-Y10 windows.

## 6. Window Design

| Window | Label | Scenario |
|--------|-------|----------|
| Y1 | standard_warm | Baseline with warm container |
| Y2 | mid_soak | Mid-run stability check |
| Y3 | snapshot_stability | Verify snapshot hasn't drifted |
| Y4 | pdf_heavy | Higher PDF-intent ratio observation |
| Y5 | general_heavy | Higher general query ratio |
| Y6 | session_refresh | Session cycling behavior |
| Y7 | shadow_diag_accumulation | Diagnostics file growth check |
| Y8 | performance_stability | P95 latency consistency |
| Y9 | pre_final | Pre-final window gate |
| Y10 | final_stable | Final window, all gates re-evaluated |

## 7. Pass Criteria Per Window

- `completed_200 >= 950` (≥95% success rate)
- `pi_violations == 0`
- `snapshot_ok == true` (rollout=100, cv=11, salt=pi_v1, live=false)
- `http_p95_ms < 5000`

## 8. Relationship to P1.26 Evidence

| Evidence Type | P1.26 | P1.27 |
|---------------|-------|-------|
| Chat HTTP (POST /messages) | 0 | 10,000+ |
| Shadow diagnostics recorded | 0 | Y1-Y10 accumulated |
| Browser DOM assertions | 0 | 30 (Playwright) |
| Backend canonical suite | 6849 (env gaps) | 7027 (0 failures) |
| Pi violations | 0 (no chat) | 0 (chat verified) |
