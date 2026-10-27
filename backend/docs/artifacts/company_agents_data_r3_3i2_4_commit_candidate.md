# Phase 6W-R3.3I.2.4 — Minimal Commit and Pure-Candidate Verification

## Final decision

`CANDIDATE_REGRESSION_DETECTED`

Traffic: `HOLD_1_PERCENT`

The minimal provenance repair was committed and reproduced in a clean detached image. The one permitted cold Q3 request completed S0–S8, resolved citations and C1 provenance, but the numeric gate rejected the formula constants `100%` and `100`. The request safely ended as `partial_success`. It was not retried and no validator rule was changed.

## 1. Workspace and commit boundary

- Main workspace pre/post HEAD: `b055da8495c54bb37625f0b0e0f94b4d4a627de2`.
- Main branch: `release/demo-staging`; its dirty working tree was not switched, reset, cleaned, or overwritten.
- Validated candidate parent: `5e9977a3d43fd64d75a09156e800889483404458` on linked worktree branch `r33e-pgvector-portability`.
- New independent commit: `28870a13d98f6e7bab5a2b16c6f3144411859198`.
- Message: `fix(report-agent): preserve claim provenance for derived facts`.
- Pre-commit `git diff --cached --check`: clean; post-commit staging area: empty.
- Historical tracked dirty files preserved and excluded: `backend/Dockerfile`, `backend/app/main.py`, `backend/app/services/report_embedding_provider.py`, `backend/pyproject.toml`, `backend/uv.lock`.
- The candidate parent is two commits ahead of the main workspace HEAD. Those existing parent commits include migration/dependency work; none of those files appears in the new commit's 14-file diff.

### Actual commit files

1. `HKNA/update_report/update_101.md`
2. `backend/app/agent/prompts/report_chat_system.md`
3. `backend/app/agent/report_chat_copilot_agent.py`
4. `backend/app/services/report_derived_fact_service.py`
5. `backend/app/services/report_local_structured_operand_supplement.py`
6. `backend/docs/artifacts/company_agents_data_r3_3i2_3_citation_claim_boundary.json`
7. `backend/docs/artifacts/company_agents_data_r3_3i2_3_citation_claim_boundary.md`
8. `backend/scripts/r33i2_strict_serial_harness.py`
9. `backend/tests/test_phase6w_r3_3_trace_durability.py`
10. `backend/tests/test_phase6w_r3_3i2_2_q3_validation_diagnosis.py`
11. `backend/tests/test_phase6w_r3_3i2_3_citation_claim_boundary.py`
12. `backend/tests/test_phase6w_r3_3i2_3_serial_harness.py`
13. `backend/tests/test_phase6w_r3_3i2_structured_operand_coverage.py`
14. `backend/tests/test_phase6w_r3_3i_derived_fact_provenance.py`

This phase's post-commit artifacts and `update_102.md` are intentionally uncommitted so the verified SHA remains immutable.

## 2. Tests

Final configured command:

```text
env DATABASE_URL=postgresql+asyncpg://test:test@localhost:5432/test SECRET_KEY=<test-value> DEEPSEEK_API_KEY=<test-value> .venv/bin/python -m pytest -q tests/test_phase6w_r3_3_trace_durability.py tests/test_phase6w_r3_3i_derived_fact_provenance.py tests/test_phase6w_r3_3i2_structured_operand_coverage.py tests/test_phase6w_r3_3i2_2_q3_validation_diagnosis.py tests/test_phase6w_r3_3i2_3_citation_claim_boundary.py tests/test_phase6w_r3_3i2_3_serial_harness.py --durations=0
```

- Collected: 44; passed: 44; failed: 0; skipped: 0; duration: 0.67s.
- Two earlier setup attempts stopped during collection because required test settings were absent/too short. They did not run tests and were corrected only by supplying test environment values; no test threshold or business code changed.

## 3. Pure candidate identity

- Detached clean worktree: `/private/tmp/tradingagents-r33i2-4-pure.adXrqd`; HEAD `28870a13...`; porcelain status empty before build.
- Image: `tradingagents-backend:rc-r33i2-4-28870a1`.
- Image digest: `sha256:2be2ca15711eb5ff96076c5c9d95a9b2f53c7979da16220a12d727ebcac1cccb`.
- OCI revision: `28870a13d98f6e7bab5a2b16c6f3144411859198`.
- Candidate container: `c3d80e3640a4083a92b93266d62510f610cdb27357401d5a10bf3105515d03e4` (`r33i2-4-pure-backend`).
- Mounts: `[]`; no source bind mount.
- Isolated data namespace: `tradingagents-r33i-run-net`, `r33i-run-postgres`, `r33i-run-redis`.
- Health: API `ok`, DB `ok`, Redis `ok` before Q3.

### Source hash proof

| File | Git blob | Image/host SHA-256 |
|---|---|---|
| `report_chat_copilot_agent.py` | `2acc43648367279e794a27cdb031bb5938f63d7d` | `791f5b45b500eeeaf8e0235e9736163f993cfc4435ad09530baf321340ef6f0e` |
| `report_derived_fact_service.py` | `467e8a5ef65538c7d271b90e68f797c987400cc7` | `8b9fbc67c68e56401ceb982e86851dcce8661249edd25e5b66b3cd2495acb3b2` |
| `report_local_structured_operand_supplement.py` | `ec321e3f3e51395703ed33ee8f382217afd649b9` | `739e57cdffc7aa16c4161032a4d2ce364abded6ce796bc7db9ad52ebf2125e86` |

For every file, `git rev-parse HEAD:path == git hash-object path`, and the image SHA-256 equals the clean worktree SHA-256.

## 4. One-shot pure-candidate Q3

- Frozen question: `请根据贵州茅台2024年营业收入和归母净利润计算并解释净利率。`
- Request: `ab337d23`; trace: `fbd038bc-d047-4905-aa4a-20a22a29f1bc`.
- Unique session: `r33i2-4-210e3e8795df-q1`; `force_refresh=true`; final-answer cache bypass; memory disabled.
- Started `2026-08-30 01:24:26.103819Z`; terminal/S8 `2026-08-30 01:24:51.825682Z`.
- Four-condition gate: API terminal true, S8 persisted true, backend completion marker true, health true.

| Stage | Result |
|---|---|
| S0 | Frozen request accepted once. |
| S1 | Report 1, 2024 annual, period `2024-12-31`, explicit report selection. |
| S2–S4 | Current-report retrieval completed; request-local `E1..E6` assembled. |
| S5 | Revenue `170899152276.34 CNY`, net profit `86228146421.62 CNY`, both period 2024/E1; C1 `net_margin=50.46%`, `ratio_percentage`. |
| S6 | Completed in 25.271s; LLM used 50.46%, `×100%`, and `每100元`; no raw chunk/internal metadata in answer. |
| S7 citation | Valid; resolved count 2; C1 resolved; metadata leak false. |
| S7 numeric | Invalid; first rejected tokens `100%`, `100`, both first observed in S6 formula sentence. |
| S8 | Correct safe degradation: `partial_success`, `UNSUPPORTED_NUMBERS:100%, 100`. |

The final answer exposed no E-label, raw chunk ID, table name, or internal metadata. API `source_chunks` remains a backend response field and is not part of the user-facing answer text.

## 5. Prior Q1 timeout and operational boundary

The prior Q1 sample remained an unchanged `REPORT_LLM_TIMEOUT` with safe `partial_success`, no retry, no false `completed`, and no unsupported numeric publication. No Q1 was issued in this phase.

Regression occurred: yes. It is specifically the pure-commit numeric formula-scale path; citation boundary, operand provenance, report/year scope, and metadata containment passed. Per phase rules, no retry or remediation was attempted.

No push, deployment, migration, production image/container/database/Redis change, or traffic expansion occurred.

Final status: `CANDIDATE_REGRESSION_DETECTED`

Traffic decision: `HOLD_1_PERCENT`
