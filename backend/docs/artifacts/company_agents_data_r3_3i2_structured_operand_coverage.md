# Phase 6W-R3.3I.2 — Structured Financial Operand Coverage Remediation

## Final decision

`STRUCTURED_FACT_COVERAGE_NOT_READY`

Traffic: `HOLD_1_PERCENT`

The report-local operand gap is remediated and Q1 S5 emits an auditable `net_margin=50.46%`, but Q1 terminates at S6 with `REPORT_LLM_TIMEOUT`. It therefore does not meet the required `completed + numeric_validation.valid=true` runtime gate. Timeout remediation is explicitly outside this phase.

## Workspace boundary

- HEAD: `b055da8495c54bb37625f0b0e0f94b4d4a627de2`
- Branch: `release/demo-staging`
- `git diff --check`: clean at entry; candidate diff check also clean after implementation.
- Historical tracked dirty files preserved: `backend/Dockerfile`, `backend/app/main.py`, `backend/app/services/report_embedding_provider.py`, `backend/pyproject.toml`, `backend/uv.lock`.
- Existing historical untracked reports under `HKNA/`, `backend/docs/artifacts/`, and `memory/` were not overwritten.
- R3.3I.1 uncommitted implementation remains isolated under `/private/tmp/tradingagents-r33e1.IfXFWV`.
- R3.3I.2 candidate additions: `report_local_structured_operand_supplement.py`, its integration edits, and `test_phase6w_r3_3i2_structured_operand_coverage.py` in that isolated tree. This report, its JSON peer, and `HKNA/update_report/update_100.md` are the only current-workspace additions.

## Read-only evidence matrix

Selected scope: report id `1`, `600519.SH`, 2024 annual, period `2024-12-31`, official CNINFO PDF `https://static.cninfo.com.cn/finalpage/2025-04-03/1222993920.PDF`.

| Operand | 原始证据文本 | Period | Unit | Source chunk | 可映射 evidence ID | 是否可用 |
|---|---|---|---|---|---|---|
| revenue | “主要会计数据 2024年 2023年 … 营业收入 170,899,152,276.34 147,693,604,994.14” | 2024 / selected `2024-12-31` | 元；币种人民币 | same active indexed report, chunk 4, pages 5–6 | Q1 `E7` | 是 |
| net_profit | “归属于上市公司股东的净 利润 86,228,146,421.62 74,734,071,550.75” | 2024 / selected `2024-12-31` | 元；币种人民币 | same active indexed report, chunk 4, pages 5–6 | Q1 `E7` | 是 |

The active RAG document has `report_id=1`, `report_year=2024`, `report_type=annual`, `status=indexed`, `active_index=1`, and 208 chunks. Both operands are directly locatable in one chunk, with an explicit year header and unit/currency header.

## Minimal implementation

Candidate-tree locations:

- `/private/tmp/tradingagents-r33e1.IfXFWV/backend/app/services/report_local_structured_operand_supplement.py:61`: trigger only for requested net margin and missing operands.
- Same file `:79`: exact selected period guard; `:86`: selected active annual report guard; `:102`: bounded lookup (limit 8) inside the selected report; `:118`: year/unit/currency validation; `:139`: provenance-bearing fields.
- `/private/tmp/tradingagents-r33e1.IfXFWV/backend/app/agent/report_chat_copilot_agent.py:1610`: merge supplement before derived-fact build; `:1640`: bind request-local E labels; `:1647`: build derived facts; `:1674`: persist supplement/S5 audit.
- `/private/tmp/tradingagents-r33e1.IfXFWV/backend/app/services/report_derived_fact_service.py:119`: reject structured operands without request-local evidence IDs or complete provenance.

No generic retrieval ranking/threshold, schema, embedding, chunking, report selection, validator, prompt strategy, cache TTL, frontend, Company Overview, D3 containment, D5/D7, or timeout logic was changed.

## Before / after

Frozen R3.3I.1 Q1:

- S5 fields: `[]`
- S5/S7 derived facts: `[]`

R3.3I.2 Q1:

- Original normal extraction: revenue present; parent net profit missing.
- Supplement audit: `missing=[parent_net_profit]`, `supplemented=[parent_net_profit]`, reason `complete_report_local_evidence`.
- S5 snapshot: revenue + parent net profit, both period `2024-12-31`.
- Derived fact: `net_margin`, `50.46%`, operands revenue `170899152276.34` and net profit `86228146421.62`, both cited by request-local `E7`.
- Model-visible records contain E labels only; raw chunk ids are stripped. Unit tests confirm prompt/citation/validator helpers preserve this containment.

## Q1–Q3 isolated runtime acceptance

All three allowed questions were issued serially against only `r33i-run-backend` on `127.0.0.1:18005`. No additional question was issued.

| Q | Request | S0–S8 / endpoint | Result |
|---|---|---|---|
| Q1 net margin | `85f64702` | S0–S6, S8; S7 absent because synthesis produced no output | S5 emitted net margin; S6 `REPORT_LLM_TIMEOUT` after 90s; final `partial_success`; numeric validation unavailable |
| Q2 revenue/profit growth | `146efe3d` | S0–S8 | `partial_success`; citation validation false and unsupported `15%` (existing independent boundary; not modified) |
| Q3 operating cash flow | `ea528f60` | S0–S6, S8; S7 absent | S6 `REPORT_LLM_TIMEOUT`; final `partial_success` |

Q1 required audit:

- selected report/period: report 1, 2024 annual, `2024-12-31`.
- original structured count: 1 (`revenue`).
- supplemented count: 1 (`parent_net_profit`).
- revenue provenance: report-local direct evidence in Q1 `E7`, chunk 4 internally, pages 5–6.
- net-profit provenance: supplement record, Q1 `E7`, same report/period/unit and same source chunk.
- derived build: emitted `C1 net_margin=50.46%` with complete operand provenance.
- prompt assembly: derived fact was available before S6; model-visible payload contains `E7`, not raw chunk id.
- citation validation / numeric validation: not executed because S6 timed out and no S7 exists.
- final status: `partial_success`, not `completed`.
- raw chunk-id leakage: none in final answer; D3 unit regression also passed.

## Tests

| Command | Collected | Passed | Failed | Skipped | Duration |
|---|---:|---:|---:|---:|---:|
| `python -m pytest -q tests/test_phase6w_r3_3i2_structured_operand_coverage.py tests/test_phase6w_r3_3i_derived_fact_provenance.py tests/test_phase6w_r3_3_trace_durability.py --disable-warnings --durations=10` with test-only DB/secret/provider env | 34 | 34 | 0 | 0 | 0.58s |

Coverage includes real-field net margin construction, empty structured fields plus complete supplement, missing operands, different periods, incompatible units, unbound E labels, S5 persistence, prompt/derived-fact integration, numeric validation corpus, D3 metadata containment, and ordinary unrequested report QA.

An earlier environment-misconfigured invocation collected 27 tests and reported 12 failures/15 passes in 0.68s because required Settings values were absent; after supplying valid test-only settings it was rerun. A second configuration attempt collected 27 tests and reported 6 failures/21 passes in 1.06s because the test provider key was absent; the final command above is authoritative and green.

## Release assessment

Minimal commit condition: **not met**. The operand coverage implementation itself is test-green and its S5 runtime behavior is correct, but the mandatory Q1 end-to-end acceptance failed at the unchanged S6 timeout boundary. Per phase scope, no timeout, D5, D7, or unrelated remediation was attempted.

No commit, push, migration, production/staging deployment, production container replacement, or traffic expansion was performed. Only the isolated `r33i-run-backend` candidate container was updated/restarted for acceptance.

Final state: `STRUCTURED_FACT_COVERAGE_NOT_READY`

Traffic decision: `HOLD_1_PERCENT`
