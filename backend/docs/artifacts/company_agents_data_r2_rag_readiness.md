# Phase 6W-R2.0 — RAG Readiness

**Generated:** 2026-08-12  
**Branch:** release/demo-staging  
**HEAD:** a542bc1

---

## Status: BLOCKED (Production DB Paused)

RAG initialization cannot proceed until Supabase is resumed. All steps below are documented for execution after DB is restored.

---

## Configuration

After root `.env` alignment:

| Flag | Value | Effect |
|------|-------|--------|
| `ENABLE_REPORT_RAG` | `true` | RAG enabled — `ReportRagService` active |
| `ENABLE_REPORT_PDF` | `true` | PDF pipeline enabled — ingestion allowed |
| `report_embedding_provider` | `mock` (config default) | WARNING — see below |

### Embedding Provider Warning

`config.py` default: `report_embedding_provider: str = "mock"`  
`REPORT_EMBEDDING_PROVIDER` is NOT in root `.env`.

**Impact:** In mock mode, embeddings are random vectors. Similarity search will return random results. RAG retrieval will be unreliable.

**Required action (before real E2E):**
- If production server has GPU or acceptable CPU: add `REPORT_EMBEDDING_PROVIDER=local` and `REPORT_EMBEDDING_MODEL=BAAI/bge-small-zh-v1.5` to root `.env`
- If using OpenAI embeddings: add `REPORT_EMBEDDING_PROVIDER=openai` and `OPENAI_API_KEY=...`
- If using BM25-only (keyword search): the fallback in `ReportRagService` uses BM25 when vector search returns empty — this may be acceptable for initial launch

**This is a newly identified gap** not present in R1.7/R1.8 reports. Must be resolved before G5/G6/G7/G8 can pass.

---

## Required DB Tables

After DB is restored, verify:

```sql
SELECT table_name FROM information_schema.tables 
WHERE table_schema = 'public'
AND table_name IN (
  'report_documents',
  'company_v2_report_rag_documents',
  'company_v2_report_rag_chunks'
);
```

Expected: 3 rows.

---

## Real Report Ingestion Plan

### Source Requirement

- **Symbol:** 600519.SH (贵州茅台)
- **Report year:** 2024
- **Report type:** Annual (年报)
- **Source:** CNINFO official disclosure — http://www.cninfo.com.cn
- **File type:** Official PDF announcement

**PROHIBITED:** Synthetic chunks, manually typed text, staging data.

### Download Path

CNINFO disclosure URL pattern for 贵州茅台 2024 annual report:
```
http://static.cninfo.com.cn/finalpage/[year]/[report_id].PDF
```

Actual URL must be fetched from CNINFO search (requires CN network access from production server).

### Ingestion Pipeline

```bash
# Step 1: Ensure backend container is running with ENABLE_REPORT_PDF=true
# Step 2: Trigger ingestion via admin API
POST /api/v1/admin/reports/ingest
{
  "ts_code": "600519.SH",
  "report_year": 2024,
  "report_type": "annual",
  "source_url": "<CNINFO official PDF URL>"
}

# Step 3: Verify ingestion
GET /api/v1/admin/reports/status?ts_code=600519.SH
```

### Verification Queries (After Ingestion)

```sql
-- 1. Check report_documents
SELECT id, ts_code, report_year, report_type, parsed, rag_status, chunk_count, source
FROM report_documents 
WHERE ts_code = '600519.SH' AND report_year = 2024;
-- Expected: parsed=true, rag_status='indexed', chunk_count > 0

-- 2. Check company_v2_rag_documents
SELECT id, report_id, status, chunk_count, index_generation, active_index
FROM company_v2_report_rag_documents
WHERE report_id IN (
  SELECT id FROM report_documents WHERE ts_code = '600519.SH' AND report_year = 2024
);
-- Expected: status='indexed', chunk_count > 0, active_index=1

-- 3. Check chunks
SELECT count(*), min(chunk_index), max(chunk_index)
FROM company_v2_report_rag_chunks
WHERE rag_document_id IN (
  SELECT id FROM company_v2_report_rag_documents WHERE status = 'indexed'
);
-- Expected: count > 0
```

---

## Post-Ingestion E2E Verification

### Analysis Query (Must Return COMPLETED)

```bash
POST /api/v1/stock/600519/report-chat
Authorization: Bearer <user_token>
{
  "question": "贵州茅台2024年财报表现如何？营收和利润增长情况怎么样？",
  "force_refresh": true
}
```

**Required response fields:**

| Field | Expected | Evidence of |
|-------|----------|------------|
| `status` | `"completed"` | Full chain success |
| `partial` | `false` | No degradation |
| `confidence` | `"high"` | Evidence quality |
| `rag_status` | `"indexed_fast_path"` | Real indexed report found |
| `chunks_retrieved` | `>= 1` | Real chunks retrieved |
| `llm_model` | `"deepseek-v4-flash"` | Real LLM invoked |
| `numeric_validation.valid` | `true` | Numbers grounded in evidence |
| `numeric_validation.evidence_available` | `true` | Evidence chain complete |
| `errors` | `[]` | No errors |

**Any answer containing unsupported financial numbers → FAIL.**

### Locator Query (Must NOT Call LLM)

```bash
POST /api/v1/stock/600519/report-chat
Authorization: Bearer <user_token>
{
  "question": "请给我贵州茅台最新年报官方PDF"
}
```

**Expected:**
```json
{
  "rag_status": "not_required",
  "intent_type": "locator"
}
```

**Cache isolation verify:** locator cache key `rc:v2:locator:600519:...` ≠ analysis key `rc:v2:analysis:600519:...`.

---

## Additional Config Gap Identified

| Variable | Root .env | Config Default | Issue |
|----------|-----------|----------------|-------|
| `REPORT_EMBEDDING_PROVIDER` | ABSENT | `"mock"` | RAG similarity search unreliable |
| `REPORT_EMBEDDING_MODEL` | ABSENT | `None` | Must set if using local/openai provider |

**Add to root `.env` before real RAG verification:**
```bash
REPORT_EMBEDDING_PROVIDER=local
REPORT_EMBEDDING_MODEL=BAAI/bge-small-zh-v1.5
```

Or confirm BM25-only fallback is acceptable for initial launch.

---

*No production data was written. All steps are pending DB resume.*
