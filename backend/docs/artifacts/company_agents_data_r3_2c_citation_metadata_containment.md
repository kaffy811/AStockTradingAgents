# Phase 6W-R3.2C — Citation Metadata Leakage Containment

Date: 2026-08-22
Baseline HEAD: `3c30787db82bc2a6de14042bbda2895f64f1b623`
Branch: `release/demo-staging`
Traffic: `HOLD_1_PERCENT`

## 1. Workspace protection

The pre-change worktree contained the existing unstaged dependency/build changes in `backend/Dockerfile`, `backend/app/main.py`, `backend/app/services/report_embedding_provider.py`, `backend/pyproject.toml`, and `backend/uv.lock`, plus historical untracked artifacts. No file was staged. All pre-existing changes were preserved; no reset, checkout, clean, overwrite, push, or traffic change was performed.

`backend/app/main.py` startup warmup remains `UNRESOLVED — EXCLUDED FROM THIS PHASE`.

## 2. D3 evidence and containment design

Five prior complete S0-S8 samples established that raw database chunk IDs entered the LLM prompt and appeared in answer prose in four samples. This phase replaces model-visible raw IDs with request-local labels assigned in final evidence order.

- `_build_local_evidence_context()` emits `E1..En` and retains `E1 -> raw chunk` only in an in-memory request map.
- `_strip_model_visible_chunk_metadata()` removes nested `chunk_id`/`source_chunk_id` fields from the model-facing copy of structured financial data. The original structured data remains unchanged for numeric validation.
- The prompt schema now requires `citations[].evidence_id` and `claim`; it no longer asks for `source_chunks[].chunk_id`.
- `_resolve_local_citations()` rejects unknown, numeric, malformed, duplicate or empty references. Citation claim numbers must validate against the mapped evidence content plus its report year/period. Valid labels resolve back to the existing API `source_chunks` shape.
- `_citation_metadata_leaks()` scans only final answer prose, only for raw IDs retrieved in the current request, and only in citation/source/chunk/evidence/片段/编号/ID context.

Ordinary `2024`, `600519`, `1708.99`, `15.38%`, and a business value `3670` outside citation context do not trigger the gate. A detected leak records `CITATION_METADATA_LEAK`, forces non-completed status, and replaces the polluted answer with the existing evidence fallback.

## 3. Changed files

- `backend/app/agent/report_chat_copilot_agent.py`: local evidence mapping, model-visible metadata stripping, citation resolver, claim-number validation, leak gate and machine-readable audit metadata.
- `backend/app/agent/prompts/report_chat_system.md`: `citations/evidence_id/claim` contract and answer boundary.
- `backend/tests/test_phase6w_r2_6_synthesis_optimization.py`: D3 unit and indexed-fast-path integration coverage.
- `backend/tests/fundamental/test_phase6u_report_chain_alignment.py`: existing fixture migrated to the local citation contract.
- This artifact and `HKNA/update_report/update_97.md`.

No numeric-validator, canonicalization, retrieval, SQL, top_k, chunking, report selection, cache TTL/key, timeout, frontend, dependency, Dockerfile, or startup-warmup logic was changed.

## 4. Tests

| Command | Collected | Passed | Failed | Skipped | Duration |
|---|---:|---:|---:|---:|---:|
| `UV_CACHE_DIR=/private/tmp/tradingagents-uv-cache uv run pytest tests/test_phase6w_r2_6_synthesis_optimization.py -q` | 36 | 36 | 0 | 0 | 0.78 s |
| `... pytest test_phase6j_report_chat_copilot.py test_phase6w_r1_2_numeric_pipeline.py test_phase6w_r2_6_synthesis_optimization.py -q` | 86 | 86 | 0 | 0 | 1.08 s |
| `... pytest test_phase6u_report_chain_alignment.py test_phase6i_review_source_chunks_strict.py test_phase6h_ai_source_chunks.py -q` | 40 | 39 | 1 | 0 | 0.65 s; expected old-schema fixture found and migrated |
| Final six-file targeted/regression command | 127 | 127 | 0 | 0 | 1.33 s |

The only warning was the existing Python `crypt` deprecation warning from passlib.

## 5. Serial runtime evidence

All requests used `report_id=17`, year 2024, `force_refresh=true`, unique sessions, no concurrency, and at least ten seconds plus a successful DB/Redis health check between requests.

### Final-image batch

| Query | Request ID | Prompt raw ID | Citation validation | Leak gate | Numeric validation | Final status |
|---|---|---:|---|---:|---|---|
| Q1 revenue | `d5ec31f6` | No | valid; E5 -> 3670 | false | valid | completed |
| Q2 net profit | `a3c8fe8a` | No | valid; E5 -> 3670, E3 -> 3665 | false | valid | completed |
| Q4 cash flow | `4760e83a` | No | valid; E3 -> 3671, E6 -> 3677 | false | valid | completed |

Q1, Q2 and Q4 showed model-visible IDs `E1..E6`, no `chunk_id` field/table name/raw retrieved ID in the prompt, valid resolution to canonical source metadata, no raw ID in the answer, and no numeric regression. Q2 was closed in Phase R3.2C.1 with one controlled invocation and atomic stage persistence; all S0-S8 stages were captured.

Earlier pre-final batches also demonstrated raw-ID removal, but exposed two separate fail-closed behaviors: an LLM-derived number (`232.06`) was rejected by the unchanged numeric guard, and the initial citation claim validator needed the mapped report period to validate a legitimate `2024` claim. Those observations informed the final local resolver only; neither global numeric validation nor financial synthesis requirements were loosened.

## 6. Scope exclusions

- D1 compactor loss: not changed; not established as the D3 cause.
- D2 retrieval coverage: not changed; no missing-slot evidence in this phase.
- D4 financial fabrication/calculation: not changed; existing guard correctly rejected derived `232.06` in an earlier runtime sample.
- `backend/app/main.py`: warmup necessity remains unresolved.

## 7. Git and release decision

`git diff --check` passes. The D3 code/test diff is isolated, but the worktree still contains unrelated pre-existing dirty changes which must remain excluded from any future staging command.

Commit gate result: **PASS** after the controlled Q2 closure and the repeated 127-test regression. The isolated D3 files are eligible for the requested local commit. No push or traffic change is authorized.

Traffic decision: `HOLD_1_PERCENT`.
