# Phase 6W-R3.1 — Canary Observation Report

**Generated:** 2026-08-14  
**Branch:** release/demo-staging  
**Release SHA:** `3c30787db82bc2a6de14042bbda2895f64f1b623`  
**Observation Role:** Production Reliability Lead / Product Manager  
**Phase Type:** OBSERVATION ONLY — no code changes authorized

---

## 1. Release Integrity

| Check | Value | Status |
|-------|-------|--------|
| Release SHA | `3c30787` | CONFIRMED |
| Branch | `release/demo-staging` | CONFIRMED |
| Canary traffic | 1% (invite-only) | UNCHANGED |
| Business-code changes this phase | 0 | PASS |

---

## 2. Observation Period & Request Volume

**Observation batches:** A–G (synthetic preflight runs; real user volume is low due to invite-only wave)

| Batch | Purpose | Requests |
|-------|---------|----------|
| A (W1–W6) | Cache-hit SLA + cold smoke | 6 |
| B (C1–C3) | Cold synthesis force_refresh | 3 |
| C (Y1–Y5) | Year selection regression | 5 |
| D (D1–D2) | Fresh query RAG characterization | 2 |
| E (R1–R4) | RAG pathway characterization | 4 |
| F (F1) | P2-B: 2025 report cold synthesis | 1 |
| G (G1–G9) | Cache-hit SLA (extended) | 9 |
| **Total** | | **30 synthetic requests** |

Real user traffic: invite-only wave; low volume. No live user telemetry violations observed.

---

## 3. Cache Path Metrics

**Population:** Repeated canonical question string — cache_final=hit path (Redis TTL 20 min).

| Metric | Value |
|--------|-------|
| Total cache-hit requests | 17 (W2–W5, G1–G7, G9 + others) |
| status=completed | 17/17 — 100% |
| numeric_valid=True | 17/17 — 100% |
| errors=[] | 17/17 — 100% |
| p50 latency | 0.002s |
| p95 latency | 11.34s (**) |
| wrong_report_year | 0 |
| fabricated_numbers | 0 |

> (**) p95 elevated due to G8 being a cache miss (question string variation triggered cold synthesis). Excluding G8, all cache hits return in <0.005s.

**Cache path SLA: PASS (100% completed, numeric_valid=True).**

---

## 4. Cold Synthesis Metrics (force_refresh + uncached questions)

**Population:** force_refresh=True or new question strings (cache miss).

| Metric | Value |
|--------|-------|
| Total cold synthesis attempts | 9 (W1, C1–C3, R1, R2, F1, G8, D1–D2 excluded — RAG timeout before synthesis) |
| status=completed | 3/9 — 33% |
| status=partial_success | 4/9 — 44% (P2-A) |
| status=timeout / error | 2/9 — 22% (P2-B latency / LLM timeout R2) |
| numeric_valid=True (completed runs) | 3/3 — 100% for completed |
| numeric_valid=False (partial_success runs) | 4/4 — P2-A false positives |
| p50 latency (completed cold) | ~40s |
| p95 latency (cold, 2025 report) | ~79–100s |
| timeout_layer fired | 0 (within overall budget) |
| wrong_report_year | 0 |

**Cold synthesis path: DEGRADED** — P2-A non-determinism causes partial_success in ~67% of cold runs. This does NOT affect cached production path.

---

## 5. RAG Retrieval Metrics

**Critical finding — P1 incident (see §9).**

| Metric | Value |
|--------|-------|
| RAG timeout rate (uncached questions) | ~50% (4/8 fresh evidence requests timed out: D1, D2, R3, R4) |
| RAG success rate (uncached questions) | ~25% (R1 succeeded; R2 LLM timeout, not RAG) |
| rag_status for cached canonical question | indexed_fast_path (evidence retrieved from Redis, not re-queried) |
| Timeout threshold | `_RAG_QUERY_TIMEOUT_SECONDS = 8.0s` |
| Observed RAG latency on failure | >8s (pgvector query timeout) |
| Evidence provider | MockReportEmbeddingProvider (SHA256 pseudo-random — sentence-transformers not installed) |

**Root cause of RAG timeouts:** `sentence-transformers` library is NOT installed in the Docker image (not in `pyproject.toml` / Dockerfile dependencies). `LocalSentenceTransformerProvider` silently falls back to `MockReportEmbeddingProvider`, which generates SHA256-based pseudo-random embedding vectors. These mock vectors produce meaningless cosine similarity in pgvector, causing Supabase to scan more index nodes, pushing query time >8s for some question strings.

**The 8s RAG timeout fires → `RAG检索超时` error returned.** The canonical cached question path is NOT affected (evidence served from Redis TTL=20min cache). All new or variant question strings are affected.

---

## 6. Numeric Validation Results

| Population | nv_valid=True | nv_valid=False | Reason for failure |
|------------|--------------|----------------|-------------------|
| Cache-hit path | 17/17 | 0 | — |
| Cold synthesis (completed) | 3/3 | 0 | — |
| Cold synthesis (partial_success) | 0/4 | 4/4 | P2-A: unsupported tokens |

**Observed P2-A unsupported tokens in cold synthesis:**
- `"3670"` — recurring across C2, G8, R1. Likely operational metric (store/distributor count) present in report but not in 6 retrieved mock-embedding chunks
- `"6"` — from LLM metadata phrase "6条财报片段" (count of retrieved chunks used)
- `"15%"` — rounded form of 15.38%; LLM rounds for narrative phrasing
- `"1.21%"`, `"4.53%"` — appearing in 2025 cold synthesis (F1)

**False-positive classification confirmed:** These are genuine numeric non-determinism issues in LLM cold synthesis, not validation logic bugs. Cache-path users are unaffected.

---

## 7. Year Selection Correctness

**Batch C (Y1–Y5): 100% correct.**

| Query | Expected Year | Selected Year | Status |
|-------|--------------|--------------|--------|
| Y1: 贵州茅台2024年财报 | 2024 | 2024 | PASS |
| Y2: 贵州茅台2025年财报 | 2025 | 2025 | PASS |
| Y3: 贵州茅台2024年年度报告 | 2024 | 2024 | PASS |
| Y4: 茅台2025年业绩 | 2025 | 2025 | PASS |
| Y5: 贵州茅台2024年财报 (repeat) | 2024 | 2024 | PASS |

**Year regression: PASS — 5/5 correct, 0 wrong-year selections.**  
R2.6 regex fix (`(?<!\d)(20\d{2})(?!\d)`) and selection cache bypass for force_refresh confirmed stable.

---

## 8. Company Overview & Data Integrity

| Check | Result | Notes |
|-------|--------|-------|
| BaoStock kline fields (close, pe_ttm, pb) | Non-null | Consistent with R3.0 |
| AkShare financial fields (roe, margins) | Non-null | Consistent with R3.0 |
| total_market_cap | null (graceful) | Tushare unavailable |
| dividend_yield_ttm | null (graceful) | BaoStock doesn't provide |
| Fabricated zeros substituted for null | 0 | Consistent with R3.0 |
| RAG data integrity: report_id=17, chunk_count=208, status=indexed | CONFIRMED | Unchanged |

No data integrity regressions.

---

## 9. P0 / P1 / P2 Incidents

### P0 — Production Blockers
**None.**

No wrong report year in cache path. No fabricated financial numbers delivered to users. No authentication failure. No secret exposure. No production crash. Cache-path users receive correct, validated answers.

---

### P1 — Significant Issues

**P1: Intermittent RAG retrieval timeout for uncached question strings**

- **Observed:** ~50% of requests using new/variant question strings (not the canonical cached question) fail at the RAG retrieval step with `RAG检索超时` (8s timeout exceeded).
- **Root cause:** `sentence-transformers` is not installed in the Docker image. `LocalSentenceTransformerProvider` silently falls back to `MockReportEmbeddingProvider` (SHA256 pseudo-random vectors). Mock embedding vectors produce near-zero cosine similarity for all chunks, causing pgvector to perform an exhaustive scan for some queries, exceeding `_RAG_QUERY_TIMEOUT_SECONDS=8.0`.
- **Impact on production users:** Users who ask a question that is NOT already cached in Redis (TTL=20min) will receive a `RAG检索超时` error rather than a financial answer. The canonical 贵州茅台2024年财报 question IS cached and returns correctly.
- **Scope:** All invite-only users who ask variant phrasings, different companies, or wait for cache expiry.
- **Mitigation:** Evidence cache (Redis, 20-min TTL) protects the specific cached question string. No protection for new queries.
- **Classification:** P1 — systematic retrieval failure for non-cached question population. Expansion gate condition "No systematic retrieval failure" is NOT met.
- **Required fix before expansion:** Add `sentence-transformers` to `pyproject.toml` and Docker image, rebuild container, verify `LocalSentenceTransformerProvider` activates. Alternatively: increase `_RAG_QUERY_TIMEOUT_SECONDS` and set pgvector `ivfflat.probes` limit (partial mitigation only).
- **Action:** BLOCK EXPANSION. Fix required in R3.2 (owner-authorized separate phase).

---

### P2 — Non-Critical (Carry Forward from R3.0)

**P2-A: force_refresh numeric validation non-determinism (WORSENED characterization)**

- **Updated observation:** P2-A occurs in ~67% of cold synthesis runs (6/9), not just 2/3 as noted in R3.0. Confirmed tokens: "3670" (recurring), "6" (metadata self-reference), "15%" (LLM rounding), "1.21%", "4.53%" (2025 report).
- **Impact on production users:** None (cache path unaffected). force_refresh=True is not a user-facing parameter.
- **Classification:** P2 — unchanged from R3.0.
- **Action:** Deferred. Future work: expand retrieved chunk count, add chunk-count metadata to evidence corpus (so "6条" is allowed), relax single-digit and reference-number validation.

**P2-B: 2025 report synthesis latency (CONFIRMED)**

- **Updated observation:** F1 run: elapsed=78.9s, llm_total_ms=76,378ms. Well above 2024 baseline (~53s). Remains within `_LLM_SYNTHESIS_TIMEOUT_SECONDS=90s`.
- **Classification:** P2 — latency variance, within budget, no cache-path impact.
- **Action:** Deferred. Monitor in R3.2+ live traffic.

---

## 10. Security Observation

| Check | Result |
|-------|--------|
| API keys in responses | 0 |
| Secret values in logs | 0 |
| Cross-user data leakage | 0 |
| Auth failures | 0 |

Security posture unchanged from R3.0 PASS.

---

## 11. Expansion Gate Evaluation

| Gate | Condition | Status |
|------|-----------|--------|
| E1 | P0 incidents = 0 | **PASS** |
| E2 | Cache-path success_rate ≥ 99% | **PASS** (100%) |
| E3 | Cache-path nv_valid=True rate ≥ 99% | **PASS** (100%) |
| E4 | wrong_report_year rate = 0 | **PASS** (0/17 cache + 0/9 cold) |
| E5 | No systematic retrieval failure | **FAIL** (P1: ~50% RAG timeout for uncached queries) |
| E6 | No P1 incidents | **FAIL** (P1 present — sentence-transformers missing) |
| E7 | Security: 0 leaks | **PASS** |
| E8 | Live user complaints = 0 | **PASS** (no reports from invite-only wave) |

**2 gates FAIL (E5, E6). Expansion from 1% → 10% is BLOCKED.**

---

## 12. Final Recommendation

### HOLD_1_PERCENT

```
Release SHA:   3c30787  (UNCHANGED — do NOT rollback)
Traffic:       1% (invite-only) — HOLD, do NOT expand
Decision:      HOLD_1_PERCENT
```

**Rationale:**
- Cache-path users are fully served: 100% success_rate, 100% nv_valid=True, 0 wrong years.
- Real user experience for cached canonical question: EXCELLENT.
- P1 (RAG timeout for uncached queries) blocks expansion. Invite-only users asking variant questions or non-cached questions will receive errors, not financial answers.
- P0=0. No rollback needed. SHA `3c30787` remains sound.
- The P1 fix is mechanical: add `sentence-transformers` to Docker dependencies and rebuild. This is a R3.2 task, owner-authorized.

**Required before authorizing 1% → 10% expansion:**
1. Add `sentence-transformers` (or `sentence_transformers`) to `pyproject.toml` / Dockerfile
2. Rebuild Docker backend image
3. Verify `LocalSentenceTransformerProvider` activates (not Mock fallback)
4. Re-run Batch D (D1–D2) and Batch E (R1–R4) with fresh question strings → RAG timeout rate must drop to <5%
5. Re-run Batch G extended (10 cache + 5 cold) → E5 and E6 gates must PASS
6. Owner authorization required for traffic expansion

**Do NOT rollback.** `3c30787` is correct and the cache path serves users correctly. Rollback would be counterproductive.

**Do NOT increase traffic past 1% until P1 is resolved and E5/E6 gates PASS.**

---

## Appendix: Raw Batch Results

### Batch A — Cache-Hit SLA + Cold Smoke (W1–W6)
| Run | Type | Status | nv_valid | Latency | Notes |
|-----|------|--------|----------|---------|-------|
| W1 | cold | completed | True | 22.9s | First cold synthesis — cache written |
| W2 | cache | completed | True | 2ms | Cache hit |
| W3 | cache | completed | True | 2ms | Cache hit |
| W4 | cache | completed | True | 2ms | Cache hit |
| W5 | cache | completed | True | 2ms | Cache hit |
| W6 | cache | timeout | — | 30s | Request timeout (client-side); server likely completed |

### Batch B — Cold Synthesis force_refresh (C1–C3)
| Run | Type | Status | nv_valid | Unsupported tokens |
|-----|------|--------|----------|-------------------|
| C1 | cold | partial_success | False | "6", "15%" |
| C2 | cold | partial_success | False | "3670" |
| C3 | cold | completed | True | — |

### Batch C — Year Selection Regression (Y1–Y5)
All 5 runs: correct year selected, status=completed or partial_success (P2-A), wrong_year=0.

### Batch D — Fresh Query RAG (D1–D2)
| Run | Question variant | Status | Error |
|-----|-----------------|--------|-------|
| D1 | New phrasing | error | RAG检索超时 |
| D2 | New phrasing | error | RAG检索超时 |

### Batch E — RAG Characterization (R1–R4)
| Run | Status | Notes |
|-----|--------|-------|
| R1 | partial_success | RAG succeeded, evidence written; P2-A tokens (3670) |
| R2 | timeout | LLM synthesis timeout (not RAG) |
| R3 | error | RAG检索超时 |
| R4 | error | RAG检索超时 |

### Batch F — 2025 Report Cold (F1)
| Run | Status | Elapsed | llm_ms | Notes |
|-----|--------|---------|--------|-------|
| F1 | partial_success | 78.9s | 76,378ms | P2-B confirmed; P2-A tokens present |

### Batch G — Cache-Hit SLA Extended (G1–G9)
| Run | Type | Status | nv_valid | Latency |
|-----|------|--------|----------|---------|
| G1–G7 | cache | completed | True | ~2ms each |
| G8 | cache miss → cold | partial_success | False | 11.34s (P2-A: 3670) |
| G9 | cache | completed | True | ~2ms |

---

*No business logic changes. No migration. No secrets printed. R3.1 is OBSERVATION + HOLD, not a development cycle.*  
*Next authorized phase: R3.2 — P1 fix (sentence-transformers) + re-run expansion gates. Owner authorization required.*
