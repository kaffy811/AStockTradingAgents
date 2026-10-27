# Phase 6W-R1.7 Production Preflight / Production Readiness Audit

**Generated:** 2026-08-10  
**HEAD SHA:** a542bc1  
**Branch:** release/demo-staging  
**Auditor role:** Senior Release Engineer (read-only audit — no code or config changes)  
**Production environment tested:** Credentials and providers tested from local machine using root `.env` (the docker-compose production env source). No live production server is accessible.

---

## I. PRODUCTION ENVIRONMENT SCOPE CLASSIFICATION

| Environment | Classification | Evidence |
|-------------|---------------|---------|
| Local machine (this audit) | VERIFIED_STAGING_ONLY | Runs staging containers on 127.0.0.1:18000/18080 |
| Production Docker deploy | BLOCKED_NO_ACCESS | No live server IP/hostname found in config; production server not reachable from this machine |
| Supabase production DB | BLOCKED_NO_ACCESS | `ENOTFOUND tenant/user` error on asyncpg connect; project status UNCERTAIN (likely paused) |
| Production DeepSeek API | VERIFIED_PRODUCTION | Key from root `.env` tested via direct HTTP → HTTP 200, model authenticated |
| Production Tushare API | VERIFIED_PRODUCTION | Token from root `.env` tested via direct API → ALL 4 endpoints: PERMISSION DENIED |

**Critical principle:** Results classified individually. Staging success DOES NOT imply production readiness.

---

## II. ENV FILE SOURCE ANALYSIS

### Root `.env` → loaded by `docker-compose.yml` (production)

| Key | Status | Value/Notes |
|-----|--------|-------------|
| `DEEPSEEK_API_KEY` | PRESENT | len=35 (20–40), prefix sk-*** |
| `TUSHARE_TOKEN` | PRESENT | len=56 (>40), prefix e81*** |
| `DATABASE_URL` | PRESENT | Supabase async pooler, ap-northeast-2 |
| `SECRET_KEY` | PRESENT | len=64 (>40), hex |
| `CORS_ORIGINS` | PRESENT | 3 origins: Cloudflare tunnel + localhost:3000 + 127.0.0.1:3000 |
| `APP_ENV` | PRESENT | `development` — overridden to `production` by docker-compose |
| `DEBUG` | PRESENT | `true` — overridden to `false` by docker-compose |
| `ENABLE_REPORT_RAG` | **MISSING** | Defaults to `False` — **RAG disabled in production** |
| `ENABLE_REPORT_PDF` | **MISSING** | Defaults to `False` — **PDF pipeline disabled** |
| `DATA_MODE` | **MISSING** | Defaults to `standard` — **Tushare Pro primary** |
| `ENABLE_BAOSTOCK` | **MISSING** | Defaults to `False` — BaoStock disabled |
| `ENABLE_AKSHARE` | **MISSING** | Defaults to `False` — AkShare fallback disabled |

### `backend/.env` — NOT loaded by docker-compose (development only)

Contains `DATA_MODE=free`, `ENABLE_BAOSTOCK=true`, `ENABLE_AKSHARE=true`, `ENABLE_REPORT_PDF=true` — none of these reach the production container.

### docker-compose.yml explicit overrides

```yaml
environment:
  - REDIS_URL=redis://redis:6379
  - APP_ENV=production
  - DEBUG=false
```

---

## III. P0 — PRODUCTION TUSHARE ACCESS

**Token source:** Root `.env`, prefix e81***, len=56 (>40 chars)  
**Same token** as used in staging (confirmed matching prefix and length)

| Endpoint | HTTP Result | Tushare Code | Permission Error | Success |
|----------|------------|--------------|-----------------|---------|
| `trade_cal` | API call | Error | **YES** — "没有接口访问权限" | FAIL |
| `stock_basic` | API call | Error | **YES** — "没有接口访问权限" | FAIL |
| `daily_basic` | API call | Error | **YES** — "没有接口访问权限" | FAIL |
| `fina_indicator` | API call | Error | **YES** — "没有接口访问权限" | FAIL |

**Root cause classification:** Type C — Token valid but endpoint permission unavailable (no purchased Tushare Pro credits)

**Critical finding:** The original user-visible error "您没有接口(fina_indicator)访问权限" is **confirmed unfixed**. The production Tushare token cannot access ANY tested endpoint.

**Production impact:**
- `DATA_MODE` defaults to `standard` in production → Tushare is the **primary** provider
- `ENABLE_AKSHARE=False` (default) → AkShare fallback **disabled**
- Result: Company Overview fields (PE, PB, market cap) will return null from provider chain failure, not from graceful degradation

**Fallback behavior if Tushare fails in standard mode:**
```
Tushare daily_basic → PERMISSION DENIED
  ↓ (if ENABLE_AKSHARE=True) → AkShare
  ↓ (if ENABLE_AKSHARE=False) → err_envelope(primary_reason)
```
In production (ENABLE_AKSHARE=False): no fallback. PE/PB/Market Cap = `null`.  
In staging (DATA_MODE=free, ENABLE_AKSHARE=True): AkShare attempted but blocked by Docker network.

**Gate G2: FAIL** — Production `fina_indicator` permission denied.

---

## IV. P0 — PRODUCTION DEEPSEEK AUTHENTICATION

**Key source:** Root `.env`, prefix sk-***, len=35 (20–40 chars)

| Property | Value |
|----------|-------|
| Key presence | PRESENT |
| HTTP status | 200 OK |
| Authentication | SUCCESS |
| Model returned | `deepseek-v4-flash` |
| Latency | 661ms |
| Tokens | prompt=90, completion=5 |
| Error category | None |

**Classification:** VERIFIED_PRODUCTION  
**Gate G4: PASS** — Production DeepSeek authentication confirmed via direct HTTP call.

---

## V. P0 — PRODUCTION RAG DATA

**Supabase DB connectivity:** BLOCKED_NO_ACCESS  
- DNS: RESOLVED (43.202.154.182, 15.164.188.235)  
- TCP port 6543: REACHABLE (latency 242ms)  
- asyncpg connect: `InternalServerError: (ENOTFOUND) tenant/user postgres.qvpdtnazhxbfifrjdfdf not found`  
- Supabase REST HTTPS: SSL EOF (project appears paused — Supabase free-tier auto-pauses after 7 days inactivity)

**Cannot verify production report data.** All report table contents (report_documents, company_v2_report_rag_documents, company_v2_report_rag_chunks) are UNKNOWN.

**Additional critical finding:** Even if DB were accessible, `ENABLE_REPORT_RAG=False` (production default) means report chat would return `rag_status: unavailable` for all queries without exception.

**Gate G5 (RAG enabled in production):** FAIL — ENABLE_REPORT_RAG not set in root `.env`, defaults to False.  
**Gate G6 (real 600519 report indexed):** BLOCKED_NO_ACCESS — DB unreachable.  
**Gate G7 (real RAG chunks available):** BLOCKED_NO_ACCESS — DB unreachable.

---

## VI. REAL END-TO-END PRODUCTION QUERY

**Cannot execute.** Production server is not accessible from this machine. Supabase DB is not connectable.

**Staging trace (VERIFIED_STAGING_ONLY, synthetic data):**

| Stage | Status | Evidence |
|-------|--------|---------|
| chat_orchestrator | INVOKED | POST /api/v1/stock/600519/report-chat HTTP 200 |
| intent classification | INVOKED | classification="analysis" from `_classify_question()` |
| ReportExplanationSkill | N/A | Route goes directly to ReportChatCopilotAgent (not through orchestrator skills) |
| resolve_report_selection | INVOKED | `selection_reason: latest_formal_report`, report_id=1 |
| company_v2_report_rag (indexed fast path) | INVOKED | `indexed_fast_path: True`, 3 chunks retrieved |
| Data Agent / Analysis Agent / Review Agent | **NOT_INVOKED** | report-chat uses ReportChatCopilotAgent directly, not the analysis agent chain |
| LLM (DeepSeek) | INVOKED | `llm_model: deepseek-v4-flash`, HTTP 200 |
| validate_numeric_claims | INVOKED | `numeric_validation.valid: True` |
| has_sanitization_artifacts | INVOKED | `has_artifacts: False` |
| Final response | status=completed, partial=False, confidence=high | HTTP 200 |

**Agent chain clarification:** The "贵州茅台最新财报表现如何？" query routes to `POST /api/v1/stock/600519/report-chat` → `ReportChatCopilotAgent`. This is a separate pipeline from the comprehensive analysis agents (Data Agent → Analysis Agent → Review Agent). The general chat orchestrator's `_handle_latest_report_setup_direct` is invoked only when the report-chat query arrives via the main chat endpoint.

**Gate G9 (Data Agent invocation proven):** NOT_APPLICABLE for report-chat endpoint.  
**Gate G10 (Analysis Agent invocation proven):** NOT_APPLICABLE for report-chat endpoint.  
**Gate G11 (Review Agent invocation proven):** NOT_APPLICABLE for report-chat endpoint.

---

## VII. REAL DATA CORRECTNESS (STAGING)

**Source type:** Staging synthetic chunks — NOT extracted from real 600519.SH PDF

| Numeric claim in answer | Value | Classification | Source |
|------------------------|-------|----------------|--------|
| 营业收入 | 1,738.05亿元 | SUPPORTED_BY_SOURCE | Chunk 0: synthetic |
| Revenue growth | +15.05% | SUPPORTED_BY_SOURCE | Chunk 0: synthetic |
| 归母净利润 | 862.96亿元 | SUPPORTED_BY_SOURCE | Chunk 0: synthetic |
| Net profit growth | +14.82% | SUPPORTED_BY_SOURCE | Chunk 0: synthetic |
| ROE | 34.2% | SUPPORTED_BY_SOURCE | Chunk 2: synthetic |
| 毛利率 | 91.5% | SUPPORTED_BY_SOURCE | Chunk 2: synthetic |
| EPS | 68.72元 | SUPPORTED_BY_SOURCE | Chunk 4: synthetic |

**numeric_validation.valid = True** — correct, numbers trace to synthetic chunk text.

**Caveat:** The synthetic chunks contain plausible but not authoritative 2024 Maotai data. The real 2024 annual report (official PDF) was not downloaded or indexed (EastMoney/CNINFO blocked in Docker staging network). Production "data correctness" is unverifiable until real report is indexed.

**Classification:** VERIFIED_STAGING_ONLY — pipeline integration proven; real data accuracy NOT verified.

---

## VIII. COMPANY OVERVIEW — SIX FIELDS (PRODUCTION)

**Provider chain in production (DATA_MODE=standard, ENABLE_AKSHARE=False):**

| Field | Primary Provider | Result | Fallback | Final Status |
|-------|-----------------|--------|----------|-------------|
| `latest_price` | Tushare daily_basic | PERMISSION DENIED | None (AkShare disabled) | null |
| `pe_ttm` | Tushare daily_basic | PERMISSION DENIED | None | null |
| `pb` | Tushare daily_basic | PERMISSION DENIED | None | null |
| `total_market_cap` | Tushare daily_basic | PERMISSION DENIED | None | null |
| `roe` | Tushare fina_indicator | PERMISSION DENIED | None | null |
| `dividend_yield_ttm` | Tushare daily_basic | PERMISSION DENIED | None | null |

**All six fields will be null in production** due to Tushare permission failure and disabled fallbacks.

**Root cause:** Type C — Token valid, endpoint permission denied. Not a code bug.

**Note on BaoStock:** BaoStock login succeeded (35s latency), but `query_history_k_data_plus` with `peTTM,pbMRQ` fields returns code=10004012 (no data) for 2025–2026 date ranges. Only `query_profit_data(year=2024, quarter=4)` returns real financial data (ROE=38.4%, gpMargin=91.9%).

**Gate G14 (Company Overview six fields):** FAIL — all six null in production.

---

## IX. PROVIDER FALLBACK FORENSICS

| Provider | Config in Production | Failure Mode | Fallback Available |
|---------|---------------------|-------------|-------------------|
| Tushare Pro (standard mode primary) | Enabled, token present | All endpoints: permission denied | No (only if ENABLE_AKSHARE=True) |
| AkShare stock_zh_a_spot_em | **Disabled** (ENABLE_AKSHARE=False default) | Not attempted | N/A |
| BaoStock | **Disabled** (ENABLE_BAOSTOCK=False default) | Not attempted | N/A |
| yfinance | Not configured as fallback for CN market | N/A | N/A |

**Answer to required question:** "If Tushare fina_indicator is unavailable in production, does the system continue safely?"

**YES, the system continues safely — but with ALL valuation fields null.**  
- No unhandled exception occurs (permission errors are caught)  
- Frontend shows "—" or DataSourceBanner when data is unavailable  
- No 500 errors  
- User-facing experience: Company Overview shows all valuation metrics as unavailable

This is degraded but non-crashing behavior.

---

## X. PRODUCTION FEATURE FLAGS

| Flag | root `.env` | Production Default | Impact |
|------|------------|-------------------|--------|
| `ENABLE_REPORT_RAG` | NOT SET | False | **Report chat returns "RAG unavailable" for all queries** |
| `ENABLE_REPORT_PDF` | NOT SET | False | PDF download/index pipeline disabled |
| `DATA_MODE` | NOT SET | "standard" | Tushare Pro primary (fails); BaoStock/AkShare disabled |
| `ENABLE_BAOSTOCK` | NOT SET | False | BaoStock unavailable as fallback |
| `ENABLE_AKSHARE` | NOT SET | False | AkShare unavailable as fallback |
| `ENABLE_DEEPSEEK_REASONER` | true | true (root .env) | Reasoner model enabled |
| `ANALYSIS_RUN_REGISTRY` | memory | memory (root .env) | Single-worker only; Redis registry not enabled |
| `DEFAULT_ANALYSIS_ENGINE` | custom_coordinator | custom_coordinator (root .env) | Stable engine |
| `CORS_ORIGINS` | 3 entries | 3 entries (root .env) | Cloudflare tunnel + localhost |

---

## XI. FRONTEND PRODUCTION BUILD

**Evidence from locally built dist/ (VITE_API_BASE=/api/v1 per frontend/.env.production):**

| Check | Result | Classification |
|-------|--------|---------------|
| `/api/v1` in bundle | YES (5 chunks) | VERIFIED_STAGING_ONLY |
| `localhost:8000` in bundle | NO | VERIFIED_STAGING_ONLY |
| `localhost:18000` in bundle | NO | VERIFIED_STAGING_ONLY |
| nginx proxy `/api/v1/` → `backend:8000` | Configured in nginx.conf | VERIFIED_STAGING_ONLY |
| Production server nginx running | BLOCKED_NO_ACCESS | Cannot verify |

**Note:** `frontend/.env.production` committed at HEAD a542bc1. Future production builds (via Dockerfile ARG `VITE_API_BASE=/api/v1`) are also correct.

---

## XII. A-SHARE COLOR BROWSER EVIDENCE

**Classification: BROWSER_NOT_AVAILABLE**

| Evidence type | Value | Classification |
|--------------|-------|----------------|
| Source code `.pct-up` | `color: var(--danger)` | VERIFIED_STAGING_ONLY |
| Built CSS (dist/) `.pct-up[data-v-*]` | `color:var(--danger)` | VERIFIED_STAGING_ONLY |
| Built CSS (dist/) `.pct-dn[data-v-*]` | `color:var(--success)` | VERIFIED_STAGING_ONLY |
| Browser `getComputedStyle()` | NOT PERFORMED | BROWSER_NOT_AVAILABLE |
| Vitest test `phase6wR1P1aColorConvention` | 52/52 PASS | VERIFIED_STAGING_ONLY |
| `--danger` resolved value (default theme) | `#ef5350` (red) | CSS variable |
| `--success` resolved value (default theme) | `#26a69a` (green) | CSS variable |

Manual browser `getComputedStyle()` verification required before 1% live. Playwright not installed in staging environment.

---

## XIII. CACHE ISOLATION

**Key format (verified in source, committed at a542bc1):**
```
rc:v1:{intent_type}:{ts_code}:{question_hash}:{filters_hash}
intent_type ∈ {"analysis", "locator"}
```

**Staging verification (VERIFIED_STAGING_ONLY):**
- Analysis query → `rc:v1:analysis:...` key
- Locator query → `rc:v1:locator:...` key (returns `rag_status: not_required`)
- Cross-contamination: not observed

**Production:** Cannot verify without production Redis access. Code is correct; runtime behavior depends on correct REDIS_URL in production container.

**Gate G19 (cache intent isolation):** PASS at code level; BLOCKED_NO_ACCESS at production runtime.

---

## XIV. STAGING/PRODUCTION CREDENTIAL ISOLATION

| Check | Result | Classification |
|-------|--------|----------------|
| Production `DATABASE_URL` host | `aws-1-ap-northeast-2.pooler.supabase.com` (not localhost) | PASS |
| Production DB password contains `staging_changeme` | NO | PASS |
| Production DB user contains `staging_user` | NO | PASS |
| Staging `staging_changeme` in any production env | NO | PASS |
| Root `.env` TUSHARE_TOKEN = backend/.env TUSHARE_TOKEN | YES (same token, e81*** prefix, len=56) | OK — same token, different env files |
| Root `.env` DEEPSEEK_API_KEY = backend/.env (from staging) | YES (same key, sk-81*** → sk-*** prefix, len=35) | OK |

**No staging credentials detected in production configuration.**

**Gate G20 (production/staging credential isolation):** PASS

---

## XV. DOCKER / NETWORK

| Endpoint | From Local Machine | Notes |
|----------|-------------------|-------|
| PostgreSQL (Supabase) | TCP REACHABLE, auth FAIL | Project may be paused; ENOTFOUND tenant |
| Redis (production) | NOT_ACCESSIBLE | redis://redis:6379 only inside Docker |
| Tushare API (https://api.tushare.pro) | HTTP 200 reachable | Permission denied on all endpoints |
| AkShare/EastMoney HTTPS | Connection drops on HTTPS | GFW or proxy; HTTP 404 (reachable) |
| AkShare/EastMoney HTTP | HTTP 200/404 | Accessible without proxy |
| DeepSeek API | HTTP 200/401 | Authenticated successfully |

---

## XVI. OBSERVABILITY

| Signal | Code path | Production observable |
|--------|-----------|----------------------|
| `validate_numeric_claims` failures | `report_chat_copilot_agent.py:1565` | YES — emitted in `numeric_validation` response field |
| `NUMERIC_EVIDENCE_MISSING` | `report_chat_copilot_agent.py:1580` | YES — in `errors[]` array |
| Tushare permission failures | `base.py` permission guard | YES — logged at WARNING, user sees "部分财务指标暂不可用" |
| RAG unavailable | `_compute_rag_status()` | YES — `rag_status: "unavailable"` in response |
| DeepSeek auth failures | LLM call layer | YES — surfaced as partial=True, error in errors[] |
| Provider fallback | `base.py` fallback chain | YES — logged |
| `partial_success` badge | Frontend `badgeClass()` | YES — maps to `badge-failed` (not `badge-success`) |
| Source chunk count | `source_chunks` response field | YES |
| Agent invocation state | `performance_meta.indexed_fast_path` | YES |

No secret leakage paths identified in logs or API responses.

**Gate G21 (observability):** PASS at code level.  
**Gate G22 (no secret leakage):** PASS — no credential echoing in response or log paths observed.

---

## XVII. 22-GATE PRODUCTION GATE MATRIX

| Gate | Description | Result | Evidence | Environment | Classification | Impact | Recommended Action |
|------|-------------|--------|---------|-------------|---------------|--------|-------------------|
| G1 | Production Tushare token present | PARTIAL | PRESENT (len=56, e81***) but NO permissions | VERIFIED_PRODUCTION | Configuration issue | HIGH — all fundamentals null | Purchase Tushare Pro points or switch DATA_MODE |
| G2 | Production `fina_indicator` permission | **FAIL** | "没有接口访问权限" on ALL 4 endpoints tested | VERIFIED_PRODUCTION | Type C: permission denied | HIGH — financial data unavailable | Purchase Tushare Pro credits |
| G3 | Production `daily_basic` access | **FAIL** | Permission denied | VERIFIED_PRODUCTION | Type C | HIGH | Same as G2 |
| G4 | Production DeepSeek authentication | **PASS** | HTTP 200, model=deepseek-v4-flash, latency=661ms | VERIFIED_PRODUCTION | — | None | — |
| G5 | Production RAG enabled | **FAIL** | ENABLE_REPORT_RAG not in root .env → defaults False | CONFIGURATION_MISSING | Missing env var | CRITICAL — report chat broken in production | Add ENABLE_REPORT_RAG=true to root .env |
| G6 | Real 600519 report indexed | **BLOCKED** | Supabase DB unreachable (ENOTFOUND — likely paused) | BLOCKED_NO_ACCESS | DB inaccessible | HIGH | Resume Supabase project; verify report indexing |
| G7 | Real RAG chunks available | **BLOCKED** | DB unreachable | BLOCKED_NO_ACCESS | — | HIGH | Same as G6 |
| G8 | Real E2E report analysis | **BLOCKED** | No production server accessible | BLOCKED_NO_ACCESS | — | HIGH | Run against production server post-deploy |
| G9 | Data Agent invocation proven | NOT_APPLICABLE | report-chat uses ReportChatCopilotAgent, not analysis pipeline | VERIFIED_STAGING_ONLY | Architecture clarification | None for report-chat | Document routing correctly |
| G10 | Analysis Agent invocation proven | NOT_APPLICABLE | Same as G9 | VERIFIED_STAGING_ONLY | — | None | — |
| G11 | Review Agent invocation proven | NOT_APPLICABLE | Same as G9 | VERIFIED_STAGING_ONLY | — | None | — |
| G12 | Numeric validation runtime proven | PASS (staging) | `validate_numeric_claims` called, valid=True, in response metadata | VERIFIED_STAGING_ONLY | — | None (code correct) | Re-verify with real production data |
| G13 | Real numeric claims source-supported | BLOCKED | Staging used synthetic chunks; production DB inaccessible | BLOCKED_NO_ACCESS | Cannot verify real data | HIGH | Index real 600519 report; re-run query |
| G14 | Company Overview six fields | **FAIL** | All 6 null: Tushare permission denied, AkShare disabled (default off) | VERIFIED_PRODUCTION | Type C + CONFIGURATION_MISSING | HIGH — blank Company Overview | Fix DATA_MODE + enable fallback in root .env |
| G15 | Provider fallback behavior | PARTIAL | Tushare→null (graceful, no crash). AkShare/BaoStock disabled in production | VERIFIED_PRODUCTION | Design gap | MEDIUM — no fallback chain active | Add DATA_MODE=free or ENABLE_AKSHARE=true to root .env |
| G16 | Production VITE_API_BASE | PASS (build) | /api/v1 in bundle, no localhost; Dockerfile ARG also correct | VERIFIED_STAGING_ONLY | — | None | Verify production nginx serving new bundle |
| G17 | Browser A-share color | BROWSER_NOT_AVAILABLE | CSS confirmed in source + dist; no Playwright | VERIFIED_STAGING_ONLY | — | LOW | Manual browser verify before 1% live |
| G18 | `partial_success` badge ≠ green | PASS | `badgeClass('partial_success')` → `badge-failed` verified in source + test | VERIFIED_STAGING_ONLY | — | None | — |
| G19 | Cache intent isolation | PASS (code) | `rc:v1:{intent_type}:...` format; staging confirmed locator/analysis separation | VERIFIED_STAGING_ONLY | — | None | — |
| G20 | Production/staging credential isolation | **PASS** | No `staging_changeme` or `staging_user` in production env | VERIFIED_PRODUCTION | — | None | — |
| G21 | Observability | PASS | All key signals emitted in response metadata and logs | VERIFIED_STAGING_ONLY | — | None | — |
| G22 | No secret leakage | PASS | No credential echoing in responses or logs | VERIFIED_STAGING_ONLY | — | None | — |

---

## XVIII. GO / NO-GO RULING

### Decision: **NO-GO**

**Reason:** Multiple P0 production gates fail. 1% production traffic MUST NOT start until all P0 items are resolved.

---

## XIX. BLOCKERS BEFORE 1% PRODUCTION

### P0-BLOCKER-1: ENABLE_REPORT_RAG missing from root `.env`

**Finding:** `ENABLE_REPORT_RAG` is not in root `.env`. Config.py default is `False`.  
**Impact:** Every report-chat query in production returns `rag_status: unavailable`, `error_code: COMPANY_V2_INDEX_NOT_FOUND`. The core feature does not work.  
**Fix:** Add `ENABLE_REPORT_RAG=true` to root `.env`.  
**Severity:** CRITICAL (feature completely broken).

### P0-BLOCKER-2: Tushare token has no API permissions

**Finding:** Token `e81***` (len=56) tested against `trade_cal`, `stock_basic`, `daily_basic`, `fina_indicator` — all return "您没有接口访问权限".  
**Impact:** In production (`DATA_MODE=standard`, `ENABLE_AKSHARE=False`), all Company Overview valuation fields are null. The original user-visible error is **not fixed**.  
**Fix option A:** Purchase Tushare Pro credits for this account.  
**Fix option B:** Add `DATA_MODE=free`, `ENABLE_BAOSTOCK=true`, `ENABLE_AKSHARE=true` to root `.env` (switches to BaoStock+AkShare providers). Note: BaoStock login takes ~35s; AkShare EastMoney may have connectivity issues in production region.  
**Severity:** CRITICAL (core data pipeline broken).

### P0-BLOCKER-3: Supabase production DB status uncertain

**Finding:** `asyncpg.connect()` fails with `ENOTFOUND tenant/user` despite TCP reachability. Supabase free-tier projects auto-pause after 7 days inactivity.  
**Impact:** Cannot verify: production DB schema, migration state, whether real 600519 reports are indexed, or whether any user data exists.  
**Fix:** Access Supabase dashboard → resume project → verify connectivity → confirm migration state → index 600519 report via API.  
**Severity:** CRITICAL (cannot confirm production data exists).

### P0-BLOCKER-4: Production feature flags not synced

**Finding:** Root `.env` is missing `DATA_MODE`, `ENABLE_BAOSTOCK`, `ENABLE_AKSHARE`, `ENABLE_REPORT_PDF`. These are in `backend/.env` (development only) but not loaded by docker-compose.  
**Impact:** Production behavior differs from staging behavior in all these dimensions.  
**Fix:** Sync required flags to root `.env` before production deployment.  
**Severity:** HIGH (silent behavioral difference between staging and production).

---

### Non-P0 Items (required before 1% live, not blocking audit)

**NP1:** Browser `getComputedStyle()` verification for A-share color convention — BROWSER_NOT_AVAILABLE. Manual verification required.

**NP2:** `CORS_ORIGINS` contains Cloudflare tunnel URL (`hugh-focusing-jet-urge.trycloudflare.com`) — this is a temporary tunnel. For production deployment to a permanent domain, CORS_ORIGINS must be updated to include the production domain.

**NP3:** `ANALYSIS_RUN_REGISTRY=memory` in root `.env` — single-worker only. Multi-worker production requires `ANALYSIS_RUN_REGISTRY=redis`.

**NP4:** Real 600519.SH annual report must be indexed into production DB (not synthetic staging data) before report-chat produces verified financial analysis.

---

## XX. ALL FAILURES AND LIMITATIONS SUMMARY

| ID | Issue | Severity | Environment | Status |
|----|-------|----------|-------------|--------|
| F1 | Tushare ALL endpoints: permission denied | P0 | VERIFIED_PRODUCTION | UNRESOLVED |
| F2 | ENABLE_REPORT_RAG missing → RAG disabled | P0 | CONFIGURATION_MISSING | UNRESOLVED |
| F3 | Supabase DB: ENOTFOUND (likely paused) | P0 | BLOCKED_NO_ACCESS | UNRESOLVED |
| F4 | DATA_MODE/ENABLE_AKSHARE/BAOSTOCK/PDF not in root .env | P0 | CONFIGURATION_MISSING | UNRESOLVED |
| F5 | Company Overview: all 6 fields null in production | P0 | VERIFIED_PRODUCTION | Consequence of F1+F4 |
| F6 | CORS_ORIGINS: Cloudflare tunnel URL (temporary) | HIGH | CONFIGURATION_MISSING | Review before live |
| F7 | ANALYSIS_RUN_REGISTRY=memory (single-worker) | MEDIUM | CONFIGURATION_MISSING | Review before live |
| F8 | Browser color verify: BROWSER_NOT_AVAILABLE | LOW | Pending | Manual required |
| F9 | Real 600519 report: not indexed (staging synthetic only) | HIGH | BLOCKED_NO_ACCESS | After DB resume |
| F10 | Production server: no known IP/hostname | HIGH | BLOCKED_NO_ACCESS | Owner must provide |
| L1 | EastMoney HTTPS blocked from local machine (proxy/GFW) | MEDIUM | ENVIRONMENT_ISSUE | Staging limitation only |
| L2 | BaoStock login latency: ~35s (slow) | LOW | ENVIRONMENT_ISSUE | Acceptable if primary |

---

## XXI. RECOMMENDED NEXT PHASE

**Phase 6W-R1.8 — Production Configuration Fix + DB Resume**

Required steps (in order):

1. **Fix root `.env`** (authorized by project owner):
   - Add `ENABLE_REPORT_RAG=true`
   - Add `ENABLE_REPORT_PDF=true`
   - Add `DATA_MODE=free`
   - Add `ENABLE_BAOSTOCK=true`
   - Add `ENABLE_AKSHARE=true`
   - Update `CORS_ORIGINS` for production domain

2. **Resume Supabase project** (via Supabase dashboard):
   - Navigate to project qvpdtnazhxbfifrjdfdf
   - Resume if paused
   - Verify `SELECT 1` connects
   - Verify migration HEAD matches current Alembic head

3. **Index 600519 real report** (via production API):
   - Run `POST /api/v1/reports/discover-latest?symbol=600519.SH`
   - Download → parse → index → verify chunk_count > 0
   - Re-run `POST /api/v1/stock/600519/report-chat` with real data

4. **Re-run all 22 gates** against production runtime.

5. **Manual browser color verification** (`.pct-up` getComputedStyle).

6. Only after all P0 gates PASS → issue GO for 1% production traffic.

---

## XXII. HEAD SHA AND FINAL STATUS

**HEAD SHA:** `a542bc1`  
**Branch:** `release/demo-staging`  
**Commit message:** `docs(phase6w): R1.5 runtime truth + R1.6 e2e acceptance (18/18 PASS)`

**R1.7 Production Preflight Decision: NO-GO**

P0 blockers found: 4  
P0 gates FAIL: G2, G3, G5, G6, G7, G14  
P0 gates BLOCKED: G6, G7, G8, G13  
P0 gates PASS: G4, G20  

**Do NOT start 1% production traffic until Phase 6W-R1.8 resolves all P0 blockers.**
