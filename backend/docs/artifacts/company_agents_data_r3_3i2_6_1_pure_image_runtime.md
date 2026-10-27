# Phase 6W-R3.3I.2.6.1 — Pure Image Runtime Provenance Closure

## Final decision

`PURE_IMAGE_RUNTIME_PROVENANCE_READY`

Traffic: `HOLD_1_PERCENT`

The final pure image for commit `154c65c7` executed the frozen Q3 exactly once. The persisted trace records the same full Git SHA and image digest as the running container. S0–S8 completed, C1 was generated, citation and numeric validation passed, and metadata leakage was false.

## 1. Final image identity

- Tag: `tradingagents-backend:rc-r33i2-5-154c65c`.
- Full digest/image ID: `sha256:911cf927b7255f920cacadc750af7ffce6632a5b73f8dfb87caa961aed3b0383`.
- OCI revision: `154c65c7df236db74fd37ea8167ca15e72241f0a`.
- OCI source: `pure-detached-worktree`.
- Created: `2026-08-30T02:24:07.098131667Z`.
- Repo tag list: `tradingagents-backend:rc-r33i2-5-154c65c` only.

| Key source file | Git blob at `154c65c7` | Image SHA-256 |
|---|---|---|
| `backend/app/agent/report_chat_copilot_agent.py` | `167aaf6359f55473a5278b3eff94a9554e09c601` | `f75847ed1f6826b8c9619df0b3133d91ea1ae9e68f754a481740e155569fb13d` |
| `backend/app/services/report_derived_fact_service.py` | `6b6c7cefedac838a8185671c1387dd005a20eb30` | `cd5462036d7ed4c1b869371ac44229ba16f811507c358468bbd02aa641d1d096` |

For each file, `git rev-parse HEAD:path == git hash-object path`; the image bytes match the recorded source SHA-256. No host source bind mount was used.

The excluded snapshot remains distinct:

- Snapshot digest: `sha256:08587ed18a9c2ed59c996bb76bc2f45b5876b05f6418fafa7ce0e42466e01e42`.
- Snapshot revision: `r33i2-5-snapshot-36f67bc69e9f`.
- It was not used for this request.

## 2. Isolated runtime identity

- Backend container: `r33i2-6-1-pure-backend`.
- Container ID: `e614cea5775072f21cd71ab2d0a1a5fc959df5465e3c71f2b857bb18797a6994`.
- Container image ID: `sha256:911cf927b7255f920cacadc750af7ffce6632a5b73f8dfb87caa961aed3b0383`.
- Mounts: `[]`.
- Network: `tradingagents-r33i-run-net`, ID `ada68a4f92dfc6f5fe4150a5bee2faa1a246f8450f92254b853401cdd876180c`.
- PostgreSQL container: `r33i-run-postgres`, ID `0c513420c58202462f9eb50a0eab6c2eaff6a8f27bcad61229f8a4b2e8535d41`.
- PostgreSQL database: `tradingagents_r33i_run`; service host `r33i-run-postgres`; server `172.25.0.2/32:5432`.
- Redis container: `r33i-run-redis`, ID `f4b5dc55b5a4e67a53fa942707119c930341f3205b73fc2ed7e22fd2a45fceab`.
- Redis namespace: `r33i-run-redis:6379/0`; ping successful.
- Candidate API health: app, DB, and Redis all `ok` before Q3.

No production connection, source mount, container restart, or container replacement occurred.

## 3. Data and schema gate

- Alembic version: `r6s7t8u9v0w1`.
- `report_analysis_traces` and `report_analysis_trace_stages`: present.
- Selected indexed document gate:
  - report ID `1`;
  - symbol `600519`;
  - year `2024`;
  - type `annual`;
  - source `https://static.cninfo.com.cn/finalpage/2025-04-03/1222993920.PDF`;
  - status `indexed`;
  - active index `1`;
  - declared chunks `208`, actual chunks `208`.

The source is official CNINFO. No migration or data initialization was needed or executed in this phase. Production migration count and production data writes were both zero.

## 4. One-shot Q3 and image-to-trace provenance

- Question: `请根据贵州茅台2024年营业收入和归母净利润计算并解释净利率。`
- Request ID: `f06c4525`.
- Trace ID: `b3699eeb-4c12-4a75-9e35-9c5f67bf1998`.
- Unique session hash: `1d58e613b4f14286cd3b17645d6169d9464024efa86989a1fed2347b66e4bd05`.
- `force_refresh=true`; final-answer cache `bypass`; retry count `0`.
- Started: `2026-08-30T13:32:11.496087Z`.
- Completed: `2026-08-30T13:33:30.319183Z`.
- Four-condition gate: API terminal true, S8 persisted true, backend completion marker true, health true.

Persisted trace identity:

```text
git_sha = 154c65c7df236db74fd37ea8167ca15e72241f0a
runtime_image_identity = sha256:911cf927b7255f920cacadc750af7ffce6632a5b73f8dfb87caa961aed3b0383
container image = sha256:911cf927b7255f920cacadc750af7ffce6632a5b73f8dfb87caa961aed3b0383
```

This establishes an exact commit → image → container → isolated DB/Redis → trace chain.

## 5. S0–S8 results

| Stage | Status | Duration | Evidence |
|---|---|---:|---|
| S0 | completed | 2ms | Frozen Q3 accepted once; report 1/year 2024; force refresh true. |
| S1 | completed | 9ms | Selected report 1, 2024 annual, period `2024-12-31`, explicit report selection. |
| S2 | completed | 84ms | Current-report hybrid evidence lookup completed; no retrieval timeout. |
| S3 | completed | 1ms | Six report-local chunks selected: raw IDs remain backend trace data. |
| S4 | completed | 0ms | Request-local evidence assembled and canonical source retained. |
| S5 | completed | 8ms | Revenue `170899152276.34 CNY`, net profit `86228146421.62 CNY`, both 2024/E1; C1 `net_margin=50.46%`, `ratio_percentage`. |
| S6 | completed | 78,663ms | LLM completed without timeout; raw answer contained 50.46% and “每100元”. |
| S7 | completed | 13ms | Citation valid, C1 resolved, numeric valid, formula policy C1, unsupported tokens empty, metadata leak false. |
| S8 | completed | 1ms | Final status `completed`, partial false, errors empty. |

The final answer contains no raw chunk ID, E-label, internal table name, or metadata identifier. API source payload remains separate from the user-facing answer.

## 6. Production and operations boundary

Production/staging backend identities before and after remained:

- Production: `c9567bfdfec4892823d7a5febd09d1cba2e4fac2ba6dd300082f74bfd0140bee`, image `sha256:48a50ce2435e379c46f0ed0afa1878a5f9c8e9f223dcb418bb4bbc1a944987db`.
- Staging: `c8dada5aa80ca483bacbdc22c6ac9da77ba766098b44163deb0bde13cfd6fbcd`, image `sha256:bf92b046c42bf7d5498418373d3d0ddec182dfcda91057af9890734432eebf69`.

No production code, test, Prompt, validator, derived-fact rule, RAG, cache, timeout, container, database, or Redis change was made. No new source image was built. No push, merge, deployment, migration, or traffic expansion occurred.

Final status: `PURE_IMAGE_RUNTIME_PROVENANCE_READY`

Traffic decision: `HOLD_1_PERCENT`
