# Phase 6W-R3.3I.2.5 — Formula Constant Validation Boundary Repair

## Final decision

`FORMULA_CONSTANT_BOUNDARY_READY`

Traffic: `HOLD_1_PERCENT`

## 1. Frozen failure and attribution

- Frozen request/trace: `ab337d23` / `fbd038bc-d047-4905-aa4a-20a22a29f1bc`, produced by commit `28870a13d98f6e7bab5a2b16c6f3144411859198`.
- S5 contained C1 `net_margin=50.46%`, `formula_type=ratio_percentage`, revenue and net-profit operands, both tied to canonical E1.
- Citation validation was valid, C1 resolved, and metadata leakage was false.
- Exact failing S6 spans included:
  - `净利率=归属于上市公司股东的净利润÷营业收入×100%。`
  - `按上述数据计算，贵州茅台2024年每实现100元营业收入，对应约50.46元归属于上市公司股东的净利润。`
- S7 rejected `100%` and `100`; both were first observed in S6. The global validator output was `unsupported_numbers_found`, producing safe `partial_success`.

Classification: `F3_ANSWER_SPAN_NOT_RECOGNIZED_AS_FORMULA`.

First failure was `validate_numeric_claims_with_derived_formula_scales()` at the former `report_derived_fact_service.py:298-302`. It required every formula sentence to contain an exact derived validation token. The first span bound C1 through operand names but did not repeat `50.46%`; the second contained `50.46元` and `每实现100元`, neither recognized by the old exact-token/phrase check. Formula policy emission and final-validator wiring were present, so this was not F1/F2/F4.

## 2. Minimal request-local repair

- `backend/app/services/report_derived_fact_service.py:261-291` emits a policy only when C1 is citation-resolved, `ratio_percentage`, and every operand is present in canonical request-local evidence.
- `:294-312` binds a formula span to the same policy by either the derived result number or all canonical operand metric names.
- `:315-357` keeps the global validator unchanged and consumes an optional, default-empty policy. Only exact rejected tokens `100`/`100%`, explicit `×100%`, `每100元`, or `每实现100元`, and a C1-bound span may pass.
- `backend/app/agent/report_chat_copilot_agent.py:2076-2104` builds the policy after citation resolution and passes it only to this request's final numeric gate. S7 records `formula_policy_ids`.

The policy contract is:

```json
{
  "derived_fact_id": "C1",
  "operation": "ratio_percentage",
  "operand_evidence_ids": ["E1"],
  "operand_metrics": ["net_profit", "revenue"],
  "derived_result": "50.46%",
  "allowed_formula_constants": ["100", "100%"]
}
```

No constant is appended to global evidence or the global allowed set. Missing policy, unresolved C1, incomplete operands, independent `100`, non-formula `100%`, `1000`, `10000`, `101`, `99%`, or fabricated `9999.99` remains rejected.

## 3. Tests

| Run | Collected | Passed | Failed | Skipped | Duration | Result |
|---|---:|---:|---:|---:|---:|---|
| Initial expanded suite | 48 | 47 | 1 | 0 | 0.90s | Test fixture omitted the existing extractor's table shape; no policy failure. |
| Fixture-corrected suite | 48 | 47 | 1 | 0 | 0.74s | Exposed exact `每实现100元` phrase gap. |
| Final suite | 48 | 48 | 0 | 0 | 0.67s | Green. |

Final command covered trace durability, derived provenance, operand supplement, frozen Q3 diagnosis, citation/formula boundary, and strict serial harness tests. Direct end-to-end coverage at `test_phase6w_r3_3_trace_durability.py:141-170` drives frozen S5/S6 through the final report-chat S7 gate. Negative coverage is at `test_phase6w_r3_3i2_3_citation_claim_boundary.py:61-103`.

## 4. Isolated one-shot runtime

- Source baseline: `28870a13...` plus scoped four-file diff; snapshot hash `36f67bc69e9fae5d8d5f12f2ce1369a34683c190c9cf468792f254c7a90c4403`.
- Snapshot image: `tradingagents-backend:rc-r33i2-5-snapshot`.
- Digest: `sha256:08587ed18a9c2ed59c996bb76bc2f45b5876b05f6418fafa7ce0e42466e01e42`.
- Container: `ee83239bb769e54b7ebaa284a05e0eb6e5e22ea72454e486a77724abcf74a26e`; mounts `[]`.
- Isolated namespace: `tradingagents-r33i-run-net`, `r33i-run-postgres`, `r33i-run-redis`.
- Image/host source hashes matched: copilot `f75847ed...fb13d`; derived service `cd546203...d096`.

Only Q3 was issued, once, with unique session, `force_refresh=true`, final-answer cache bypass, and the four-condition terminal gate.

- Request: `9cf98947`; trace: `819c10bf-dcc6-4aaa-a817-1bef4346dae1`.
- S1: report 1, 2024 annual, period `2024-12-31`.
- S5: revenue `170899152276.34`, net profit `86228146421.62`, C1 `50.46%`, E1.
- S6: completed in 84.643s; answer used `每100元` with `50.46元`; no timeout and no retry.
- S7: completed; citation valid; C1 resolved; formula policy IDs `[C1]`; numeric valid; unsupported tokens empty; metadata leak false.
- S8: `completed`, partial false, errors empty.

The answer exposed no raw chunk ID, E-label, table name, or internal metadata. Production/staging container identities were not replaced.

## 5. Commit and operations

The follow-up commit is created only after the tests and one-shot runtime passed. Its SHA is reported by the phase handoff because a Git commit cannot embed its own hash in its committed contents.

No push, deployment, migration, production database/Redis/container change, or traffic expansion occurred.

Final status: `FORMULA_CONSTANT_BOUNDARY_READY`

Traffic decision: `HOLD_1_PERCENT`
