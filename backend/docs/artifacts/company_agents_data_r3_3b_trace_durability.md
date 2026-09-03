# Phase 6W-R3.3B — Agent Trace Durability Foundation

Date: 2026-08-26 (America/New_York)

Baseline: `9c65027eeef5d599ae13083affc926497a4d2432` on `release/demo-staging`

Traffic: `HOLD_1_PERCENT`

## Outcome

Report Chat now records an internal, durable S0–S8 audit lifecycle. Trace persistence is failure-safe and is not exposed in the ordinary user API. No numeric validator, prompt financial content, retrieval, selection, cache, timeout, LLM provider, frontend, Docker, dependency, embedding, or startup-warmup behavior was changed.

## Storage and access boundary

Migration `q5r6s7t8u9v0` creates:

- `report_analysis_traces`: request header, correlation identity, release/runtime fields, final status, partial flag, persistence status, and 30-day expiry.
- `report_analysis_trace_stages`: one atomic upsert row per S0–S8 stage, with started/completed timestamps, duration, state, error code, input/output hashes, and controlled JSON payload.

There is no public or ordinary-user read endpoint. Access is restricted to direct administrator/engineering database audit paths. Traces are not stored in session memory, answer cache, Redis run registry, or the public response.

The 30-day `expires_at` field establishes the retention boundary; operational deletion scheduling remains an administrator maintenance concern and is not coupled to request execution.

## Trace lifecycle

| Stage | Durable content |
|---|---|
| S0 | accepted request, request/report filters, hashes, redacted question/session identity |
| S1 | selected report/year/type/source/cache or selection failure |
| S2 | query metadata, actual provider/search mode/cache, retrieval errors/timeouts |
| S3 | retrieved chunk IDs, page/section metadata and content hashes |
| S4 | bounded pre-compaction evidence, numeric tokens and evidence hash |
| S5 | bounded post-compaction evidence, structured facts and numeric tokens |
| S6 | bounded/redacted raw structured LLM result, citations, prompt/structured hashes, timeout/failure |
| S7 | review, citation validation, leak gate, numeric validation, unsupported tokens, complete answer sentences and first-observed stage |
| S8 | bounded/redacted final answer, source IDs, errors, numeric/review state, final status |

Each stage first persists `started`, then independently persists `completed`, `failed`, `rejected`, or `skipped`. An interrupted process therefore leaves a readable started row. Repository failures set the in-process persistence-failure flag and emit a correlation log containing only request/trace IDs, operation, and exception type; business execution remains safely degraded.

## Redaction and minimization

- Authorization, Cookie, API key, client secret, access/refresh/auth token, password, and connection-string fields are replaced.
- Bearer values and PostgreSQL connection URLs embedded in strings are removed.
- Individual stored text fields are bounded to 12,000 characters; question text is bounded to 500.
- Session IDs are SHA-256 hashes.
- Evidence is bounded and accompanied by content hashes and numeric token summaries.
- Raw database chunk IDs remain backend-only and never enter the public answer through tracing.

## Tests

Command:

```text
UV_CACHE_DIR=/private/tmp/tradingagents-uv-cache uv run pytest \
  tests/test_phase6w_r3_3_trace_durability.py \
  tests/test_phase6w_r2_6_synthesis_optimization.py \
  tests/fundamental/test_phase6u_report_chain_alignment.py \
  tests/fundamental/test_phase6j_report_chat_copilot.py \
  tests/fundamental/test_phase6k_report_chat_cache_rate_memory.py \
  tests/fundamental/test_phase6l_production_hardening.py -q
```

Result: `127 passed`, `0 failed`, `0 skipped`, one existing passlib `crypt` deprecation warning; 1.75 seconds.

Covered gates include completed S0–S8 order, selection failure, retrieval/no-evidence failure, LLM timeout, citation failure, numeric token sentence capture, S8 rejection, store failure safety, secret redaction, and unchanged user contract.

Python compilation passed for all changed modules and migration. `alembic heads` reports the single head `q5r6s7t8u9v0`.

The initial host-only full offline SQL generation was blocked by an older 2026-06-24 migration importing unavailable `pgvector`; it did not reach this revision. The new revision was then correctly based on the actual prior head `p4q5r6s7t8u9`, and the controlled database upgrade completed successfully:

```text
p4q5r6s7t8u9 -> q5r6s7t8u9v0
```

## Runtime acceptance

Acceptance ran in an isolated `/tmp` application overlay inside the existing container. The production uvicorn process was not reloaded; no image was rebuilt and no deployment occurred. One initial diagnostic sample was excluded because the artifact writer could not serialize SQL datetime values. The business trace remained in the DB; the sample was not presented as accepted.

Five new queries then ran serially with unique sessions, `force_refresh=true`, and at least 10 seconds between requests:

| Type | Request ID | Result | Durable stages | Key audit result |
|---|---|---|---|---|
| Revenue | `5b100ed7` | completed / numeric valid | S0–S8 | all completed |
| Net profit | `faaae76e` | completed / numeric valid | S0–S8 | all completed |
| Cash flow | `a12d3374` | completed / numeric valid | S0–S8 | all completed |
| Profitability | `8a194f1d` | partial / LLM timeout | S0–S6 + S8 | S6 failed with `REPORT_LLM_TIMEOUT` |
| Comprehensive risk | `1f51dbf6` | partial / numeric invalid | S0–S8 | S7 failed; tokens `12`, `31` retain their full sentence and first-observed stage `S1` |

Runtime gates:

- Readable complete trace or explicit failure endpoint: 5/5.
- Numeric-invalid token context and first-observed stage: 2/2 tokens.
- `trace_persistence_failed`: 0/5.
- Secret matches in stored trace: 0/5.
- Raw chunk ID in final-answer citation context: 0/5.
- Citation metadata leak regression: 0/5.

## Release integrity

The pre-existing dirty changes remain untouched and excluded: `backend/Dockerfile`, `backend/app/main.py`, `backend/app/services/report_embedding_provider.py`, `backend/pyproject.toml`, and `backend/uv.lock`.

The currently running production-style image remains non-release-representative and contains dirty dependency/warmup work. R3.3B did not rebuild or deploy it. Runtime acceptance used a separate `/tmp` overlay only.

## Decision

The trace durability implementation and controlled acceptance pass the R3.3B implementation gate. It does not authorize traffic expansion or a numeric remediation. New traces may now support a separately owner-authorized R3.3D root-cause phase.

Traffic decision: `HOLD_1_PERCENT`.
