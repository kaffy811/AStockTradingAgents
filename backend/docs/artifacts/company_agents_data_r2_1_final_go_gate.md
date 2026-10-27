# Phase 6W-R2.1 — Final Go Gate Matrix

**Generated:** 2026-08-12  
**Branch:** release/demo-staging  
**HEAD:** a542bc1

---

## Step Execution Summary

| Step | Description | Status | Notes |
|------|-------------|--------|-------|
| STEP 0 | Safety check (no secrets, audit-only) | **COMPLETE** | No violations |
| STEP 1 | Supabase DB recovery | **BLOCKED** | Owner action required — project paused |
| STEP 2 | Embedding provider config | **COMPLETE** | `REPORT_EMBEDDING_PROVIDER=local` added to root `.env`; sentence-transformers absent is NOT a P0 blocker |
| STEP 3 | Container restart | **BLOCKED** | Depends on STEP 1 |
| STEP 4 | Real report ingestion (600519.SH 2024) | **BLOCKED** | Depends on STEP 1 |
| STEP 5 | E2E financial query | **BLOCKED** | Depends on STEP 4 |
| STEP 6 | Company Overview live verification | **BLOCKED** | Depends on STEP 1 + container restart |
| STEP 7 | Cache isolation verification | **BLOCKED** | Depends on STEP 5 |

---

## 14-Gate Matrix

| Gate | Description | Status | Evidence |
|------|-------------|--------|---------|
| **G1** | Production DB reachable (asyncpg SELECT 1) | **BLOCKED** | Supabase project paused — ENOTFOUND tenant. DNS for project subdomain fails. Owner must resume at supabase.com/dashboard. |
| **G2** | Alembic revision == p4q5r6s7t8u9 | **BLOCKED** | Cannot verify — DB unreachable. Depends on G1. |
| **G3** | DeepSeek HTTP 200 OK | **PASS** | R2.0 verified: HTTP 200, model=deepseek-v4-flash, latency=669ms. |
| **G4** | RAG enabled (ENABLE_REPORT_RAG=true) | **PASS** | Added to root .env in R2.0. Verified via grep. |
| **G5** | Real 600519.SH 2024 report indexed (chunk_count>0) | **BLOCKED** | Depends on G1 + real ingestion. No synthetic data permitted. |
| **G6** | Real financial query: status=completed, rag_status=indexed_fast_path | **BLOCKED** | Depends on G5. |
| **G7** | Numeric validation: valid=true, evidence_available=true | **BLOCKED** | Depends on G6. |
| **G8** | Provider chain: BaoStock → price/PE/PB/ROE for 600519 | **PASS** | R2.0 verified: close=1346.50, peTTM=20.35, pbMRQ=6.21, roeAvg=38.43%. |
| **G9** | Company Overview 4 of 6 fields not null (price/PE/PB/ROE) | **PASS (code+provider)** | BaoStock provides all 4. total_mv and dv_ttm graceful "—". Live test requires container restart after G1. |
| **G10** | Cache isolation: locator key ≠ analysis key | **PASS (code)** | Key format `rc:v2:{intent_type}:{ts_code}:...` — structurally isolated by intent_type segment. Live test requires G6. |
| **G11** | Frontend VITE_API_BASE=/api/v1, no localhost in bundle | **PASS** | Bundle `index-BxIiHZ4a.js`: 0× localhost, 3× "/api/v1". |
| **G12** | A股 browser color: pct-up=red, pct-dn=green | **BROWSER_EVIDENCE_PASS** | Playwright Chromium headless: `.pct-up[data-v-*]{color:var(--danger)}` verified. `--danger`=rgb(229,72,93) red, `--success`=rgb(22,160,133) green. |
| **G13** | Badge semantics: partial_success displays in danger (red) | **PASS** | Playwright: `.badge-failed{color:var(--danger)}`. `badgeClass('partial_success')` → `'badge-failed'`. |
| **G14** | No secrets in responses, artifacts, or terminal output | **PASS** | All R1.7→R2.1 artifacts: 0 occurrences of full token values. Masking: PRESENT/len/prefix only. |

---

## Embedding Provider Gap (R2.0 Finding — Now Resolved)

| Variable | Root .env | Config Default | Status |
|----------|-----------|----------------|--------|
| `REPORT_EMBEDDING_PROVIDER` | `local` | `mock` | **ADDED in R2.1** |
| `REPORT_EMBEDDING_MODEL` | `BAAI/bge-small-zh-v1.5` | `None` | **ADDED in R2.1** |

`sentence-transformers` not installed → embedding step skipped → `rag_status="chunked"` → keyword retrieval path active.  
**This is NOT a P0 blocker.** Keyword RAG works without vector embeddings.

---

## Gate Summary

| Status | Gates | Count |
|--------|-------|-------|
| PASS | G3, G4, G8, G9*, G10*, G11, G12, G13, G14 | 9 |
| BLOCKED | G1, G2, G5, G6, G7 | 5 |

*G9, G10: pass at code/provider level; need live container verification after G1.

**P0 BLOCKED gates: 5** — all depend on single owner action (Supabase resume).

---

## Decision

### **NO-GO**

**Primary reason:** Production database paused. 5 gates BLOCKED.

**No code defects identified.** All blocked gates are environment or data blockers.

**Root .env is complete.** All 7 feature flags now set (DATA_MODE, ENABLE_BAOSTOCK, ENABLE_AKSHARE, ENABLE_REPORT_PDF, ENABLE_REPORT_RAG, REPORT_EMBEDDING_PROVIDER, REPORT_EMBEDDING_MODEL).

---

## Single Remaining Owner Action

```
Resume Supabase project:
  URL: https://supabase.com/dashboard
  Project ref: qvpdtnazhxbfifrjdfdf
  Action: Click "Resume project" → wait ~60s
  Verify: curl -s https://qvpdtnazhxbfifrjdfdf.supabase.co/rest/v1/
          → expect HTTP 401 (not SSL EOF or DNS failure)
```

---

## Engineer Actions After Owner Resumes Supabase

```bash
# 1. Verify DB connectivity
python3 -c "
import asyncio, asyncpg
async def test():
    conn = await asyncpg.connect('<DATABASE_URL>', ssl='require', timeout=12)
    r = await conn.fetchval('SELECT 1')
    print(f'SELECT 1 = {r}')
    await conn.close()
asyncio.run(test())
"
# Expected: SELECT 1 = 1

# 2. Check Alembic schema
cd backend
uv run alembic current
uv run alembic heads
# Expected HEAD: p4q5r6s7t8u9
# If delta: await owner authorization, then: uv run alembic upgrade head

# 3. Restart containers (no rebuild needed — .env flags injected at start)
docker compose up -d

# 4. Ingest real 600519.SH 2024 annual report from CNINFO
POST /api/v1/admin/reports/ingest
{
  "ts_code": "600519.SH",
  "report_year": 2024,
  "report_type": "annual",
  "source_url": "<CNINFO official PDF URL>"
}
# PROHIBITED: synthetic chunks, manually typed text, staging data

# 5. Verify ingestion
GET /api/v1/admin/reports/status?ts_code=600519.SH
# Expected: parsed=true, rag_status="chunked" or "indexed", chunk_count > 0

# 6. E2E financial query
POST /api/v1/stock/600519/report-chat
{"question": "贵州茅台2024年财报表现如何？营收和利润增长情况怎么样？", "force_refresh": true}
# Expected: status=completed, rag_status=indexed_fast_path, chunks_retrieved>=1,
#           numeric_validation.valid=true, errors=[]

# 7. Locator query (cache isolation)
POST /api/v1/stock/600519/report-chat
{"question": "请给我贵州茅台最新年报官方PDF"}
# Expected: rag_status=not_required, intent_type=locator

# 8. Company Overview
GET /api/v1/stocks/CN/600519/profile
# Expected: price/pe_ttm/pb/roe not null; total_mv and dv_ttm null is acceptable

# 9. Re-run gate matrix → issue GO
```

---

## Completed This Phase

- ✅ STEP 0: Safety check — no secrets leaked, no destructive operations
- ✅ STEP 2: `REPORT_EMBEDDING_PROVIDER=local` + `REPORT_EMBEDDING_MODEL=BAAI/bge-small-zh-v1.5` added to root `.env`
- ✅ Embedding gap analysis: sentence-transformers absent is NOT P0 — keyword retrieval is independent
- ✅ G12 (color convention): BROWSER_EVIDENCE_PASS (Playwright)
- ✅ G13 (badge semantics): PASS
- ✅ G14 (secret isolation): PASS across all R1.7→R2.1 artifacts

---

*No production deploy was performed. No application code was modified. All changes: root .env additions + artifacts.*
