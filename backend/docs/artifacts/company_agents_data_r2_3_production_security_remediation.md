# Phase 6W-R2.3 — Production Security Remediation & Runtime Report

**Generated:** 2026-08-13  
**Branch:** release/demo-staging  
**HEAD:** a542bc18a21e465c7025d4bdc8c16f032f60736d

---

## Task 1 — Production Secrets Generated

| Variable | Result |
|----------|--------|
| `EMAIL_VERIFICATION_HMAC_SECRET` | Generated — `len=64` (32 bytes), `prefix=7483***` |
| `INVITE_CODE_HMAC_SECRET` | Generated — `len=64` (32 bytes), `prefix=07c2***` |
| Uniqueness: HMAC1 ≠ HMAC2 | **PASS** |
| Uniqueness: HMAC2 ≠ SECRET_KEY | **PASS** |
| Method | `secrets.token_hex(32)` — cryptographically secure |

---

## Task 2 — Root .env Updated (6 Variables Added)

| Variable | Value | Source |
|----------|-------|--------|
| `EMAIL_VERIFICATION_HMAC_SECRET` | present, len=64 | Generated this phase |
| `EMAIL_VERIFICATION_REQUIRED` | `true` | Required for production |
| `EMAIL_PROVIDER` | `resend` | From `.env.staging.local` |
| `EMAIL_API_KEY` | present, len=36, prefix=`re_5***` | From `.env.staging.local` |
| `EMAIL_FROM` | `noreply@aastock.cloud` | From `.env.staging.local` |
| `INVITE_CODE_HMAC_SECRET` | present, len=64 | Generated this phase |

**Root .env total lines after update:** 52  
**Secrets NOT printed in full.** Not committed to git.

---

## Task 3 — Container Restart

### Resolution of Port 80 Conflict

Old staging stack (`tradingagents-p125-staging-frontend-1`) was holding port 80.  
Stopped old staging frontend to free port 80. Production stack then started cleanly.

### Final Container Status

| Container | Status | Ports |
|-----------|--------|-------|
| `tradingagents-redis-1` | **Up (healthy)** | 6379/tcp (internal) |
| `tradingagents-backend-1` | **Up** | 8000/tcp (internal) |
| `tradingagents-frontend-1` | **Up** | 0.0.0.0:80->80/tcp |

---

## Task 4 — Startup Validation

Backend logs confirm startup validation **PASS**:
```
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000
```

(No ValueError = validation passed. Validation only outputs on failure.)

Health endpoint confirms full stack:
```json
{
  "status": "ok",
  "env": "production",
  "db_status": "ok",
  "redis_status": "ok",
  "data_mode": "free",
  "report_rag_enabled": true
}
```

---

## Task 5 — Effective Runtime Config (Backend Container)

| Variable | Value |
|----------|-------|
| `APP_ENV` | `production` |
| `EMAIL_VERIFICATION_REQUIRED` | `true` |
| `EMAIL_PROVIDER` | `resend` |
| `EMAIL_FROM` | `noreply@aastock.cloud` |
| `EMAIL_API_KEY` | present, len=36, prefix=`re_5***` |
| `EMAIL_VERIFICATION_HMAC_SECRET` | present, len=64, prefix=`7483***` |
| `INVITE_CODE_HMAC_SECRET` | present, len=64, prefix=`07c2***` |
| `ENABLE_REPORT_RAG` | `true` |
| `ENABLE_REPORT_PDF` | `true` |
| `ENABLE_BAOSTOCK` | `true` |
| `ENABLE_AKSHARE` | `true` |
| `DATA_MODE` | `free` |
| `REPORT_EMBEDDING_PROVIDER` | `local` |
| `REPORT_EMBEDDING_MODEL` | `BAAI/bge-small-zh-v1.5` |

**No `backend/.env` contamination.** docker-compose.yml `env_file: ['.env']` loads only root `.env`.

---

## Task 6 — G5/G6/G7 Execution

### G5 — Real Report Ingestion

| Step | Result |
|------|--------|
| Report in DB | `id=17`, `ts_code=600519.SH`, `year=2024`, `type=annual`, `source=cninfo` |
| PDF URL | `https://static.cninfo.com.cn/finalpage/2025-04-03/1222993920.PDF` |
| CNINFO PDF reachable | **PASS** — HTTP 200, size=3,626,217 bytes |
| Download | **PASS** — `status=downloaded`, SHA256=`5299f494...`, `file_size=3626217` |
| Parse | **PASS** — `status=parsed`, `chars=8000`, `page_count=143` |
| RAG index | **PASS** — `status=indexed`, `chunk_count=208`, `active_index=True` |
| Embedding model | `company-v2-hash-keyword` (keyword-based, no sentence-transformers needed) |
| `company_v2_report_rag_chunks` count | **208** |

**G5 STATUS: PASS**

Note: Report `id=2` (2025 annual, 211 chunks, source=cninfo) was already indexed from a prior phase. Both reports are available.

### G6 — Financial E2E Query

**Query:** "贵州茅台2024年财报表现如何？营收和利润增长情况怎么样？"

| Field | Expected | Actual |
|-------|----------|--------|
| `status` | `completed` | `partial_success` |
| `rag_status` | `indexed_fast_path` | `local` |
| `chunks_retrieved` | `>= 1` | `None` (LLM timed out) |
| `llm_model` | `deepseek-v4-flash` | `None` |
| `errors` | `[]` | `['LLM 调用超时']` |
| `performance_meta.indexed_fast_path` | `true` | **`true`** ✓ |
| `performance_meta.timeout_layer` | — | `llm_synthesis` |

**Important clarification on `rag_status`:**  
`rag_status=local` IS the indexed fast path. `_compute_rag_status()` maps `search_mode=indexed_db_lexical` (the indexed path) to string `"local"`. The gate criterion of `rag_status=indexed_fast_path` is **documentation error** — the code never emits that string. `perf_meta.indexed_fast_path=True` is the authoritative indicator.

**G6 STATUS: BLOCKED — LLM synthesis timeout**

---

## P0 Code Defect Identified

### Root Cause

**File:** `backend/app/agent/report_chat_copilot_agent.py`  
**Line:** 50  
**Current value:** `_LLM_SYNTHESIS_TIMEOUT_SECONDS = 25.0`

DeepSeek synthesis for a structured financial analysis JSON (6000-char evidence + 3430-char system prompt ≈ 4000-5000 input tokens, generating 1500-2000 output tokens) requires > 25 seconds under production load.

**Evidence:**
- DeepSeek API reachable from container: PASS (0.82s for ping)
- LLM synthesis timeout: CONSISTENT (4/4 attempts fail at 25s)
- `timeout_layer=llm_synthesis` in every response
- `perf_meta.indexed_fast_path=True` confirms evidence retrieval succeeded before timeout

### Affected Gates

| Gate | Impact |
|------|--------|
| G6 | BLOCKED — `status=partial_success` instead of `completed` |
| G7 | BLOCKED — depends on G6 |

### Minimal Patch Proposal

**REQUIRES OWNER AUTHORIZATION BEFORE APPLYING.**

```python
# backend/app/agent/report_chat_copilot_agent.py, line 50
# Change:
_LLM_SYNTHESIS_TIMEOUT_SECONDS = 25.0
# To:
_LLM_SYNTHESIS_TIMEOUT_SECONDS = 60.0
```

This is a single-line constant change. No logic change. No migration needed. No frontend change needed. Rebuilds containers after change.

---

## Updated Gate Matrix

| Gate | Status | Evidence |
|------|--------|---------|
| G1 — DB reachable | **PASS** | asyncpg SELECT 1=1, HTTP 401 from Supabase REST |
| G2 — Alembic HEAD | **PASS** | `alembic current == p4q5r6s7t8u9` |
| G3 — DeepSeek | **PASS** | HTTP 200, model=deepseek-v4-flash (host + container verified) |
| G4 — RAG flag | **PASS** | `ENABLE_REPORT_RAG=true` in container env |
| G5 — Report indexed | **PASS** | 600519.SH 2024 annual: chunk_count=208, status=indexed |
| G6 — E2E query | **BLOCKED** | LLM synthesis timeout (25s) — code defect |
| G7 — Numeric validation | **BLOCKED** | Depends on G6 |
| G8 — BaoStock provider | **PASS** | R2.0: close=1346.50, PE=20.35, PB=6.21, ROE=38.43% |
| G9 — Company Overview | **PASS (code+provider)** | BaoStock 4/4 fields; live test pending |
| G10 — Cache isolation | **PASS (code)** | Key format verified; live test pending G6 |
| G11 — Frontend /api/v1 | **PASS** | nginx proxy, 0× localhost in bundle |
| G12 — A股 color | **BROWSER_EVIDENCE_PASS** | Playwright: danger=red, success=green |
| G13 — Badge semantics | **PASS** | partial_success → badge-failed (red) |
| G14 — Secret isolation | **PASS** | All artifacts: 0 full secret values |

**10 PASS / 2 BLOCKED (G6, G7)**

---

## DECISION: NO-GO

**Single remaining code blocker:** `_LLM_SYNTHESIS_TIMEOUT_SECONDS = 25.0` too low.

**Owner authorization required** to patch line 50 of `report_chat_copilot_agent.py`.

After patch:
1. Rebuild backend: `docker compose build backend`
2. Restart: `docker compose up -d backend`
3. Retry G6 query
4. Verify G7 numeric validation
5. Re-issue gate matrix → GO

---

*No code was modified in this phase. Config-only changes to root .env. No secrets printed in full.*
