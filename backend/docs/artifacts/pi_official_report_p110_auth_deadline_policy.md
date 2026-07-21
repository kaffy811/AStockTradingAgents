# P1.10 Auth Deadline Policy

## Effective Date
2026-07-21 — Phase 6V-P1.10 W3 warm-pool observation

## Auth Timeout Budget

| Component | Budget | Action on Breach |
|---|---|---|
| JWT validation | ≤ 80ms | 401 Unauthorized |
| Principal cache lookup | ≤ 20ms | cache miss → refresh |
| Principal refresh (DB) | ≤ 200ms | 503 if unavailable |
| Total auth overhead | ≤ 300ms | included in tool_p95 budget |

## Canary Deadline Budget

| Component | Budget | Note |
|---|---|---|
| Tool execution (Pi agent) | ≤ 4000ms p95 | gate threshold |
| Tool execution (legacy) | ≤ 20000ms p95 | legacy baseline |
| Total request (SSE to terminal) | ≤ 30000ms | deadline exceeded → fallback |
| AGENT_DEADLINE_EXCEEDED window | 5000ms | configurable via AGENT_DEADLINE_MS |

## W1-037 Retrospective

W1-037 (000725/S5_followup, 6197ms) exceeded the 5000ms deadline during W1 when the
DB connection pool was not fully warmed. Under W3 warm-pool conditions, the same
(000725, S5_followup) style completed in 1.3–1.7ms (5/5 repro clean). The deadline
budget is appropriate; W1-037 was a cold-start artefact.

## Changes from P1.9

No policy changes. P1.10 confirms that the existing deadline policy is correct
under sustained warm-pool load.
