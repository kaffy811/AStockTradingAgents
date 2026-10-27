# Phase 6W-R2.0 — Database Readiness

**Generated:** 2026-08-12  
**Branch:** release/demo-staging  
**HEAD:** a542bc1

---

## Production DB Status: BLOCKED (Supabase Paused)

### Connectivity Audit

| Layer | Test | Result | Evidence |
|-------|------|--------|---------|
| DNS — pooler | `aws-1-ap-northeast-2.pooler.supabase.com` | **PASS** | Resolves → 15.164.188.235 |
| TCP — port 6543 | Connect | **PASS** | Connection established |
| asyncpg connect | `SELECT 1` | **FAIL** | `ENOTFOUND tenant/user postgres.qvpdtnazhxbfifrjdfdf not found` |
| DNS — project | `qvpdtnazhxbfifrjdfdf.supabase.co` | **FAIL** | `[Errno 8] nodename nor servname provided` |
| HTTPS — project REST | `https://qvpdtnazhxbfifrjdfdf.supabase.co/rest/v1/` | **FAIL** | SSL: UNEXPECTED_EOF_WHILE_READING |

**Classification:** `SUPABASE_PROJECT_PAUSED` — free-tier auto-pause after 7 days inactivity.

### Evidence of Pause (not configuration error)

1. Pooler DNS resolves and TCP connects → network and pooler infrastructure healthy
2. ENOTFOUND tenant from pooler → project tenant not active in pooler
3. Project subdomain DNS fails → project is not serving
4. SSL EOF on project HTTPS → server closed connection without TLS handshake
5. This is the documented behavior for paused Supabase free-tier projects

### Owner Action Required

```
1. Go to: https://supabase.com/dashboard
2. Select project: qvpdtnazhxbfifrjdfdf
3. Click "Resume project"
4. Wait ~60 seconds for project activation
5. Verify: curl -s https://qvpdtnazhxbfifrjdfdf.supabase.co/rest/v1/ 
   → expect HTTP 401 (project active, missing API key)
   → NOT SSL EOF or DNS failure
```

---

## Post-Resume Actions (Engineer, After Owner Resumes)

### DB Connectivity Verification

```bash
python3 -c "
import asyncio, asyncpg

async def test():
    dsn = '<DATABASE_URL from .env>'
    conn = await asyncio.wait_for(asyncpg.connect(dsn, ssl='require', timeout=12), timeout=15)
    r = await conn.fetchval('SELECT 1')
    print(f'SELECT 1 = {r}')
    await conn.close()

asyncio.run(test())
"
```

Expected: `SELECT 1 = 1`

### Alembic Schema Audit

```bash
cd backend
uv run alembic current   # check current migration on production DB
uv run alembic heads     # confirm repository head = p4q5r6s7t8u9
```

**Expected HEAD:** `p4q5r6s7t8u9` (`2026_07_28_0001-p4q5r6s7t8u9_add_email_verified_at.py`)

### Required Table Check

```sql
SELECT table_name, 
       (SELECT count(*) FROM information_schema.columns 
        WHERE table_name = t.table_name) AS col_count
FROM information_schema.tables t
WHERE table_schema = 'public'
AND table_name IN (
  'report_documents',
  'company_v2_report_rag_documents', 
  'company_v2_report_rag_chunks',
  'chat_sessions',
  'chat_messages',
  'users',
  'alembic_version'
)
ORDER BY table_name;
```

Expected: 7 rows.

### If Schema Delta Exists (alembic current ≠ p4q5r6s7t8u9)

**DO NOT run automatically.** Generate `company_agents_data_r2_migration_plan.md` and await project owner authorization.

If authorized:
```bash
cd backend
uv run alembic upgrade head
```

Prohibited:
```bash
# NEVER
DROP TABLE ...
TRUNCATE ...
DELETE FROM ...
alembic downgrade ...
```

---

## Migration Chain Reference (Offline Audit)

| Revision | File | Purpose |
|----------|------|---------|
| baseline | 2026_05_30_1612-4b49004d01a6 | Existing schema baseline |
| 76fe066d | 2026_06_01_0937 | stock_master table |
| 3a2f8b4c | 2026_06_04_0001 | stock_name on analysis_reports |
| a7c3f91e | 2026_06_04_0002 | auto_saved field |
| b4d8e2f1 | 2026_06_04_0003 | analysis_scope field |
| c5e9f12a | 2026_06_07_0001 | output_language field |
| d7e3a9b5 | 2026_06_12_0001 | chat tables |
| e8f3a2c7 | 2026_06_24_0001 | financial_rag tables |
| f1a4b7c9 | 2026_06_24_0002 | content_hash |
| a2c5e8f1 | 2026_06_24_0003 | pgvector embedding |
| b8c3d9e2 | 2026_07_05_0001 | ETL tables |
| c1d2e3f4 | 2026_07_06_0001 | **report_documents** ← RAG dep |
| d2e3f4a5 | 2026_07_06_0002 | report_discovery_fields |
| e3f4a5b6 | 2026_07_06_0003 | pdf_download_parse_fields |
| f4a5b6c7 | 2026_07_06_0004 | report_chunks |
| g5h6i7j8 | 2026_07_06_0005 | embedding dim 384 |
| h6i7j8k9 | 2026_07_07_0001 | coverage tables |
| i7j8k9l0 | 2026_07_11_0001 | **company_v2_rag** ← RAG dep |
| j8k9l0m1 | 2026_07_12_0001 | fusion_jobs |
| k9l0m1n2 | 2026_07_13_0001 | worker_foundation |
| l0m1n2o3 | 2026_07_14_0001 | shadow_observation_index |
| m1n2o3p4 | 2026_07_26_0001 | pi_real_provider_audit |
| n2o3p4q5 | 2026_07_26_0002 | mvp_release_tables |
| o3p4q5r6 | 2026_07_26_0003 | mvp_r12_invite_security |
| 37cd8a42 | 2026_07_27_1120 | fix invite redeemed_by uuid |
| **p4q5r6s7** | **2026_07_28_0001** | **add_email_verified_at ← HEAD** |

RAG-critical migrations: `c1d2e3f4` (report_documents) and `i7j8k9l0` (company_v2_rag_documents, company_v2_rag_chunks) — both must be applied.

---

*DB is BLOCKED until project owner resumes Supabase. No destructive operations were performed.*
