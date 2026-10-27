# Phase 6W-R3.3I.2.1 — Structured Operand Runtime Closure

## Final decision

`STRUCTURED_FACT_RUNTIME_NOT_READY`

Traffic: `HOLD_1_PERCENT`

Two cold-synthesis requests completed the full S0–S8 chain with emitted net margin, valid citations, valid numeric validation, no citation metadata leak, and final status `completed`. However, Q2 was still executing in the backend when Q3 began, so the fixed plan was not strictly serial at backend completion boundaries. No request was retried and no fourth request was issued. Because the prescribed execution protocol was not fully satisfied, no commit was created.

## 1. Workspace and boundary

- HEAD: `b055da8495c54bb37625f0b0e0f94b4d4a627de2`
- Branch: `release/demo-staging`
- Entry and final `git diff --check`: clean.
- Historical tracked dirty files remained unchanged: `backend/Dockerfile`, `backend/app/main.py`, `backend/app/services/report_embedding_provider.py`, `backend/pyproject.toml`, `backend/uv.lock`.
- R3.3I/R3.3I.2 implementation remained only in `/private/tmp/tradingagents-r33e1.IfXFWV` and in the isolated candidate image. No application code was modified in this closure turn.
- This turn added only the required runtime closure MD/JSON artifacts.

## 2. Candidate identity and isolation

- Image: `tradingagents-backend:rc-r33i2-1-runtime`
- Image digest / ID: `sha256:d01562d22cbc02d4cbad5277d087b793251125cf470e0e1500bb947c8d473dd1`
- OCI revision: `r33i2-1-739e57cd`
- OCI source: `tradingagents-r33e1.IfXFWV-r33i2-1`
- Container ID: `4da938a5374d593afc0ce162061d304f387c2a2a418fc11e0f521f4bca94ed37`
- Mounts: `[]`; no source bind mount.
- Network: `tradingagents-r33i-run-net`.
- PostgreSQL: isolated `r33i-run-postgres`, dedicated volume, database `tradingagents_r33i_run`.
- Redis: isolated `r33i-run-redis`, dedicated volume/database namespace.
- Health probe: DB and Redis both `ok`.
- Candidate file hashes matched the built image for the supplement, derived-fact service, and copilot integration.
- Production and staging containers/images/databases/Redis were not modified.

The prior runtime container had R3.3I.2 files copied into it but its base image still identified R3.3I. A new isolated image was therefore built from the candidate tree and only the isolated backend was replaced. The prior isolated backend was retained stopped as `r33i-run-backend-r33i2-old` for recoverability.

## 3. Fixed requests and execution protocol

All three predefined questions were sent exactly once with unique sessions, `force_refresh=true`, `report_id=1`, `years=[2024]`, and `use_memory=false`. Response files were persisted under `/private/tmp/r33i2_1-q1.json` through `q3.json`. No retry was issued.

Start times were separated by more than 15 seconds:

- Q1: `00:27:39.799576Z`
- Q2: `00:28:24.147271Z` — 44.35s after Q1 start and 26.05s after Q1 completion.
- Q3: `00:29:13.919678Z` — 49.77s after Q2 start.

Protocol deviation: Q2 completed at `00:29:21.222987Z`, so Q3 began 7.30s before Q2 completed. The client command ended before the backend trace finalized Q2. This makes the backend executions overlap and fails the strict serial-execution requirement. The deviation was discovered from persisted trace timestamps after all three predefined requests had already been sent; no corrective fourth request was allowed or issued.

All requests bypassed final-answer cache. Q1 did show a structured-field extraction cache hit, which is not the final-answer cache and did not bypass S6: Q1 S6 performed a fresh 17.9s LLM call. Q2 and Q3 likewise reached S6 with fresh raw output.

## 4. Runtime matrix

| Item | Q1 `8e074a05` | Q2 `1e906783` | Q3 `ba464706` |
|---|---|---|---|
| report / period | report 1, 2024 annual, `2024-12-31` | same | same |
| stages | S0–S8 complete | S0–S8 complete | S0–S8 persisted; S7 failed |
| revenue provenance | `E7`, 2024, CNY; 170,899,152,276.34 | `E7`, 2024, CNY; same | `E1`, 2024, CNY; same |
| net-profit provenance | `E7`, 2024, CNY; 86,228,146,421.62 | `E7`, 2024, CNY; same | `E1`, 2024, CNY; same |
| supplement | parent net profit; complete same-report evidence | same | same |
| derived fact | `C1 net_margin=50.46%` | same | same |
| S6 raw LLM | completed, raw output present, 17.9s | completed, raw output present, 56.9s | completed, raw output present, 17.1s |
| citation validation | valid; resolved `C1` | valid; resolved `C1` | invalid evidence reference; claims `E1`, `C1` rejected |
| numeric validation | valid, reason `ok` | valid, reason `ok` | invalid; unsupported `100` twice |
| citation metadata leak | false | false | false |
| final status | completed | completed | partial_success |
| E/C/raw chunk/table ID in final answer | false | false | false |

### Q1

- S1 selected the correct official 2024 annual report and `2024-12-31` period.
- S5 normal structured data had revenue and the supplement added parent net profit from the selected report.
- S5 emitted `net_margin=50.46%`; both operands used request-local `E7` and the same 2024/CNY scope.
- S6 returned readable output and cited the derived fact.
- S7 citation validation was valid, `resolved_derived_fact_ids=[C1]`; numeric validation was valid with no unsupported numbers.
- S8 final status was `completed`, `partial=false`.

### Q2

- Same correct report, period, operands, `E7`, and derived fact.
- S7 citation and numeric validation were both valid; final status `completed`.
- This request itself passed the runtime data/validation gate, but overlapped with Q3 at the backend execution boundary.

### Q3

- Same correct report and period; operands were request-local `E1` for this request.
- S5 emitted the same deterministic net margin.
- The LLM introduced explanatory “每100元” twice. Citation resolution rejected its submitted references and numeric validation rejected the unsupported `100` tokens.
- S7 was persisted as failed with `CITATION_VALIDATION_FAILED`; S8 safely recorded `partial_success`. It was not represented as completed and was not retried.

## 5. Safety and closure assessment

- Timeout count: 0/3.
- Full S0–S8 validations satisfying the content gate: 2/3 (Q1 and Q2).
- Wrong report/year: none.
- Cross-report operands: none.
- Unsupported financial numbers presented as validated: none; Q3 was downgraded.
- Raw chunk IDs in prompt model-visible contract: false by the request-local evidence builder and metadata-stripping boundary.
- Raw chunk IDs, internal table names, E-labels, or C-labels in final answers: false for all three.
- Production mutation: none.

The substantive structured-operand runtime chain is demonstrated by Q1 and Q2. The closure run nevertheless fails its fixed-plan integrity condition because Q2/Q3 were not strictly serial through backend completion. The evidence cannot be repaired by retrying because each question was allowed only once.

## 6. Conditional commit

- Commit created: no.
- Commit SHA: none.
- Committed files: none.
- Reason: Step 4 was not fully satisfied due to the Q2/Q3 backend overlap; therefore the conditional commit gate was not opened.
- No historical dirty file or historical artifact was staged.

No push, deployment, production image rebuild, migration, secret change, timeout change, or traffic expansion was performed.

Final status: `STRUCTURED_FACT_RUNTIME_NOT_READY`

Final traffic decision: `HOLD_1_PERCENT`
