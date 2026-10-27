# Phase 6W-R3.2C.1 — Q2 Runtime Evidence Closure

Date: 2026-08-24  
Baseline before commit: `3c30787db82bc2a6de14042bbda2895f64f1b623`  
Branch: `release/demo-staging`  
Traffic: `HOLD_1_PERCENT`

## Workspace protection

The staging area was empty. Existing Docker, dependency, embedding-provider, lockfile and `backend/app/main.py` warmup changes remained untouched and unstaged. Historical untracked artifacts were preserved. `git diff --check` passed.

## Previous interruption diagnosis

The prior Q2 trace stopped after S5 without a Python exception or termination record. At inspection time backend, Redis and DB were healthy, disk had about 491 GiB free, and the backend container had remained up. Because the request ran through a one-shot in-process ASGI diagnostic runner, the persistent uvicorn access log did not receive its request ID. Direct evidence therefore locates the previous interruption at `S6_LLM_IN_FLIGHT`, outside retrieval/DB/compaction/artifact-disk layers; the exact external termination source remains unproven.

The temporary diagnostic runner—not production code—was strengthened with atomic replace writes, a `current_stage` marker, pre-LLM persistence, and SIGTERM/SIGINT termination capture.

## Controlled Q2 invocation

Exactly one invocation was executed; no retry occurred.

| Field | Result |
|---|---|
| Question | `2024年贵州茅台净利润增长情况如何？` |
| Request ID | `a3c8fe8a` |
| Session | `r32c1-q2-20260824` |
| force_refresh | true |
| Selected report | report_id 17 / 2024 annual / explicit_report_id |
| Selection cache | miss |
| Selection latency | 5988 ms |
| Retrieval path | indexed fast path / indexed DB lexical |
| Retrieval latency | 1642.4 ms |
| Raw chunk IDs (artifact only) | 3663, 3664, 3665, 3666, 3670, 3671 |
| LLM-visible evidence | E1, E2, E3, E4, E5, E6 |
| Prompt raw chunk ID/table name | absent |
| Citations before resolution | E5 net-profit claim; E3 EPS claim |
| Resolved citations | E5 -> 3670; E3 -> 3665 |
| Citation validation | valid; 2 resolved; no invalid/duplicate/invalid-claim IDs |
| CITATION_METADATA_LEAK | false |
| Numeric validation | valid=true / reason=ok / unsupported=0 |
| Final status | completed / partial=false / errors=[] |
| Final answer raw chunk ID | absent |
| Post-request backend/DB/Redis health | ok |

All S0-S8 stages were atomically persisted. The final answer discusses attributable net profit, EPS and report limitations without E-labels, raw chunk IDs, table names or retrieval implementation details.

## Three-query gate matrix

| Query | Completed | Prompt raw ID absent | Citation valid | Leak false | Numeric valid | Answer raw ID absent |
|---|---:|---:|---:|---:|---:|---:|
| Q1 revenue (`d5ec31f6`) | Yes | Yes | Yes | Yes | Yes | Yes |
| Q2 net profit (`a3c8fe8a`) | Yes | Yes | Yes | Yes | Yes | Yes |
| Q4 cash flow (`4760e83a`) | Yes | Yes | Yes | Yes | Yes | Yes |

## Regression

Command:

```text
UV_CACHE_DIR=/private/tmp/tradingagents-uv-cache uv run pytest tests/test_phase6w_r2_6_synthesis_optimization.py tests/fundamental/test_phase6u_report_chain_alignment.py tests/fundamental/test_phase6i_review_source_chunks_strict.py tests/fundamental/test_phase6h_ai_source_chunks.py tests/fundamental/test_phase6j_report_chat_copilot.py tests/test_phase6w_r1_2_numeric_pipeline.py -q
```

Result: 127 passed, 0 failed, 0 skipped in 1.52 seconds; one pre-existing passlib `crypt` deprecation warning.

## Commit and release gate

The Q1/Q2/Q4 runtime matrix, tests and diff checks pass. Only the approved D3 code, tests and artifacts are eligible for the isolated local commit. `backend/app/main.py` remains `UNRESOLVED — EXCLUDED FROM THIS PHASE`.

No push, deployment or traffic expansion is authorized. Final traffic remains `HOLD_1_PERCENT`.

