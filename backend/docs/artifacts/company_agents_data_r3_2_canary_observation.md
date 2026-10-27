# Phase 6W-R3.2 — Canary Observation

Date: 2026-08-21  
Release baseline: `3c30787`  
Traffic decision: `HOLD_1_PERCENT`

## Observation status

The planned 30-request observation was not started because the earlier mandatory G1–G14 regression stop condition failed at G7.

## Completed populations

| Population | Count | RAG timeout | Completed | Partial | Numeric valid |
|---|---:|---:|---:|---:|---:|
| Direct fresh indexed retrieval | 10 | 0 | 10 retrieval successes | 0 | N/A |
| Full fresh API E2E | 10 | 0 | 1 | 9 | 1 |

## Retrieval evidence

- Direct retrieval P50: 485.9 ms
- Direct retrieval max: 5101.9 ms (first request)
- Full E2E retrieval range: 661–1295 ms
- Timeout layer: none for all 20 completed retrieval operations
- Actual report-chat path: `indexed_db_lexical`

## Correctness evidence

- Requested report: 600519.SH, 2024 annual, report_id=17
- Wrong-year selections: 0
- Full E2E numeric-valid rate: 10%
- Safe partial-success rate: 90%
- User-visible unsafe success: 0

## Incident classification

- Previous fresh-RAG timeout P1: not reproduced after restart/build (0 timeouts).
- G7 numeric correctness gate: failed because 9/10 cold answers contained unsupported numeric claims and were correctly degraded.
- No P0 security, DB, report-selection, or secret incident observed.

## Expansion decision

`HOLD_1_PERCENT`

Rationale: the retrieval timeout condition is closed in the measured sample, but R3.2 requires G1–G14 to pass before the 30-request observation and before any dependency commit. G7 did not pass. Per phase rules, testing stopped without changing validator behavior, timeout thresholds, retrieval logic, or traffic.

