# Phase 6W-R2.2 — Real Report Ingestion

**Generated:** 2026-08-12  
**Branch:** release/demo-staging  
**HEAD:** a542bc18a21e465c7025d4bdc8c16f032f60736d  
**Gate:** G5

---

## Current State: BLOCKED (depends on G1, G2, container restart)

Cannot ingest until production database is reachable and containers are running with updated env vars.

---

## Source Requirements

| Field | Value |
|-------|-------|
| Symbol | 600519.SH (贵州茅台) |
| Report year | 2024 |
| Report type | Annual (年报) |
| Source | CNINFO official disclosure |
| Source URL | http://www.cninfo.com.cn (fetch actual URL from search) |
| File format | Official PDF announcement |

**PROHIBITED:**
- Synthetic chunk generation
- Manual SQL INSERT into chunk tables
- Manually typed financial text
- Staging data or test fixtures
- Any data not from the official CNINFO PDF

---

## Pre-Ingestion Container Check

Before calling the ingestion API, confirm containers are running:

```bash
docker compose ps
```

Expected:
```
NAME                    STATUS
tradingagents-backend   Up (healthy)
tradingagents-frontend  Up
tradingagents-redis     Up
```

Confirm env flags are loaded in backend container:

```bash
docker compose exec backend printenv ENABLE_REPORT_PDF
docker compose exec backend printenv ENABLE_REPORT_RAG
docker compose exec backend printenv DATA_MODE
```

Expected: `true`, `true`, `free`

---

## Ingestion Procedure

### Step 1: Fetch CNINFO PDF URL

From the production server (CN network required for CNINFO):

```bash
# Option A: CNINFO search API
curl -s "http://www.cninfo.com.cn/new/hisAnnouncement/query" \
  -d "qlKeywords=600519&seDate=2025-01-01~2025-12-31&category=category_ndbg_szsh" \
  | python3 -c "import sys,json; data=json.load(sys.stdin); [print(a['adjunctUrl']) for a in data.get('announcements',[])[:3]]"

# Option B: Manually find from cninfo.com.cn search for 贵州茅台 2024年报
# Expected URL pattern: http://static.cninfo.com.cn/finalpage/YYYY/NNNNNN.PDF
```

### Step 2: Trigger Ingestion via Admin API

```bash
# Replace <TOKEN> with admin user JWT from login
# Replace <PDF_URL> with actual CNINFO PDF URL from Step 1

curl -s -X POST http://localhost:8000/api/v1/admin/reports/ingest \
  -H "Authorization: Bearer <TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{
    "ts_code": "600519.SH",
    "report_year": 2024,
    "report_type": "annual",
    "source_url": "<PDF_URL>"
  }' | python3 -m json.tool
```

Expected response:
```json
{
  "status": "queued",
  "document_id": "<uuid>",
  "ts_code": "600519.SH",
  "report_year": 2024
}
```

### Step 3: Monitor Ingestion Progress

```bash
# Poll status until parsed=true
curl -s "http://localhost:8000/api/v1/admin/reports/status?ts_code=600519.SH" \
  -H "Authorization: Bearer <TOKEN>" | python3 -m json.tool
```

Expected final state:
```json
{
  "ts_code": "600519.SH",
  "report_year": 2024,
  "report_type": "annual",
  "parsed": true,
  "rag_status": "chunked",
  "chunk_count": ">0",
  "source": "cninfo_official"
}
```

---

## Database Verification Queries

Run after ingestion completes:

```sql
-- 1. report_documents
SELECT id, ts_code, report_year, report_type, parsed, rag_status, chunk_count, source
FROM report_documents 
WHERE ts_code = '600519.SH' AND report_year = 2024;
-- Required: parsed=true, rag_status IN ('indexed','embedded','ready','chunked'), chunk_count > 0

-- 2. company_v2_report_rag_documents
SELECT id, report_id, status, chunk_count, index_generation, active_index
FROM company_v2_report_rag_documents
WHERE report_id IN (
  SELECT id FROM report_documents WHERE ts_code = '600519.SH' AND report_year = 2024
);
-- Required: status IN ('indexed','chunked'), chunk_count > 0

-- 3. company_v2_report_rag_chunks (count)
SELECT count(*), min(chunk_index), max(chunk_index)
FROM company_v2_report_rag_chunks
WHERE rag_document_id IN (
  SELECT id FROM company_v2_report_rag_documents 
  WHERE report_id IN (
    SELECT id FROM report_documents WHERE ts_code = '600519.SH' AND report_year = 2024
  )
);
-- Required: count > 0
```

### G5 Pass Criteria

| Check | Required |
|-------|---------|
| `report_documents` row exists for 600519.SH 2024 | ✓ |
| `parsed = true` | ✓ |
| `rag_status` IN ('indexed','embedded','ready','chunked') | ✓ |
| `chunk_count > 0` | ✓ |
| `source` != synthetic/manual | ✓ |
| `company_v2_report_rag_chunks` count > 0 | ✓ |

---

## Embedding Note

`REPORT_EMBEDDING_PROVIDER=local` is configured but `sentence-transformers` is not installed.  
`LocalSentenceTransformerProvider.is_available()` returns `False` → embedding step is **skipped** → `rag_status` will be `"chunked"` (not `"indexed"`).

`_is_indexed_report()` accepts `rag_status="chunked"` → **keyword retrieval path is active**.  
This is acceptable for G5/G6. Vector similarity is not required.

---

## G5 Verdict

**BLOCKED** — awaiting G1 (database) + G2 (migration) + container restart.

*Update this file after chunk_count > 0 is confirmed in production DB.*
