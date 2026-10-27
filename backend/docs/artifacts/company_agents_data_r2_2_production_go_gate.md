# Phase 6W-R2.2 — Production GO Gate Matrix

**Generated:** 2026-08-12  
**Branch:** release/demo-staging  
**HEAD:** a542bc18a21e465c7025d4bdc8c16f032f60736d

---

## Gate Matrix

| Gate | Description | Evidence | Status |
|------|-------------|---------|--------|
| **G1** | Production DB reachable (asyncpg SELECT 1) | DNS project: FAIL `[Errno 8] nodename nor servname`. DNS pooler: PASS 43.202.154.182. TCP 6543: PASS. HTTPS REST: FAIL SSL EOF. Classification: SUPABASE_PROJECT_PAUSED. | **BLOCKED** |
| **G2** | Alembic revision == p4q5r6s7t8u9 (HEAD) | Cannot run `alembic current` — asyncpg unreachable. Expected HEAD: p4q5r6s7t8u9 (2026_07_28_0001). | **BLOCKED** |
| **G3** | DeepSeek HTTP 200 OK | R2.0 verified: HTTP 200, model=deepseek-v4-flash, latency=669ms, key sk-8*** len=35. | **PASS** |
| **G4** | RAG enabled (ENABLE_REPORT_RAG=true) | Root .env confirmed: `ENABLE_REPORT_RAG=true`. Verified via grep. Config default was `false` — now overridden. | **PASS** |
| **G5** | Real 600519.SH 2024 report indexed (chunk_count>0) | Cannot ingest — DB paused. No real PDF indexed. No synthetic data permitted. Depends on G1+G2+container restart. | **BLOCKED** |
| **G6** | Real financial query: status=completed, rag_status=indexed_fast_path | Cannot run E2E — depends on G5. | **BLOCKED** |
| **G7** | Numeric validation: valid=true, evidence_available=true | Cannot verify — depends on G6. | **BLOCKED** |
| **G8** | Provider chain: BaoStock → price/PE/PB/ROE for 600519 | R2.0 live test PASS: close=1346.50, peTTM=20.35, pbMRQ=6.21, roeAvg=38.43%. BaoStock login code=0. DATA_MODE=free in root .env. | **PASS** |
| **G9** | Company Overview 4 of 6 fields not null (price/PE/PB/ROE) | BaoStock provides all 4 required fields. total_mv and dv_ttm null = accepted graceful degradation. Frontend fmt(null)→"—" verified. Live API test requires container restart after G1. | **PASS (code+provider)** |
| **G10** | Cache isolation: locator key ≠ analysis key | Key format: `rc:v2:{intent_type}:{ts_code}:...` — intent_type segment structurally isolates locator from analysis. R1.6 staging: locator returned `rag_status=not_required` separately. Live test requires G6. | **PASS (code)** |
| **G11** | Frontend VITE_API_BASE=/api/v1, no localhost in bundle | Production bundle `index-BxIiHZ4a.js`: 0× localhost, 3× "/api/v1". `frontend/.env.production` VITE_API_BASE=/api/v1. Docker build arg `/api/v1`. | **PASS** |
| **G12** | A股 browser color: pct-up=red, pct-dn=green | Playwright Chromium headless: `.pct-up[data-v-ce6f7f0c]{color:var(--danger)}` verified in browser stylesheet. `--danger`=rgb(229,72,93) red. `--success`=rgb(22,160,133) green. | **BROWSER_EVIDENCE_PASS** |
| **G13** | Badge semantics: partial_success displays in danger (red), not success | Playwright: `.badge-failed{background:rgba(245,85,74,0.12);color:var(--danger)}`. `badgeClass('partial_success')`→`'badge-failed'` confirmed in source. | **PASS** |
| **G14** | No secrets in responses, artifacts, or terminal output | All R1.7→R2.2 artifact files: 0 occurrences of full token/key values. Masking: PRESENT/len/prefix only. Terminal outputs reviewed. | **PASS** |

---

## Embedding Provider Status (Identified Gap — Resolved)

| Variable | Root .env | Config Default | Status |
|----------|-----------|----------------|--------|
| `REPORT_EMBEDDING_PROVIDER` | `local` | `mock` | **SET in R2.1** |
| `REPORT_EMBEDDING_MODEL` | `BAAI/bge-small-zh-v1.5` | `None` | **SET in R2.1** |

`sentence-transformers` not installed → embedding step skipped → `rag_status="chunked"`.  
`_is_indexed_report()` accepts `"chunked"` → keyword retrieval path active. **NOT a P0 blocker.**

---

## Gate Summary

| Status | Gates | Count |
|--------|-------|-------|
| PASS | G3, G4, G8, G9*, G10*, G11, G12, G13, G14 | 9 |
| BLOCKED | G1, G2, G5, G6, G7 | 5 |

*G9, G10: pass at code/provider level; require live production container verification after G1.  
G12: BROWSER_EVIDENCE_PASS included in PASS count.

**P0 BLOCKED: 5 gates — all dependent on single owner action.**

---

## DECISION: NO-GO

**Reason:** Production database paused. 5 gates BLOCKED.

**No code defects identified.** Every blocked gate is environment or data — not application logic.

**Root .env is complete.** All feature flags and embedding config are set.

---

## Single Remaining Owner Action

```
1. Go to: https://supabase.com/dashboard
   Project ref: qvpdtnazhxbfifrjdfdf
   Action: Click "Resume project" → wait ~60 seconds

2. Verify active:
   curl -I https://qvpdtnazhxbfifrjdfdf.supabase.co/rest/v1/
   → Expected: HTTP 401 (NOT SSL EOF)
```

---

## Full Engineer Execution Sequence (Post-Owner-Action)

```bash
# 1. Verify DB connectivity (see company_agents_data_r2_2_database_recovery.md)
python3 <connection test script>
# Expected: SELECT 1 = 1, 7/7 tables present → G1 PASS

# 2. Verify migration
cd backend && uv run alembic current
# Expected: p4q5r6s7t8u9 (head) → G2 PASS
# If delta: STOP, report, await authorization

# 3. Restart containers (picks up new .env flags, no rebuild needed)
cd /Users/kaffy/Documents/TradingAgents
docker compose down
docker compose up -d
docker compose ps  # verify all healthy

# 4. Verify effective config in container
docker compose exec backend printenv | grep -E "ENABLE_|DATA_MODE|REPORT_EMBEDDING"

# 5. Fetch CNINFO PDF URL and ingest real report
POST /api/v1/admin/reports/ingest {"ts_code":"600519.SH","report_year":2024,...}
# (see company_agents_data_r2_2_report_ingestion.md for full procedure)
# Expected: chunk_count > 0 → G5 PASS

# 6. E2E financial query
POST /api/v1/stock/600519/report-chat {"question":"贵州茅台2024年财报表现如何？","force_refresh":true}
# Expected: status=completed, rag_status=indexed_fast_path, chunks_retrieved>=1 → G6 PASS
# Expected: numeric_validation.valid=true → G7 PASS

# 7. Company Overview live
GET /api/v1/stocks/CN/600519/profile
# Expected: price/pe_ttm/pb/roe not null → G9 live PASS

# 8. Cache isolation
POST /api/v1/stock/600519/report-chat {"question":"贵州茅台最新报告是哪一份？"}
# Expected: intent_type=locator, rag_status=not_required → G10 live PASS

# 9. Re-run this gate matrix → issue GO
```

---

## Conditions for GO Decision

All five must pass:

- [ ] G1: asyncpg SELECT 1 = 1
- [ ] G2: alembic current == p4q5r6s7t8u9
- [ ] G5: chunk_count > 0 in production DB (real CNINFO PDF)
- [ ] G6: status=completed, rag_status=indexed_fast_path
- [ ] G7: numeric_validation.valid=true

When all five checked: **DECISION: GO**

Production deployment authorized only after GO decision and explicit project owner authorization.

---

## Environment Snapshot (R2.2 Start)

| Item | Value |
|------|-------|
| Branch | release/demo-staging |
| HEAD | a542bc18a21e465c7025d4bdc8c16f032f60736d |
| Uncommitted changes | Untracked artifacts only (no modified tracked files) |
| Root .env | 44 lines, 10 feature/config flags set, secrets present (not printed) |
| backend/.env | 997 bytes, dev-only, NOT loaded by docker-compose |
| Stash | 2 stash entries (WIP from prior phases — not relevant) |
| Artifacts generated this phase | 5 files in backend/docs/artifacts/ |

---

*No production deploy performed. No code modified. No secrets printed. All changes: root .env (R2.0/R2.1) + artifacts (R2.2).*
