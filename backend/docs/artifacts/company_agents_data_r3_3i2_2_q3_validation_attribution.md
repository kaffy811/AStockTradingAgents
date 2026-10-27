# Phase 6W-R3.3I.2.2 — Q3 Validation Failure Attribution

## Final decision

`Q3_VALIDATION_FAILURE_EXPLAINED`

Traffic: `HOLD_1_PERCENT`

Primary Q3 classification: `Q3-C CITATION_CLAIM_NOT_SUPPORTED_BY_EVIDENCE`.

The first failure occurs while validating the first submitted citation claim against its request-local compacted evidence. The citation labels and derived provenance are structurally valid, and the derived/numeric corpus contains `50.46%`; however, Q3's compacted `E1` text does not retain the numeric content asserted by the submitted claims. The resolver therefore rejects both claim IDs before full-answer numeric validation. Independently and later, the LLM added two unsupported `100` tokens, which produces the observed numeric failure (`Q3-F` as a secondary condition, not the first failure).

## 1. Workspace boundary

- HEAD: `b055da8495c54bb37625f0b0e0f94b4d4a627de2`
- Branch: `release/demo-staging`
- `git diff --check`: clean at entry and completion.
- Historical tracked dirty files remained unchanged: `backend/Dockerfile`, `backend/app/main.py`, `backend/app/services/report_embedding_provider.py`, `backend/pyproject.toml`, `backend/uv.lock`.
- No production code was modified. One diagnostic-only test was added in the isolated candidate tree: `/private/tmp/tradingagents-r33e1.IfXFWV/backend/tests/test_phase6w_r3_3i2_2_q3_validation_diagnosis.py`.
- No new runtime request was made. All findings use frozen Q3 request `ba464706`, trace `28a5a5e2-6e7d-440f-8857-94dcce7cb788`.

## 2. Frozen Q3 S0–S8

Question: `请根据贵州茅台2024年营业收入和归母净利润计算并解释净利率。`

| Stage | Status | Frozen evidence |
|---|---|---|
| S0 | completed | One request, `force_refresh=true`, report id 1, year 2024, unique session. |
| S1 | completed | Selected report 1, `600519.SH`, 2024 annual, period `2024-12-31`, explicit report selection. |
| S2 | completed | Indexed report evidence returned; no infrastructure error. |
| S3 | completed | Retrieved chunks persisted. |
| S4 | completed | Retrieval order starts with raw chunk 4; request-local mapping is constructed positionally after compaction, so chunk 4 becomes Q3 `E1`. |
| S5 | completed | Structured revenue `170899152276.34` CNY and supplemented net profit `86228146421.62` CNY, both 2024 and `E1`; emitted `C1 net_margin=50.46%`. |
| S6 | completed | Raw output present, 17.104s; used `50.46%` and introduced “每100元” twice. Citations submitted direct `E1` and derived `C1` with `evidence_ids=[E1]`. |
| S7 | failed | `CITATION_VALIDATION_FAILED`; `invalid_claim_ids=[E1,C1]`; numeric unsupported tokens `[100,100]`; citation metadata leak false. |
| S8 | completed | Correct safe downgrade: final `partial_success`, numeric validation false, citation validation false. |

No timeout, wrong report year, cross-report operand, unknown label, duplicate label, or raw chunk-id leak occurred.

## 3. First-failure attribution

| 检查项 | 实际值 | 预期值 | 第一次异常层 | 文件:行号 | 证据 |
|---|---|---|---|---|---|
| S5 derived fact | `C1 net_margin=50.46%`, operands `E1`, 2024, CNY | same | none | `report_derived_fact_service.py:175-223` | Frozen S5 derived facts |
| Prompt derived fact | model-visible C1 with legal `E1`, no raw chunk id | same | none | `report_chat_copilot_agent.py:1640-1655`, `report_derived_fact_service.py:234-236` | S5 plus S6 submitted C1/E1 |
| Direct citation shape | `{evidence_id:E1, claim:2024 + exact operands}` | legal E-label and supported claim | **citation claim support** | `report_chat_copilot_agent.py:825-852` | E1 label exists, but compact E1 lacks asserted numeric span; claim numeric check false |
| Derived citation shape | `{derived_fact_id:C1,evidence_ids:[E1],claim:2024 + 50.46%}` | matching provenance and supported claim | citation claim support | `report_chat_copilot_agent.py:789-813` | provenance list matches; claim validation fails, recorded as invalid claim rather than invalid/unknown ID |
| Citation audit | `invalid_ids=[]`, `duplicate_ids=[]`, `invalid_claim_ids=[E1,C1]` | valid, resolved C1 | resolver | `report_chat_copilot_agent.py:859-867` | Frozen S7 payload |
| Derived validation corpus | includes canonical result and `50.46%` | contains derived result | none | `report_derived_fact_service.py:226-231`; integration `report_chat_copilot_agent.py:2033-2054` | Frozen S7 allowed summary contains both tokens |
| Full answer numeric | unsupported `[100,100]`, first observed S6 | no unsupported tokens | later full-answer numeric gate | `specialist_analysis_utils.py:245-260`; caller `report_chat_copilot_agent.py:2055` | Frozen token contexts show S1/S4/S5 false, S6 true |
| Final status | `partial_success` | downgrade on validation error | none | `report_chat_copilot_agent.py:2125-2143` | Errors/numeric invalid force partial |

First abnormal function: `_resolve_local_citations()`, direct citation branch, numeric claim validation at `/private/tmp/tradingagents-r33e1.IfXFWV/backend/app/agent/report_chat_copilot_agent.py:847-852`. The first citation is structurally valid `E1`, but its claim contains `2024`, `170,899,152,276.34`, and `86,228,146,421.62`; the compacted `E1` supplied to the resolver is truncated around the heading because PDF whitespace consumes the per-chunk compaction cap. The claim is therefore not supported by the model-visible evidence item used by this resolver.

The derived citation then reaches the provenance branch with the correct expected `[E1]`, proving provenance resolution was available. Its claim-support validation still fails because the expected operand evidence is the same compacted E1; this is recorded as `invalid_claim_ids=[...,C1]`, not `invalid_ids`.

## 4. Required answers

1. **Did S5 contain `net_margin=50.46%`?** Yes. It contains C1 with full operands and request-local E1 provenance.
2. **Did the Prompt contain the derived fact and legal E-label?** Yes. S5 built the model-visible fact before S6; S6 returned C1/E1 citations matching that contract. Raw chunk metadata was stripped.
3. **Did S6 use 50.46% and add numbers?** Yes. It used the approved value and added `100` twice in “每100元” explanations.
4. **Were the LLM citations legal E labels?** Yes. `E1` matches `E[1-9]\d*`; there were no unknown or duplicate labels.
5. **Could the resolver identify operand provenance?** Structurally yes: C1 existed and supplied `[E1]` exactly matched expected provenance. Claim support, not provenance identity, failed.
6. **Did the numeric corpus contain the derived value and operands?** Yes. Frozen allowed-token summary contains raw operands, unit-converted equivalents, canonical result, and `50.46%`. It does not contain `100`.
7. **Was `partial_success` the correct safe path?** Yes. Citation failure appends an error; unsupported numbers make `_numeric_invalid=true`; either prevents completed status.
8. **What differs between Q1/Q2 and Q3?** The report and deterministic operands do not differ. The user wording changes retrieval ordering/compaction: Q1/Q2 cite the derived fact through E7 and submit claims that pass; Q3 puts the operand chunk at E1, whose model-visible compacted span is insufficient for the submitted numeric claims. Q3's output additionally introduces `100` twice. Q1/Q2 resolve C1 and validate numerically; Q3 resolves neither citation claim and fails the full-answer numeric gate.

## 5. Classification

Primary: `Q3-C CITATION_CLAIM_NOT_SUPPORTED_BY_EVIDENCE`.

Secondary observed condition: `Q3-F LLM_EMITTED_UNSUPPORTED_NUMBER` for `[100,100]`.

Not selected:

- A/B: citation objects and labels are structurally legal; no unknown/duplicate labels.
- D: C1 and its expected `[E1]` provenance exist and match.
- E: derived validation corpus contains `50.46%` and canonical result.
- G: the finalizer correctly maps validation failure to `partial_success`.
- H: both citation and numeric failures are reproduced and explained.

## 6. Q1/Q2/Q3 difference matrix

| Dimension | Q1 | Q2 | Q3 |
|---|---|---|---|
| Selected scope | report 1 / 2024 annual | same | same |
| Derived fact | C1 50.46% / E7 | C1 50.46% / E7 | C1 50.46% / E1 |
| S6 derived value used | yes | yes | yes |
| Extra unsupported number | none | none | `100` twice |
| Citation claims | supported | supported | E1 and C1 claim support failed |
| Resolved derived IDs | C1 | C1 | none |
| Numeric valid | true | true | false |
| Final | completed | completed | partial_success |

## 7. Serial runner audit

Runner classification: `RUNNER_E_OTHER`.

Timeline:

| Marker | Q2 / Q3 evidence |
|---|---|
| Q2 launch | `00:28:24.147271Z` |
| Q2 S6 duration | 56.920s |
| Q2 backend terminal / S8 persisted | `00:29:21.222987Z` |
| Client orchestration marker | The nested execution call yielded at its 30s tool window and returned a live session handle rather than an HTTP completion result; the orchestration printed only output and discarded the session handle. |
| Q3 launch | `00:29:13.919678Z` |
| Overlap | Q3 began 7.303309s before Q2 completed |

This is not `RUNNER_A_WAITED_FOR_HTTP_ONLY`: the orchestration did not actually receive Q2's terminal HTTP response before proceeding. It is not a trace-flush or clock error: S6 duration, trace timestamps, and the later persisted response are consistent. The underlying HTTP request continued in the live PTY/server after the 30-second tool yield, while the higher-level runner treated the yield as completion and started its delay/Q3 sequence.

Future diagnostic harness gate (proposal only; not implemented):

1. Preserve and poll any returned execution/session handle until curl exits.
2. Require terminal HTTP response and parse request ID.
3. Poll that request ID until S8 is persisted and trace `completed_at` is non-null.
4. Require backend completion marker and a successful isolated health check.
5. Start the 15-second interval only after all four conditions are true.
6. Abort rather than launch the next request if any condition times out.

No production Agent change is needed to explain this sample. A future business decision could address evidence compaction/claim alignment or explanatory scale numbers, but that is outside this attribution phase. A minimal diagnostic-harness fix is needed before another strictly serial acceptance run.

## 8. Diagnostic tests

Diagnostic-only file: `/private/tmp/tradingagents-r33e1.IfXFWV/backend/tests/test_phase6w_r3_3i2_2_q3_validation_diagnosis.py`.

| Command | Collected | Passed | Failed | Skipped | Duration |
|---|---:|---:|---:|---:|---:|
| First frozen diagnostic run | 3 | 2 | 1 | 0 | 0.03s |
| Corrected frozen fixture rerun | 3 | 3 | 0 | 0 | 0.01s |

The first test failure showed the fixture had included only one occurrence of `100`; the frozen answer has two. The fixture was corrected without changing application code. Tests reproduce claim-support failure, assert Q1/Q2-supported versus Q3-unsupported output differences, and define a four-condition serial gate that blocks launch before S8/backend completion.

No production code, validator, prompt, retrieval, cache, timeout, container, database, or Redis was modified. No commit, push, deployment, migration, runtime request, retry, or traffic expansion occurred.

Final status: `Q3_VALIDATION_FAILURE_EXPLAINED`

Traffic decision: `HOLD_1_PERCENT`
