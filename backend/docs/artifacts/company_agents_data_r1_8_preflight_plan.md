# Phase 6W-R1.8 — Production Preflight Plan

**Generated:** 2026-08-12  
**Branch:** release/demo-staging  
**HEAD:** a542bc1  
**Status:** PLAN — execution requires project owner authorization

---

## Executive Summary

Phase 6W-R1.7 identified 4 P0 blockers. This plan documents the exact remediation steps, execution order, and verification criteria to advance from NO-GO to GO status.

**Current state:** NO-GO (4 P0 blockers)  
**Target state:** GO (26/26 gates PASS)  
**Owner actions required:** 2 (Supabase resume, root .env update)  
**Code changes required:** 0 (all issues are config/data, not code)

---

## P0 Blocker Summary

| # | Blocker | Type | Owner Action? |
|---|---------|------|--------------|
| P0-1 | Supabase DB paused — asyncpg ENOTFOUND tenant | ENVIRONMENT | **YES** |
| P0-2 | `ENABLE_REPORT_RAG` missing from root `.env` | CONFIGURATION | **YES** |
| P0-3 | `DATA_MODE`, `ENABLE_BAOSTOCK`, `ENABLE_AKSHARE`, `ENABLE_REPORT_PDF` missing | CONFIGURATION | **YES** |
| P0-4 | Tushare all endpoints permission denied | BILLING DECISION | **YES** (strategy choice: free mode) |

---

## Execution Order

### PHASE A — Owner Actions (Prerequisite, Cannot Be Delegated)

#### A1: Resume Supabase Project

**Owner must:**
1. Log into https://supabase.com/dashboard
2. Select project `qvpdtnazhxbfifrjdfdf`
3. Click "Resume project" (if paused)
4. Wait for project to become active
5. Verify: `curl -I https://qvpdtnazhxbfifrjdfdf.supabase.co/rest/v1/` returns HTTP 200 or 401 (not SSL EOF or DNS failure)

**Evidence of success:**
- `qvpdtnazhxbfifrjdfdf.supabase.co` DNS resolves
- asyncpg `SELECT 1` returns `1`
- Status: "ACTIVE" in Supabase dashboard

**Do NOT proceed to A2 until A1 is VERIFIED.**

---

#### A2: Patch Root `.env`

**Owner must ADD these lines to root `.env`** (append, do not remove existing lines):

```bash
# Phase 6W-R1.8: Production feature flags
DATA_MODE=free
ENABLE_BAOSTOCK=true
ENABLE_AKSHARE=true
ENABLE_REPORT_PDF=true
ENABLE_REPORT_RAG=true
```

**Preservation policy:** All existing variables UNCHANGED. Only additions.

**Also review:**
- `CORS_ORIGINS`: Current value contains temporary Cloudflare tunnel URL.
  Replace with production domain before public launch.
  Do NOT block on this for 1% canary (auth currently invite-only).

**Verification after patch:**
- `grep "ENABLE_REPORT_RAG" .env` → `ENABLE_REPORT_RAG=true`
- `grep "DATA_MODE" .env` → `DATA_MODE=free`
- `grep "ENABLE_BAOSTOCK" .env` → `ENABLE_BAOSTOCK=true`

---

### PHASE B — Engineer Actions (After A1 + A2 Complete)

#### B1: Verify DB Connectivity

```bash
# From project root
python3 -c "
import asyncio, asyncpg
async def test():
    conn = await asyncpg.connect(dsn, ssl='require', timeout=15)
    r = await conn.fetchval('SELECT 1')
    print(f'SELECT 1 = {r}')
    await conn.close()
asyncio.run(test())
"
```

Expected: `SELECT 1 = 1`

---

#### B2: Alembic Schema Audit (Read-Only)

```bash
cd backend
uv run alembic current   # shows current revision on production DB
uv run alembic heads     # shows repository expected HEAD: p4q5r6s7t8u9
```

**If current ≠ p4q5r6s7t8u9:** Generate migration_plan.md, DO NOT auto-migrate.  
**If current == p4q5r6s7t8u9:** PASS, proceed.

---

#### B3: Verify Required Tables Exist

```sql
SELECT table_name FROM information_schema.tables 
WHERE table_schema = 'public' 
AND table_name IN (
  'report_documents',
  'company_v2_report_rag_documents',
  'company_v2_report_rag_chunks',
  'chat_sessions',
  'chat_messages',
  'users',
  'alembic_version'
);
```

Expected: 7 rows returned.

---

#### B4: Run Production Alembic Migration (If Required, With Authorization)

**Only if B2 shows schema delta AND project owner authorizes:**

```bash
cd backend
uv run alembic upgrade head
```

**DO NOT run** without explicit authorization. Risk: irreversible schema changes.

---

#### B5: Index Real 600519.SH Annual Report

**After DB is healthy and ENABLE_REPORT_RAG=true is deployed:**

**Requirements:**
- Source: official 2024 annual report from CNINFO (http://www.cninfo.com.cn) or official disclosure
- File: real PDF, NOT synthetic text
- Access: production server must be able to reach CNINFO (CN server)

**Pipeline:**
```bash
# Via admin API or ingestion script
POST /api/v1/reports/ingest
{
  "ts_code": "600519.SH",
  "report_year": 2024,
  "report_type": "annual",
  "source": "cninfo_official"
}
```

**Verify in DB:**
```sql
SELECT id, ts_code, report_year, parsed, rag_status, chunk_count 
FROM report_documents WHERE ts_code = '600519.SH';

SELECT id, report_id, status, chunk_count 
FROM company_v2_report_rag_documents 
WHERE report_id IN (SELECT id FROM report_documents WHERE ts_code = '600519.SH');
```

Expected:
- `rag_status` = 'indexed' or 'embedded'
- `chunk_count` > 0

---

#### B6: Real Agent E2E (After B5)

Execute against live production endpoint:

**Analysis query:**
```bash
curl -X POST https://[production-domain]/api/v1/stock/600519/report-chat \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"question": "贵州茅台2024年财报表现如何？营收和利润增长情况怎么样？", "force_refresh": true}'
```

**Expected response fields to verify:**
```json
{
  "status": "completed",
  "partial": false,
  "confidence": "high",
  "rag_status": "indexed_fast_path",
  "chunks_retrieved": ">= 1",
  "llm_model": "deepseek-v4-flash",
  "numeric_validation": {"valid": true, "evidence_available": true},
  "errors": []
}
```

**Locator query:**
```bash
curl -X POST https://[production-domain]/api/v1/stock/600519/report-chat \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"question": "请给我贵州茅台最新年报官方PDF"}'
```

**Expected:**
```json
{
  "rag_status": "not_required",
  "intent_type": "locator"
}
```

**Cache isolation check:**
```bash
# Verify locator cache key differs from analysis cache key
# Look at X-Cache-Key response header or logs
# locator: rc:v2:locator:600519:...
# analysis: rc:v2:analysis:600519:...
```

---

#### B7: Company Overview Six-Field Verification

```bash
curl https://[production-domain]/api/v1/stocks/CN/600519/profile \
  -H "Authorization: Bearer $ACCESS_TOKEN"
```

Expected (with free mode + BaoStock enabled):
```json
{
  "snapshot": {
    "data": {
      "price": "~1346",       // or latest_price or close
      "pe_ttm": "~20.35",
      "pb": "~6.21",
      "total_mv": null,       // acceptable — BaoStock kline limitation
      "dv_ttm": null,         // acceptable — BaoStock kline limitation
      "change_pct": "..."
    }
  },
  "financial_summary": {
    "data": {
      "roe": "~38.43"         // from BaoStock profit_data
    }
  }
}
```

---

#### B8: Numeric Safety Verification

Test Case A (no chunks / no RAG):
```bash
# Query for a stock with no indexed report
POST /api/v1/stock/000001/report-chat
{"question": "请分析平安银行2024年净利润增长率"}
```
Expected: `status: partial`, `errors: ["NUMERIC_EVIDENCE_MISSING"]`

Test Case B (valid evidence from indexed report):
```bash
POST /api/v1/stock/600519/report-chat
{"question": "贵州茅台2024年营收是多少？"}
```
Expected: `status: completed`, `numeric_validation.valid: true`

---

#### B9: Frontend Production Verification

```bash
# Verify production bundle
grep -c "localhost" frontend/dist/assets/index-*.js  # expect: 0

# Verify VITE_API_BASE baked in
grep '"/api/v1"' frontend/dist/assets/index-*.js | wc -l  # expect: >= 3
```

Browser test (must be done in real browser, not just CLI):
1. Open production URL
2. Open DevTools → Network tab
3. Navigate to any stock page
4. Confirm API calls go to `/api/v1/*` (relative), NOT `localhost:8000`

---

#### B10: Browser Color Evidence

**Must be verified in real browser, not Vitest or CSS file scan:**

1. Navigate to any stock with price movement (e.g., 600519.SH)
2. Open DevTools → Console
3. Run:
```javascript
// Find an element with pct-up class
const up = document.querySelector('.pct-up');
const dn = document.querySelector('.pct-dn');
if (up) console.log('pct-up color:', getComputedStyle(up).color);
if (dn) console.log('pct-dn color:', getComputedStyle(dn).color);
```

**Expected:**
- `.pct-up` → `rgb(239, 83, 80)` (red, `#ef5350` = `var(--danger)`)
- `.pct-dn` → `rgb(38, 166, 154)` (green, `#26a69a` = `var(--success)`)

Record the actual RGB values. This must be classified `BROWSER_EVIDENCE_PASS`, not `SOURCE_ONLY`.

---

### PHASE C — Final Gate Check

Run full 26-gate matrix (see Section 4 of production_readiness.md).  
All gates must be PASS before GO decision.

---

## Timeline

| Phase | Prerequisite | Action | Owner |
|-------|-------------|--------|-------|
| A1 | — | Resume Supabase project | Project Owner |
| A2 | — | Patch root .env | Project Owner |
| B1 | A1 complete | Verify DB SELECT 1 | Engineer |
| B2 | B1 | Alembic audit | Engineer |
| B3 | B2 | Schema table check | Engineer |
| B4 | B2 + authorization | Alembic migrate (if needed) | Owner + Engineer |
| B5 | B4 + ENABLE_REPORT_RAG=true deployed | Real report ingestion | Engineer |
| B6 | B5 | Agent E2E | Engineer |
| B7 | B1 + A2 | Company Overview | Engineer |
| B8 | B6 | Numeric safety | Engineer |
| B9 | — (can run now) | Frontend bundle | Engineer |
| B10 | production deployed | Browser color | Engineer |
| C | all B PASS | 26-gate matrix | Engineer |

---

## What This Plan Does NOT Change

- **Code:** Zero code changes required. All issues are configuration and data.
- **Database schema:** If current revision matches expected, no migration needed.
- **Docker images:** After A2, a container restart picks up new env vars — no rebuild needed.
- **Frontend:** Production bundle already correct (VITE_API_BASE=/api/v1).

---

*This is a plan document. No files were modified outside this artifacts directory.*
