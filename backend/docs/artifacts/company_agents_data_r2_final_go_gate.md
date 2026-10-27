# Phase 6W-R2.0 — Final Go Gate Matrix

**Generated:** 2026-08-12  
**Branch:** release/demo-staging  
**HEAD:** a542bc1

---

## Gate Matrix

| Gate | Description | Status | Evidence | Blocker |
|------|-------------|--------|---------|---------|
| **G1** | Production DB reachable (asyncpg SELECT 1) | **BLOCKED** | Supabase project paused — ENOTFOUND tenant. DNS for project subdomain fails. | P0 — Owner: Resume Supabase |
| **G2** | Alembic revision == p4q5r6s7t8u9 (HEAD) | **BLOCKED** | Cannot run `alembic current` — DB unreachable | P0 — Depends on G1 |
| **G3** | DeepSeek HTTP 200 OK | **PASS** | HTTP 200, model=deepseek-v4-flash, latency=669ms, key sk-8*** len=35 | — |
| **G4** | RAG enabled (ENABLE_REPORT_RAG=true) | **PASS** | Added to root .env; config default was false; now `true`. Verified via grep. | — |
| **G5** | Real 600519.SH 2024 report indexed (chunk_count>0) | **BLOCKED** | DB paused; no real PDF indexed in production DB | P0 — Depends on G1 + real ingestion |
| **G6** | Real financial query: status=completed, rag_status=indexed_fast_path | **BLOCKED** | Depends on G5 | P0 — Depends on G5 |
| **G7** | Numeric validation: valid=true, evidence_available=true | **BLOCKED** | Depends on G6 | P0 — Depends on G6 |
| **G8** | Provider chain: BaoStock → price/PE/PB/ROE for 600519 | **PASS** | BaoStock test: close=1346.50, peTTM=20.35, pbMRQ=6.21, roeAvg=0.3843 (38.43%). DATA_MODE=free in root .env. | — |
| **G9** | Company Overview 4 of 6 fields not null (price/PE/PB/ROE) | **PASS (code+provider)** | BaoStock provides all 4. total_mv and dv_ttm null = accepted graceful degradation. Cannot test live until DB+containers restarted. | Conditional — verify post-restart |
| **G10** | Cache isolation: locator key ≠ analysis key | **PASS (code)** | Key format: `rc:v2:{intent_type}:{ts_code}:...` — different intent_type segment. Staging R1.6: locator returned rag_status=not_required separately. Cannot live-test until G6 is unblocked. | Conditional — verify post-G6 |
| **G11** | Frontend VITE_API_BASE=/api/v1, no localhost in bundle | **PASS** | Bundle `index-BxIiHZ4a.js`: 0× localhost, 3× "/api/v1". `frontend/.env.production` VITE_API_BASE=/api/v1. docker-compose build arg /api/v1. | — |
| **G12** | A股 browser color: pct-up=red, pct-dn=green | **BROWSER_EVIDENCE_PASS** | Playwright Chromium headless: `.pct-up[data-v-*]{color:var(--danger)}` verified in stylesheet. `--danger` resolves to `rgb(229,72,93)` (red). `--success` resolves to `rgb(22,160,133)` (green). | — |
| **G13** | Badge semantics: partial_success displays in danger (red), not success | **PASS** | Playwright: `.badge-failed { background: rgba(245,85,74,0.12); color: var(--danger) }`. `badgeClass('partial_success')` → `'badge-failed'` confirmed in source. | — |
| **G14** | No secrets in responses, artifacts, or terminal output | **PASS** | All R1.7, R1.8, R2.0 artifact files: 0 occurrences of full token values. Outputs use PRESENT/len/prefix masking only. | — |

---

## Additional Identified Gap (Not in Original 14-gate spec)

| Item | Finding | Impact |
|------|---------|--------|
| `REPORT_EMBEDDING_PROVIDER` | ABSENT from root .env → default=`mock` | RAG similarity search uses random vectors → retrieval unreliable. Must set to `local` or `openai` before G6 can pass. |

**Action required before G6:** Add `REPORT_EMBEDDING_PROVIDER=local` and `REPORT_EMBEDDING_MODEL=BAAI/bge-small-zh-v1.5` to root `.env`, OR confirm BM25-only keyword fallback is acceptable.

---

## Gate Summary

| Status | Gates | Count |
|--------|-------|-------|
| PASS | G3, G4, G8, G9*, G10*, G11, G12, G13, G14 | 9 |
| BLOCKED | G1, G2, G5, G6, G7 | 5 |
| BROWSER_EVIDENCE_PASS | G12 | (included in PASS above) |

*G9, G10: pass at code/provider level; need live production verification after G1 resolved.

**P0 BLOCKED gates: 5** (G1, G2, G5, G6, G7 — all depend on Supabase resume)

---

## Decision

### **NO-GO**

**Primary reason:** Production database is paused. 5 gates BLOCKED.

**No code defects identified.** Every blocked gate is environment or data.

---

## Minimum Actions to Reach GO

### Owner Actions (Cannot Be Delegated)

```
1. Resume Supabase project at https://supabase.com/dashboard
   → project ref: qvpdtnazhxbfifrjdfdf
   → Verify: asyncpg SELECT 1 = 1

2. Root .env updates already applied (DATA_MODE, ENABLE_BAOSTOCK, ENABLE_AKSHARE, 
   ENABLE_REPORT_PDF, ENABLE_REPORT_RAG). ✅ DONE this phase.

3. Decide on embedding provider:
   → Add REPORT_EMBEDDING_PROVIDER=local to root .env
   → Or confirm BM25-only fallback acceptable
```

### Engineer Actions (After Owner Step 1)

```
4. Run: alembic current → verify == p4q5r6s7t8u9
   If delta: await owner authorization, then: alembic upgrade head

5. Ingest REAL 600519.SH 2024 annual report from CNINFO (no synthetic data)
   → Verify report_documents + company_v2_rag_documents + chunks populated

6. Restart production containers (picks up new .env flags, no rebuild needed):
   docker compose up -d

7. Run E2E query: "贵州茅台2024年财报表现如何？"
   → Verify status=completed, chunks_retrieved>0, numeric_validation.valid=true

8. Run locator query: "请给我贵州茅台最新年报官方PDF"
   → Verify rag_status=not_required, intent_type=locator

9. Verify Company Overview live: GET /api/v1/stocks/CN/600519/profile
   → Confirm price, pe_ttm, pb, roe not null; total_mv and dv_ttm null is acceptable

10. Re-run gate matrix → issue GO
```

### Completed This Phase (No Further Action)

- ✅ Root .env: 5 feature flags added
- ✅ VITE_API_BASE: /api/v1 in production bundle  
- ✅ DeepSeek: HTTP 200 PASS
- ✅ BaoStock: 4 fields PASS
- ✅ G12 Browser color: BROWSER_EVIDENCE_PASS
- ✅ G13 Badge semantics: PASS
- ✅ G14 Secret isolation: PASS

---

*No production deploy was performed. No code was modified. All changes: root .env append + artifacts.*
