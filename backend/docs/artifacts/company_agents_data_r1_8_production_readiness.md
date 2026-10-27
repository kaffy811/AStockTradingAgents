# Phase 6W-R1.8 Final Report — Production Readiness Assessment

**Generated:** 2026-08-12  
**Branch:** release/demo-staging  
**Base SHA:** a542bc1 (R1.5 runtime truth + R1.6 E2E acceptance)  
**Current HEAD:** a542bc1  
**Staging:** Containers still running (38 hours up)  
**Auditor role:** Senior Backend + Data/Agent + DevOps + QA + Technical PM

---

## 1. Base SHA

`a542bc1` — docs(phase6w): R1.5 runtime truth + R1.6 e2e acceptance (18/18 PASS)

---

## 2. Current HEAD

`a542bc1`

---

## 3. Branch

`release/demo-staging`

---

## 4. Git Status

```
?? backend/docs/artifacts/company_agents_data_r1_7_production_preflight.md
?? backend/docs/artifacts/company_agents_data_r1_8_env_audit.md          (NEW this phase)
?? backend/docs/artifacts/company_agents_data_r1_8_preflight_plan.md      (NEW this phase)
?? backend/docs/artifacts/company_agents_data_r1_8_provider_matrix.md     (NEW this phase)
?? backend/docs/artifacts/company_agents_data_r1_8_production_readiness.md (this file)
?? memory/project_phase6w_r14_staging_smoke.md
```

No tracked file modifications. All R1.8 work is new artifact files only.

---

## 5. Production DB Status

**FAIL — BLOCKED**

| Layer | Test | Result | Evidence |
|-------|------|--------|---------|
| DNS (pooler) | `aws-1-ap-northeast-2.pooler.supabase.com` → IP | **PASS** | Resolves to 15.164.188.235 |
| TCP (pooler) | port 6543 connect | **PASS** | Connection established |
| asyncpg connect | `asyncpg.connect(dsn, ssl='require', timeout=15)` | **FAIL** | `InternalServerError: (ENOTFOUND) tenant/user postgres.qvpdtnazhxbfifrjdfdf not found` |
| DNS (project) | `qvpdtnazhxbfifrjdfdf.supabase.co` → IP | **FAIL** | `[Errno 8] nodename nor servname provided, or not known` |
| HTTPS (project) | `https://qvpdtnazhxbfifrjdfdf.supabase.co/rest/v1/` | **FAIL** | `SSL: UNEXPECTED_EOF_WHILE_READING` |

---

## 6. Supabase Status

**CLASSIFICATION: PROJECT_PAUSED**

**Evidence chain:**
1. Pooler DNS resolves → the pooler infrastructure is healthy
2. Pooler TCP port 6543 connects → network is reachable
3. asyncpg returns `ENOTFOUND tenant/user` → the pooler cannot find the project tenant
4. Project subdomain DNS FAILS → `qvpdtnazhxbfifrjdfdf.supabase.co` does not resolve
5. Project HTTPS → SSL EOF → project is not serving

**Diagnostic:** Supabase free-tier projects auto-pause after 7 days inactivity. DNS for the project subdomain (`PROJECT_REF.supabase.co`) stops resolving when paused. The Transaction Pooler returns `ENOTFOUND tenant` because the tenant is not active. This is the standard Supabase pause behavior.

**Required action:** Project owner must log into https://supabase.com/dashboard, select project `qvpdtnazhxbfifrjdfdf`, and click "Resume project".

**This is a P0 blocker. All DB-dependent steps (STEP 3–9) are STOPPED.**

---

## 7. Migration Status

**BLOCKED — Cannot assess**

Production DB is unreachable. Cannot run `alembic current` or query `alembic_version` table.

**What is known offline:**
- Repository expected HEAD: `p4q5r6s7t8u9` (`2026_07_28_0001-p4q5r6s7t8u9_add_email_verified_at.py`)
- Total migrations in repository: 25 files
- Last migration date: 2026-07-28

**Post-resume action:** Run `alembic current` → compare to `p4q5r6s7t8u9` → generate migration_plan.md if delta exists → await authorization before any `alembic upgrade head`.

---

## 8. Environment Configuration Status

**FAIL — 5 variables missing from root `.env`**

| Variable | Root `.env` | Production Runtime | Config Default | Status |
|----------|------------|-------------------|----------------|--------|
| `DATA_MODE` | ABSENT | `"standard"` | `"standard"` | ❌ WRONG — Tushare-first, permission denied |
| `ENABLE_BAOSTOCK` | ABSENT | `false` | `False` | ❌ WRONG — BaoStock disabled |
| `ENABLE_AKSHARE` | ABSENT | `false` | `False` | ❌ WRONG — AkShare disabled |
| `ENABLE_REPORT_PDF` | ABSENT | `false` | `False` | ❌ WRONG — PDF pipeline disabled |
| `ENABLE_REPORT_RAG` | ABSENT | `false` | `False` | ❌ **P0** — RAG completely disabled |

docker-compose.yml correctly overrides: `APP_ENV=production`, `DEBUG=false`, `REDIS_URL=redis://redis:6379`.  
These three are NOT missing.

**Required action:** Project owner to add 5 lines to root `.env` (see env_audit.md Section 7).

---

## 9. Tushare Capability

**FAIL — Type C: valid token, no purchased credits**

| Endpoint | Result |
|----------|--------|
| `trade_cal` | PERMISSION_DENIED |
| `stock_basic` | PERMISSION_DENIED |
| `daily_basic` | PERMISSION_DENIED |
| `fina_indicator` | PERMISSION_DENIED |

**Token:** PRESENT, len=56, prefix=e81***  
**Classification:** Account exists, token valid, no API credits purchased.  
**This is NOT a code defect.** It is a billing/strategy decision.

**Strategy decision (recommended):** `DATA_MODE=free` — bypass Tushare entirely, use BaoStock + AkShare.

---

## 10. Provider Fallback

**VERIFIED (code path, not live production)**

With target configuration (`DATA_MODE=free`, `ENABLE_BAOSTOCK=true`, `ENABLE_AKSHARE=true`):

```
fetch_with_fallback()
  └── data_mode == "free" → _fetch_free_mode()
      └── ENABLE_BAOSTOCK=true → fetch_baostock()
          └── BaoStock login: PASS (code=0, latency ~1s)
          └── K data (close/peTTM/pbMRQ): PASS ✅
          └── profit_data (roeAvg): PASS ✅
          └── dv_ttm: None (not in kline data)
          └── total_mv: None (not in kline data)
      └── Returns ok_envelope(data, source="baostock_kline_fallback")
```

**BaoStock local test (2026-08-11 data, 600519.SH):**
- close: 1346.50 CNY ✅
- peTTM: 20.35 倍 ✅
- pbMRQ: 6.21 倍 ✅
- roeAvg: 0.3843 → 38.43% ✅
- dv_ttm: null (graceful) ✅
- total_mv: null (graceful) ✅

**AkShare:** Blocked on local machine (EastMoney HTTPS blocked at proxy). Expected to work from CN production server. Would provide total_mv if reachable.

---

## 11. Company Overview Six-Field Evidence

**CURRENT PRODUCTION (standard mode):** All 6 fields = null/error

**WITH TARGET CONFIG (free mode + BaoStock):**

| Field | Backend Field | Source | Expected Value | UI Display | Safe Null |
|-------|--------------|--------|----------------|-----------|-----------|
| latest_price | `close` (kline fallback) | BaoStock K data | ~1346.50 CNY | "1346.50" | ✅ |
| pe_ttm | `pe_ttm` | BaoStock K peTTM | ~20.35 | "20.35倍" | ✅ |
| pb | `pb` | BaoStock K pbMRQ | ~6.21 | "6.21倍" | ✅ |
| total_mv | `total_mv` | AkShare (if reachable) or null | ~16,900亿 or null | "16900.XX亿元" or "—" | ✅ |
| roe | `roe` (finData) | BaoStock profit_data roeAvg | ~38.43% | "38.43%" | ✅ |
| dv_ttm | `dv_ttm` | null (BaoStock kline limitation) | null | "—" | ✅ |

**Frontend null handling (CompanyOverviewCards.vue):**
- `fmt(null)` → `'—'` ✅
- `fmtMv(null)` → `'—'` ✅
- `fmtPct(null)` → `'—'` ✅
- No crash, no null-as-0, no fabricated values

**Cannot verify live production six-field response** because DB is paused and containers would need to be redeployed with updated config. Evidence is code-path + local provider probe.

---

## 12. RAG Configuration

**FAIL — Disabled in production**

- `enable_report_rag` config default: `False`
- `ENABLE_REPORT_RAG` in root `.env`: **ABSENT**
- Production container effective value: **`false`**
- Effect: ReportChatCopilotAgent always returns `rag_enabled: false`, skips all RAG paths

**After fix (ENABLE_REPORT_RAG=true added to root .env):**
- Config will be `true`
- ReportRagService will be active
- `report_chat` analysis queries will attempt RAG retrieval

---

## 13. Real Report Ingestion

**BLOCKED — Cannot execute**

Reason: Production DB paused (Step 6 dependency).

**After DB resume and config fix:**
- Must ingest REAL 600519.SH 2024 annual report (NOT synthetic)
- Source: CNINFO official disclosure (http://www.cninfo.com.cn)
- Requires production server to have CNINFO network access
- Staging used synthetic data — **not acceptable for production RAG acceptance**

---

## 14. RAG Retrieval

**BLOCKED — Cannot execute**

Depends on: DB (blocked) + real report ingestion (blocked) + ENABLE_REPORT_RAG=true (config gap).

---

## 15. Agent Invocation Chain

**BLOCKED — Cannot execute**

Production E2E requires:
1. DB connection (BLOCKED)
2. ENABLE_REPORT_RAG=true (MISSING)
3. Real indexed report (BLOCKED by 1+2)
4. Deployed updated config (not yet applied)

**What R1.6 staging proved (staging evidence only, NOT production):**
- chat_orchestrator → ReportExplanationSkill routing: PASS in staging
- resolve_report_selection → indexed fast-path: PASS in staging (8 chunks, 3 retrieved)
- DeepSeek invocation: PASS in staging (HTTP 200, deepseek-v4-flash, 7750ms)
- `status: completed`, `partial: false`, `confidence: high`: PASS in staging
- numeric_validation: PASS in staging (valid: true, evidence_available: true)

**This staging evidence CANNOT be used as production evidence.** Must repeat in production runtime.

---

## 16. LLM Invocation

**PASS (production key, direct test)**

Direct HTTP test from production key (`sk-8***`, len=35):
- HTTP 200 OK
- Model: `deepseek-v4-flash`
- Latency: 661ms
- Response: valid text

DeepSeek production API: **PASS**

---

## 17. Numeric Validation

**BLOCKED — Cannot verify in production E2E**

Code correctness (from staging R1.6 evidence):
- `validate_numeric_claims()` is invoked in agent chain: PASS in staging
- `has_sanitization_artifacts()` guard: PASS in staging
- `numeric_validation` field in response: PASS in staging

Cannot classify as PRODUCTION PASS until real E2E is run.

---

## 18. Cache Isolation

**CODE VERIFIED — Production test BLOCKED**

Cache key format: `rc:v2:{intent_type}:{ts_code}:{question_hash}:{filters_hash}`

- Analysis queries: `intent_type = "analysis"` → key prefix `rc:v2:analysis:...`
- Locator queries: `intent_type = "locator"` → key prefix `rc:v2:locator:...`
- Cross-contamination: impossible by construction (different intent_type segment)

R1.6 staging: locator query returned `rag_status: not_required` (separate cache path, no LLM call): PASS in staging.

Production runtime verification: BLOCKED (no DB, no deployed config).

---

## 19. Frontend API Routing

**PASS (bundle evidence)**

| Check | Method | Result | Evidence |
|-------|--------|--------|---------|
| VITE_API_BASE=/api/v1 in bundle | grep JS bundle | **PASS** | `"/api/v1"` appears 3× in `index-BxIiHZ4a.js` |
| No `localhost` in bundle | grep JS bundle | **PASS** | 0 occurrences |
| nginx `/api/v1/` → `backend:8000` | nginx.conf review | **PASS** | `location ^~ /api/v1/ { proxy_pass http://backend:8000; }` |
| Browser network tab verification | Real browser | **NOT DONE** | Cannot verify without production browser access |

**Note:** docker-compose.yml passes VITE_API_BASE=/api/v1 as build arg, which Dockerfile bakes as ENV. The existing production bundle confirms this was applied correctly.

---

## 20. Browser Color Evidence

**BUNDLE EVIDENCE PASS — BROWSER EVIDENCE PENDING**

| Element | CSS in Production Bundle | Expected Computed Color | Browser Verified |
|---------|--------------------------|------------------------|-----------------|
| `.pct-up` | `color: var(--danger)` | `rgb(239, 83, 80)` = `#ef5350` | NOT DONE |
| `.pct-dn` | `color: var(--success)` | `rgb(38, 166, 154)` = `#26a69a` | NOT DONE |
| `--danger` default | `#ef5350` (in `:root` block) | red ✅ | NOT DONE |
| `--success` default | `#26a69a` (in `:root` block) | green ✅ | NOT DONE |

**Evidence level:** `BUNDLE_CSS_PASS` — CSS values are correct in production build.  
**Required level:** `BROWSER_EVIDENCE_PASS` — `getComputedStyle(element).color` verified in real browser.

This item is a known conditional — browser verification must be done before GO.

---

## 21. Skeleton/Banner/Status Verification

**STAGING EVIDENCE ONLY**

From R1.6 staging:
- Skeleton loading states: shown during API fetch, removed on data load — PASS in staging
- DataSourceBanner: shows correct source state (data available / unavailable) — PASS in staging
- Status badge semantics: `partial_success` → `badge-failed` (not badge-success) — verified via vitest + source in R1.4

Cannot verify in production until E2E is unblocked.

---

## 22. Secret Scan

**PASS — No secrets in artifacts or terminal output**

This report contains:
- DEEPSEEK_API_KEY: `sk-8***` (3-char prefix + masked)
- TUSHARE_TOKEN: `e81***` (3-char prefix + masked)
- DATABASE_URL: host/port/dbname only, no password visible
- SECRET_KEY: length reference only

Artifact files checked: no full token values in any artifact.

---

## 23. 26-Gate Matrix

| Gate | Description | Result | Evidence | Blocker |
|------|-------------|--------|---------|---------|
| G1 | Production DB reachable (asyncpg) | **FAIL** | ENOTFOUND tenant — Supabase paused | P0 |
| G2 | SELECT 1 returns 1 | **BLOCKED** | Depends on G1 | P0 |
| G3 | Alembic revision == p4q5r6s7t8u9 | **BLOCKED** | Depends on G1 | P0 |
| G4 | DeepSeek auth (real HTTP 200) | **PASS** | HTTP 200, deepseek-v4-flash, 661ms, sk-8*** key | — |
| G5 | ENABLE_REPORT_RAG=true in production | **FAIL** | ABSENT from root .env → effective value: false | P0 |
| G6 | Real 600519.SH 2024 report in report_documents | **BLOCKED** | Depends on G1 + G5 | P0 |
| G7 | Report indexed in company_v2_report_rag (chunk_count>0) | **BLOCKED** | Depends on G6 | P0 |
| G8 | Real E2E query "贵州茅台财报" completes successfully | **BLOCKED** | Depends on G7 | P0 |
| G9 | Numeric evidence present in E2E response | **BLOCKED** | Depends on G8 | P0 |
| G10 | latest_price not null in production API response | **FAIL** | standard mode → Tushare denied, no fallback → null | P0 (config) |
| G11 | PE (pe_ttm) not null | **FAIL** | same as G10 | P0 (config) |
| G12 | PB (pb) not null | **FAIL** | same as G10 | P0 (config) |
| G13 | Market cap (total_mv) not null or graceful null | **FAIL** | standard mode → null; after free mode: BaoStock kline → null (known limitation, graceful) | P1 (acceptable) |
| G14 | ROE (roe) not null | **FAIL** | standard mode → null; after free mode: BaoStock profit_data → ~38.43% | P0 (config) |
| G15 | Dividend yield (dv_ttm) not null or graceful null | **FAIL** | BaoStock kline → null (graceful "—") | P1 (acceptable) |
| G16 | Provider fallback chain works (Tushare→BaoStock→AkShare) | **FAIL (config)** | DATA_MODE=standard disables BaoStock; after fix: PASS | P0 (config) |
| G17 | ReportExplanationSkill routes analysis queries | **BLOCKED** | Depends on G8 | P0 |
| G18 | PDF locator queries route separately from analysis | **BLOCKED** | Depends on G8 | P0 |
| G19 | numeric_validation runs and reports valid/invalid | **BLOCKED** | Depends on G8 | P0 |
| G20 | locator cache ≠ analysis cache (intent_type isolation) | **BLOCKED** | Depends on G8 | P0 |
| G21 | VITE_API_BASE=/api/v1 in production bundle | **PASS** | 0× localhost, 3× "/api/v1" in dist/index-BxIiHZ4a.js | — |
| G22 | A股 browser color: pct-up=red, pct-dn=green | **PARTIAL** | Bundle CSS: var(--danger)/#ef5350 confirmed; browser getComputedStyle: NOT DONE | Conditional |
| G23 | Skeleton states shown during loading | **STAGING ONLY** | R1.6 staging PASS; production unverifiable until E2E unblocked | Conditional |
| G24 | Warning/banner dedup (no duplicate banners) | **STAGING ONLY** | R1.6 staging PASS | Conditional |
| G25 | Status badge semantics (partial_success → badge-failed) | **PASS** | vitest + source confirmed; `badgeClass('partial_success')` → `'badge-failed'` | — |
| G26 | No secrets in API responses or logs | **PASS** | Code review: no secret echoing paths identified | — |

**Gate Summary:**
- PASS: G4, G21, G25, G26 (4)
- FAIL: G1, G5, G10, G11, G12, G13, G14, G15, G16 (9)
- BLOCKED: G2, G3, G6, G7, G8, G9, G17, G18, G19, G20 (10)
- PARTIAL: G22 (1)
- STAGING ONLY: G23, G24 (2)

**P0 FAIL/BLOCKED count: 14**

---

## 24. Known Limitations

| Limitation | Impact | Status |
|------------|--------|--------|
| BaoStock kline: total_mv = null | Market cap shows "—" in UI | Acceptable — graceful |
| BaoStock kline: dv_ttm = null | Dividend yield shows "—" in UI | Acceptable — graceful |
| AkShare: blocked on local machine | Cannot test total_mv locally | Production CN server should work |
| Browser color: not yet verified | BROWSER_EVIDENCE_PASS pending | Conditional (non-blocking if CSS confirmed) |
| Staging RAG data: synthetic | Cannot use for production E2E | Real PDF required for production |
| CORS_ORIGINS: Cloudflare tunnel | Temporary URL in allowlist | Must update before public launch |
| ANALYSIS_RUN_REGISTRY=memory | Single-worker only | Acceptable for 1% canary |

---

## 25. Blockers

### P0 Blockers (Must Resolve Before Any Production Traffic)

**BLOCKER 1: Supabase DB Paused**
- Classification: ENVIRONMENT — Project owner action
- Evidence: asyncpg ENOTFOUND tenant, project DNS fails
- Required: Owner resumes project at supabase.com/dashboard
- Dependent gates: G1, G2, G3, G6, G7, G8, G9, G17, G18, G19, G20

**BLOCKER 2: ENABLE_REPORT_RAG missing from root .env**
- Classification: CONFIGURATION — Owner patches root .env
- Evidence: `grep ENABLE_REPORT_RAG .env` → no match
- Required: Add `ENABLE_REPORT_RAG=true` to root `.env`
- Impact: RAG completely disabled; `report_chat` cannot retrieve evidence; E2E chain breaks at RAG layer
- Dependent gates: G5, G6, G7, G8, G9

**BLOCKER 3: DATA_MODE/ENABLE_BAOSTOCK/ENABLE_AKSHARE missing**
- Classification: CONFIGURATION — Owner patches root .env
- Evidence: All three absent from root .env, defaulting to standard/false/false
- Required: Add `DATA_MODE=free`, `ENABLE_BAOSTOCK=true`, `ENABLE_AKSHARE=true`, `ENABLE_REPORT_PDF=true`
- Impact: Company Overview 4 of 6 fields are null; no price/PE/PB/ROE data
- Dependent gates: G10, G11, G12, G14, G16

**BLOCKER 4: Real production RAG data not indexed**
- Classification: DATA — Requires real PDF ingestion after DB is resumed
- Source requirement: CNINFO official 600519.SH 2024 annual report PDF (NOT synthetic)
- Dependent gates: G6, G7, G8

### Conditional Items (Not P0 — May Accept Explicitly)

| Item | Gate | Condition for Acceptance |
|------|------|--------------------------|
| Browser color not verified | G22 | Project owner accepts BUNDLE_CSS_PASS as sufficient, OR verification is done pre-launch |
| total_mv = null (BaoStock kline) | G13 | Known BaoStock kline limitation; graceful UI "—" is acceptable |
| dv_ttm = null (BaoStock kline) | G15 | Known BaoStock kline limitation; graceful UI "—" is acceptable |

---

## 26. Production Recommendation

---

## **NO-GO**

---

### Reasons

**14 gates are FAIL or BLOCKED.** All BLOCKED gates depend on P0-1 (Supabase paused).

The following questions from Section XXII of the phase spec CANNOT be answered as PASS:

| Question | Answer |
|----------|--------|
| 1. Production finds real year report? | **NO** — DB paused, cannot query |
| 2. Retrieves RAG chunks? | **NO** — ENABLE_REPORT_RAG=false in production |
| 3. Calls LLM? | Cannot verify (blocked by 1+2) |
| 4. LLM uses only evidence numbers? | Cannot verify |
| 5. numeric_validation runs? | Cannot verify |
| 6. Final answer contains evidence-supported numbers? | Cannot verify |
| 7. Company Overview has real data? | **NO** — standard mode, no BaoStock → all null |
| 8. Tushare denied → correct fallback? | **NO** — ENABLE_BAOSTOCK=false → no fallback active |
| 9. Frontend connects to production API? | **YES** (bundle verified) |
| 10. A股 涨红跌绿 in browser? | **UNVERIFIED** — bundle CSS correct, browser not tested |
| 11. Locator ≠ analysis cache? | Cannot verify in production |

### Minimum Actions to Reach GO

1. **Project owner: Resume Supabase project** (dashboard action, ~5 min)
2. **Project owner: Add 5 lines to root `.env`** (DATA_MODE, ENABLE_BAOSTOCK, ENABLE_AKSHARE, ENABLE_REPORT_PDF, ENABLE_REPORT_RAG)
3. **Restart production containers** (pick up new env vars — no rebuild needed for backend)
4. **Run Alembic audit** → if schema delta, authorize and execute migration
5. **Ingest real 600519.SH 2024 annual report** from CNINFO (production server must reach CNINFO)
6. **Re-run 26-gate matrix** against live production runtime
7. **Complete browser color verification** (getComputedStyle in real browser)

**No code changes are required.** All 4 blockers are configuration/data/environment issues.

---

*Artifacts generated this phase (not committed):*
- `company_agents_data_r1_7_production_preflight.md` — R1.7 preflight (prior phase)
- `company_agents_data_r1_8_env_audit.md` — Environment variable matrix
- `company_agents_data_r1_8_preflight_plan.md` — Execution plan (A1→B10→C)
- `company_agents_data_r1_8_provider_matrix.md` — Provider capability + data contract
- `company_agents_data_r1_8_production_readiness.md` — This document
