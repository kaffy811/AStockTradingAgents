# Release Notes — v1.0.0-rc2

**Tag:** `v1.0.0-rc2`  
**Date:** 2026-07-06  
**Branch:** master  
**Status:** Release Candidate — Code Complete

---

## Summary

RC-2 delivers the Company Tab professional financial report experience, a three-layer AI analysis pipeline, full DataEnvelope contract enforcement, and production-grade performance optimisations. All automated tests pass and the API contract is validated across three representative A-share stocks in both token-absent and permission-denied degradation modes.

---

## What's New in RC-2

### 1. Company Tab — Professional Financial Report (Phase 4E)

A full-page, two-column financial report view anchored to the Company tab of the Stock Detail page.

**P0 Panels (always attempted):**
- Valuation (估值分位) — PE/PB/PS/DY percentile
- Growth (成长能力) — Revenue/profit YoY trends
- Profitability (盈利能力) — Gross/net margin, ROE, ROA
- Cashflow Quality (现金流质量) — Operating cashflow vs net income
- Main Business (主营业务) — Revenue breakdown by segment
- Industry Rank (行业排名) — SQL window-function percentile ranking
- Dividend History (分红历史) — Per-share dividend timeline

**P1 Panels (enriched analysis):**
- Asset Structure (资产结构) — Fixed/current/intangible composition
- Solvency (偿债能力) — Current ratio, quick ratio, debt-to-assets
- Capital Occupation (资金占用) — Receivables, prepayments, accounts payable
- Operation Capability (营运能力) — Turnover ratios, cash cycle
- Dupont Analysis (杜邦分析) — ROE = Margin × Turnover × Leverage
- Major Holders (大股东) — Top-10 float holders, share concentration
- Equity Structure (股本结构) — Total/float/restricted share breakdown

**Architecture:**
- Left anchor navigation with IntersectionObserver scroll spy
- Smart loading: only fetches visible section modules
- `requestCache.js` — in-flight dedup + 5-min TTL cache
- `defineAsyncComponent` lazy loading — panel not in initial bundle
- Vite `manualChunks` — echarts / xlsx / vue-vendor isolated

### 2. AI Three-Layer Analysis Pipeline (Phase 3B)

```
DataAgent (deterministic)
    ↓  compressed financial facts
AnalysisAgent (DeepSeek LLM)
    ↓  structured JSON output
ReviewAgent (rule-based compliance)
    ↓  approved / revised / rejected
AiSummaryStrip.vue  ←  mode=summary (30 facts)
AiAnalysisCard.vue  ←  mode=full    (60 facts)
```

**ReviewAgent rules enforced server-side:**
- Severe banned words → rejected → safe placeholder displayed
- Mild violations → revised → text replacement
- Source module attribution check (`_check_source_modules`)
- Numeric hallucination detection (`_check_numeric_hallucination`)
- Analyst ratings misuse prevention (`_check_analyst_ratings_misuse`)
- Disclaimer auto-add when missing

**AI provider abstraction:** `settings.ai_api_key` / `settings.ai_enabled` / `settings.ai_provider` — decoupled from DeepSeek-specific env vars.

### 3. DataSourceBanner & Graceful Degradation

Four-type banner classification:
- `no_token` — TUSHARE_TOKEN not configured
- `etl_missing` — industry_rank_snapshot not populated
- `upstream_empty` — API call succeeded but returned no rows
- `generic` — catch-all partial with error list

All modules always return HTTP 200. Errors surface via `partial=True` + `data.reasons[]`. No 503 on missing token.

### 4. FundamentalEmptyReason Component

Unified empty-state with icon mapping (6 reason types), traceback stripping, optional retry button.

### 5. Excel / CSV Export (Phase 4E-3)

- Sheet name sanitization (31-char limit, illegal char strip)
- Duplicate sheet name prevention (`_2`, `_3` suffix)
- `null` → empty cell (no "null" string)
- Partial modules get "数据说明" notice rows at sheet top

### 6. Performance (Phase 5)

| Optimisation | Detail |
|---|---|
| `requestCache.js` | In-flight dedup + 5-min TTL |
| `useChartResize.js` | ResizeObserver composable, disposes on unmount |
| `defineAsyncComponent` | CompanyFundamentalsPanel not in first bundle |
| Vite manualChunks | echarts / xlsx / vue-vendor isolated chunks |
| PWA manifest | theme_color, standalone, icon entries |

### 7. Production Readiness Docs

- `docs/07_ai_agent_design.md` — AI architecture and compliance rules
- `docs/09_manual_e2e_checklist.md` — 10-section E2E checklist
- `docs/10_production_readiness.md` — production checklist
- `docs/11_rc2_validation_report.md` — RC-2/2B/2C validation findings
- `docs/13_akshare_fallback_validation_plan.md` — AkShare staging plan

---

## Validation Results

| Check | Result |
|---|---|
| Backend tests | **2,076 / 2,076 PASS** |
| Frontend build | ✓ clean, 2.49s |
| Main bundle (gzip) | 143 kB ✓ |
| CompanyFundamentalsPanel lazy chunk | 91 kB ✓ |
| ECharts chunk (gzip) | 382 kB (expected, cached) |
| API calls: 3 stocks × 16 modules | **48 / 48 HTTP 200** |
| HTTP 500 count | 0 ✓ |
| HTTP 503 count | 0 ✓ |
| partial envelopes with reasons | 42 / 42 ✓ |
| Investment advice violations | 0 ✓ |
| Token leak in responses | 0 ✓ |
| Traceback leak in responses | 0 ✓ |
| X-Data-Disclaimer header | ✓ present on all fundamentals endpoints |
| CORS | ✓ for configured origins |
| PostgreSQL | ✓ healthy |
| Redis | ✓ healthy |
| Alembic: current == head | ✓ `b8c3d9e2f5a1` |
| Permission-denied path validated | ✓ graceful, no crash |

---

## Known Limitations

### L-1 — Tushare Pro Subscription Required for Financial Rows

**Severity:** P1 — affects data completeness, not system stability.

The current token is a Tushare free-tier account. All financial statement APIs (`daily_basic`, `fina_indicator`, `income`, `balancesheet`, `cashflow`, etc.) require a Tushare Pro subscription with ≥ 2,000 points.

**Impact:** Company Tab shows `partial=True` with reason "Tushare 权限不足" for all financial panels. The DataSourceBanner correctly classifies and explains this. No crash, no 5xx.

**Resolution path:**
- Upgrade to Tushare Pro subscription, OR
- Activate AkShare fallback for staging validation (`ENABLE_AKSHARE=true` — see §L-2), OR
- Integrate an alternative authorised data source

### L-2 — AkShare Fallback Not Default in Production

AkShare is implemented as a fallback source and is available in the codebase (`ENABLE_AKSHARE=true`). It is **not** enabled by default in production for the following reasons:

1. Field-level schema parity between AkShare and Tushare output has not been fully validated in production load
2. AkShare data freshness and reliability SLA are not defined
3. A staging validation plan is documented in `docs/13_akshare_fallback_validation_plan.md`

**Production default:** `ENABLE_AKSHARE=false` — intentional.

### L-3 — CORS_ORIGINS Localhost-Only

Current configuration covers `localhost:3000–5174` and `127.0.0.1` variants only. A public staging or production domain must be added to `CORS_ORIGINS` in `backend/.env` before public deployment.

### L-4 — ETL Data Empty

`industry_rank_snapshot` is unpopulated. Industry ranking panels show `etl_missing` DataSourceBanner. ETL scripts are implemented and validated for graceful permission-denied exit; data population requires Tushare Pro.

### L-5 — AiSummaryStrip: AI Analysis Also Requires Token

The AI analysis pipeline calls financial data modules internally. Without real financial rows, the AI analysis returns `partial=True` with a safe placeholder — consistent with compliance requirements.

---

## Bugs Fixed in RC-2B

| Bug | Description | Fix |
|---|---|---|
| KI-7 | `fundamentals.py` returned HTTP 503 on `ok=False` | Always return 200; errors via `partial=True` |
| KI-8 | `industry_rank` missing `data.reasons` on `partial_errors` path | Merge `partial_errors` into `data.reasons` in `build_api_response` |

---

## Upgrade Notes

No breaking changes. No database schema changes beyond the 4 migrations applied in RC-2B (`alembic upgrade head`). Frontend is fully backwards-compatible.

Required migration before first deploy of RC-2:

```bash
cd backend && alembic upgrade head
```

---

## Production Launch Checklist

Before promoting RC-2 to production:

- [ ] Tushare Pro subscription activated (or alternative authorised data source)
- [ ] ETL scripts run: `stock_basic`, `daily_basic`, `fina_indicator`, `industry_rank`
- [ ] `CORS_ORIGINS` updated to include production domain
- [ ] `DEEPSEEK_API_KEY` (or equivalent AI provider key) configured on production
- [ ] `REDIS_URL` pointing to production Redis instance
- [ ] `SECRET_KEY` rotated from development value
- [ ] `APP_ENV=production` set
- [ ] `ENABLE_AKSHARE=false` confirmed (unless AkShare validation plan completed)
- [ ] Nginx SSE configuration applied (see `docs/server_deployment_guide.md`)
- [ ] Alembic migrations verified on production DB
- [ ] AI three-layer pipeline smoke test on one stock

---

## Tag Command

```bash
git tag -a v1.0.0-rc2 -m "RC-2: Company Tab fundamental analysis + AI summary strip + Phase 5 performance + RC-2B/C contract validation"
# Push only after production domain and data source are confirmed:
# git push origin v1.0.0-rc2
```
