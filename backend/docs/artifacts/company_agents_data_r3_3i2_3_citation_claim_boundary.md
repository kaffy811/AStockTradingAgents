# Phase 6W-R3.3I.2.3 — Provenanced Citation Claim Boundary Repair

## Final decision

`CITATION_CLAIM_BOUNDARY_NOT_READY`

Traffic: `HOLD_1_PERCENT`

The citation/numeric boundary repair is implemented, test-green, and Q3 passes the complete runtime gate—including its formula `×100%` and “每100元” explanation. The mandatory Q1 runtime sample timed out at S6, so the conditional commit requirement that both Q1 and Q3 complete S0–S8 with valid citation/numeric validation is not met. Timeout behavior was not changed and Q1 was not retried.

## 1. Workspace boundary

- HEAD: `b055da8495c54bb37625f0b0e0f94b4d4a627de2`
- Branch: `release/demo-staging`
- Entry/final `git diff --check`: clean.
- Historical tracked dirty files preserved and excluded: `backend/Dockerfile`, `backend/app/main.py`, `backend/app/services/report_embedding_provider.py`, `backend/pyproject.toml`, `backend/uv.lock`.
- R3.3I implementation remains in the isolated candidate tree `/private/tmp/tradingagents-r33e1.IfXFWV`; no reset, clean, checkout, or historical artifact overwrite occurred.

## 2. Frozen Q3 boundary repair

The frozen failure `ba464706` was retained as the diagnostic baseline. No request replaced or erased it.

Implemented request-local views:

1. **LLM-visible compacted evidence** remains produced by `_build_local_evidence_context()` and serialized into the prompt with only `E1..En`, report scope, section, compact content, and score.
2. **Canonical validation evidence** is built by `_build_canonical_validation_evidence_map()` using the same E-label positions and raw retrieved chunk identity, but maps each label to its un-compacted current-request chunk for backend-only validation.

Candidate implementation locations:

- `backend/app/agent/report_chat_copilot_agent.py:725-747`: compact/model evidence view.
- Same file `:750-761`: same-label canonical validation map.
- Same file `:777-875`: citation resolver uses canonical evidence, explicit selected-year guard, and C1 canonical operand verification.
- Same file `:1660-1677`: build both views; Prompt still receives compact JSON while backend paths receive canonical map.
- Same file `:2078-2080`: final numeric validation uses the request-local derived-formula wrapper.
- `backend/app/services/report_derived_fact_service.py:161-176`: marks percentage ratios with `formula_type=ratio_percentage` without changing arithmetic.
- Same file `:242-258`: verifies every operand period/value against canonical evidence.
- Same file `:261-305`: constrained scale-constant validation.

Raw chunk identifiers remain backend-only. The model-visible JSON and final answers contain no chunk ID or database table metadata.

## 3. Formula scale constant boundary

The global numeric validator was not modified. Report-agent validation first calls the existing validator and may remove only rejected `100`/`100%` tokens when all of these are true:

- a generated fact is marked `formula_type=ratio_percentage`;
- all fact operands are present in request-local canonical evidence with matching period and value;
- each rejected occurrence is in an explicit `每100元` or `×100%` formula span;
- the same span contains an approved derived result token such as `50.46%`;
- every unsupported token is exactly `100` or `100%`.

Independent `100`, `1000`, fabricated values, missing operands, mismatched years, or unrelated formulas remain rejected.

Derived citations additionally fail closed unless operand values are directly present in canonical evidence; the derived result string alone is insufficient.

## 4. Strict serial harness

Diagnostic-only harness: `/private/tmp/tradingagents-r33e1.IfXFWV/backend/scripts/r33i2_strict_serial_harness.py`.

Before launching the next request it requires:

- terminal API response received;
- S8 persisted with completed stage status;
- trace `completed_at` recorded;
- isolated health probe successful.

It preserves and waits for the actual HTTP call rather than treating a tool yield/session handle as completion. During acceptance the harness process session was continuously polled until exit.

Runtime timestamps prove strict serialization:

- Q1 `d9161951` completed/S8 terminal: `2026-08-30 01:02:15.800889Z`.
- Q3 `3d3b4035` launched: `2026-08-30 01:02:30.828335Z`.
- Gap after Q1 backend completion: 15.027446 seconds.
- Both four-condition gate records are true.

## 5. Tests

| Command/suite | Collected | Passed | Failed | Skipped | Duration |
|---|---:|---:|---:|---:|---:|
| Existing R3.3I/I.2 plus frozen diagnosis regression | 37 | 37 | 0 | 0 | 0.74s |
| Initial phase-specific boundary + harness + prior regression | 40 | 39 | 1 | 0 | 0.82s |
| Final phase-specific boundary + harness + prior regression | 40 | 40 | 0 | 0 | 0.55s |

The one initial failure correctly exposed that C1 claim validation still trusted the derived result even when operand canonical text was absent. A fail-closed canonical operand guard was added, after which all tests passed.

Coverage includes:

- canonical E1 succeeds when compact E1 omits numbers;
- fabricated `9999.99` and wrong-period claims fail;
- C1 requires operand canonical evidence;
- constrained formula `100` succeeds while independent `100`, `1000`, and missing-operand formulas fail;
- prior Q1/Q2 derived/citation behavior;
- D3 metadata containment;
- strict four-condition serial gate.

## 6. Isolated runtime identity

- Image: `tradingagents-backend:rc-r33i2-3-runtime`
- Digest: `sha256:791ff71c4c37b62484ad8683b1f1a48e13ef0a4579812a5a739395e9b574f63c`
- OCI revision: `r33i2-3-canonical-boundary`
- Container: `96abc5e7f49bec16c0eaef4a2969994ca9faacc9bd7b1f43bd5b1d20fd8e76a6`
- Mounts: none.
- Network/data: isolated `tradingagents-r33i-run-net`, `r33i-run-postgres`, `r33i-run-redis`.
- Production/staging containers, databases, Redis, images, and secrets were unchanged.

## 7. Strictly serial runtime acceptance

Only the two predefined requests were issued by the harness, once each, with unique sessions, `force_refresh=true`, explicit report 1/year 2024, and no memory/final-answer cache reuse.

| Item | Q1 `d9161951` | Q3 `3d3b4035` |
|---|---|---|
| Selected report / period | report 1, 2024 annual, `2024-12-31` | same |
| S5 operands | revenue + parent net profit | same |
| S5 derived fact | C1 `50.46%`, E7, `ratio_percentage` | C1 `50.46%`, E1, `ratio_percentage` |
| S6 | `REPORT_LLM_TIMEOUT`, 90.278s | completed, raw output present, 14.536s |
| Formula text | no model output | includes `×100%` and `每100元` |
| S7 citation | not reached | valid; C1 resolved |
| S7 numeric | not reached | valid; unsupported count 0 |
| Citation metadata leak | no final leak | false |
| Final | `partial_success` | `completed` |
| Four-condition gate | true | true |

Q3 exactly satisfies the requested runtime gate:

- S5 contains revenue, net profit, and `net_margin=50.46%`.
- S6 contains no raw chunk ID/internal metadata.
- S7 citation validation valid.
- S7 numeric validation valid.
- S8 completed.
- citation metadata leak false.

Q1 safely stopped at S6 timeout and persisted S8 as `partial_success`; it was not disguised as completed and was not retried. Because Q1 did not reach S7, the all-samples conditional submission gate failed.

## 8. Commit and operations

- Commit created: no.
- Commit SHA/files: none.
- Reason: mandatory Q1 and Q3 full validation condition was not met due to Q1's unchanged timeout.
- No historical dirty file was staged.
- No push, deployment, migration, production image rebuild, production container change, or traffic expansion occurred.

Final status: `CITATION_CLAIM_BOUNDARY_NOT_READY`

Traffic decision: `HOLD_1_PERCENT`
