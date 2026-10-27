# Phase 6W-R3.2 — RAG Runtime Dependency Remediation

Date: 2026-08-21  
Baseline: `3c30787db82bc2a6de14042bbda2895f64f1b623`  
Branch: `release/demo-staging`  
Decision: `HOLD_1_PERCENT`

## 1. Scope and stop condition

This phase preserved the existing R3.2 working-tree changes and did not modify retrieval, pgvector schema, chunking, report selection, numeric validation, LLM timeouts, prompts, cache TTL, Company Overview, frontend, or secrets.

The required stop condition was triggered because G7 numeric validation failed during the 10-request fresh E2E sample. No traffic expansion, commit, or push was performed.

## 2. Existing working-tree changes inspected

| File | Existing change | Status |
|---|---|---|
| `backend/pyproject.toml` | Adds `sentence-transformers>=5.7.0` | Verified |
| `backend/uv.lock` | Locks sentence-transformers and transitive dependencies | Verified by targeted tests and image build |
| `backend/Dockerfile` | Preloads `intfloat/multilingual-e5-small` | Verified; native 384 dimensions match `REPORT_EMBEDDING_DIM=384` |
| `backend/app/services/report_embedding_provider.py` | Documents E5 as compatible and BGE small as 512-dimensional | Verified |
| `backend/app/main.py` | Adds database connection-pool warmup | Pre-existing R3.2 change; preserved, not independently authorized for commit |

The originally requested `BAAI/bge-small-zh-v1.5` model produces 512 dimensions and cannot be used with the current `vector(384)` report schema without a schema migration. The existing partial work therefore selected `intfloat/multilingual-e5-small`, which loads as a native 384-dimensional CPU model.

## 3. Runtime dependency and provider evidence

Production-canary backend image:

- Image ID: `076055869c43`
- Image size: 3.5 GB
- `sentence_transformers` version: `5.7.0`
- Effective provider config: `local`
- Effective model: `intfloat/multilingual-e5-small`
- Effective dimension: `384`
- Provider class result: `provider=local`, `available=True`
- Model load: 7.298 s in an isolated process
- One-query embedding latency: 0.220 s
- Output vector dimension: 384
- Output squared norm: 1.0
- Mock provider used by this provider check: false

The backend rebuilt successfully from `pyproject.toml` and `uv.lock`; the Docker model-preload layer passed its 384-dimension assertion.

## 4. Important architecture finding

The production report-chat `indexed_fast_path` does not use `LocalSentenceTransformerProvider`. It calls `_query_indexed_report_db_evidence()` and performs bounded lexical SQL retrieval against `company_v2_report_rag_chunks`.

Therefore the R3.1 statement “missing sentence-transformers caused indexed-fast-path pgvector timeouts” is not supported by the current source path. Installing sentence-transformers is valid dependency remediation for the legacy `report_chunks` vector path, but it cannot by itself explain the measured improvement of the Company V2 indexed lexical path.

No retrieval algorithm was changed in this phase.

## 5. Tests and build

| Command | Result |
|---|---|
| `UV_CACHE_DIR=/private/tmp/tradingagents-uv-cache uv run pytest tests/fundamental/test_phase6g1_embedding_dim_migration.py tests/fundamental/test_phase6g_local_embedding_and_quality.py tests/test_phase6w_r2_6_synthesis_optimization.py -q` | 40 passed, 0 failed, 0 skipped; 0.86 s |
| `docker compose build backend` | PASS; image `076055869c43` |
| `docker compose up -d backend` | PASS |
| `/api/v1/health` | `status=ok`, `env=production`, DB/Redis OK, report RAG enabled |

## 6. Ten-query retrieval-only benchmark

Ten distinct 600519.SH / report_id=17 questions were executed directly through the real indexed database evidence function with an 8-second bound.

- Count: 10
- Timeouts: 0
- Chunks: 6 for every query
- Provider/path: `indexed_db_lexical`
- P50: 485.9 ms
- Maximum / observed P95 sample value: 5101.9 ms on the first query
- Subsequent range: 416.6–667.8 ms

Fresh RAG timeout gate: PASS for the retrieval-only population.

## 7. Ten-query full E2E benchmark

Ten unique API questions were executed with explicit report_id=17/year=2024 and distinct sessions.

- HTTP success: 10/10
- RAG timeouts: 0/10
- Retrieval latency: 0.661–1.295 s
- Overall latency: 10.2–82.9 s
- `status=completed`: 1/10
- `partial_success`: 9/10
- `numeric_validation.valid=true`: 1/10
- Wrong report year: 0

The nine safe degradations contained unsupported claims such as `12`, `31`, `3670`, `3676`, `15%`, ratio decimals, and other LLM-generated operational/financial tokens not present in the selected evidence. The guard behaved safely and did not publish these runs as completed.

## 8. Gate decision

| Gate | Result |
|---|---|
| Dependency installed and image reproducible | PASS |
| Local provider loadable | PASS |
| Mock fallback in provider verification | PASS (not used) |
| 10/10 retrieval-only fresh RAG timeout=0 | PASS |
| Full E2E fresh RAG timeout=0 | PASS |
| G7 numeric validation regression | FAIL (1/10 valid) |
| 30-request observation | NOT RUN — stop condition triggered |
| Commit | NOT CREATED |
| Traffic expansion | NOT AUTHORIZED / NOT PERFORMED |

Final decision: `HOLD_1_PERCENT`.

## 9. Git state

Five tracked files remain modified and unstaged. Existing untracked historical artifacts remain untouched. No commit and no push were made.

