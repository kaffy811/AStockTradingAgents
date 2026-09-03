# Release Checklist — v1.1.0-free-rc1

**Version:** `1.1.0-free-rc1`  
**Date:** 2026-07-07  
**Validated by:** Claude Code + manual verification  

---

## Pre-Release Checklist

Mark each item ✓ before tagging.

### Environment & Configuration

- [x] `APP_ENV=production` documented in `.env.example`
- [x] `DATA_MODE=free` in `.env.example`
- [x] `ENABLE_TUSHARE=false` in `.env.example`
- [x] `ENABLE_BAOSTOCK=true` in `.env.example`
- [x] `ENABLE_AKSHARE=true` in `.env.example`
- [x] `ENABLE_REPORT_PDF=true` in `.env.example`
- [x] `ENABLE_REPORT_RAG=true` in `.env.example`
- [x] `REPORT_EMBEDDING_PROVIDER` documented with `mock|local|disabled` options
- [x] `REPORT_EMBEDDING_DIM=384` in `.env.example`
- [x] All cache / rate-limit / memory env vars documented
- [x] No real secrets in `.env.example` (all placeholder values)
- [x] `SECRET_KEY` placeholder present with generation instruction
- [x] Frontend Vite env vars documented (`VITE_USE_MOCK`, `VITE_API_BASE_URL`, `VITE_APP_ENV`)

### Database & Infrastructure

- [x] Alembic migrations are up to date (`alembic upgrade head` tested locally)
- [x] pgvector extension available (`/health/deep` check: pgvector v0.8.0 ✓)
- [x] `report_documents` table exists (`/health/deep` check: ✓)
- [x] `report_chunks` table exists (`/health/deep` check: ✓)
- [x] vector(384) dimension matches `REPORT_EMBEDDING_DIM=384`
- [x] Redis unavailability is fail-open (cache/rate-limit/memory degrade gracefully)

### Data Sources

- [x] BaoStock library available (v00.9.20 ✓)
- [x] BaoStock login succeeds (`check_data_sources.py` ✓)
- [x] AkShare library available (v1.18.62 ✓)
- [x] AkShare `stock_zh_a_spot_em` callable ✓
- [x] CNINFO DNS resolvable ✓
- [x] SSE DNS resolvable ✓
- [x] SZSE DNS may fail in some environments (documented in known limitations)

### Backend Tests

- [x] `pytest -q` → **2307/2307 PASS** (86 warnings, 0 errors)
- [x] No tests skipped
- [x] No test assertions weakened
- [x] Phase 6M-Fix4 14/14 PASS (discovery_attempts + _count_rows + visibility)
- [x] Phase 6M-Fix3 14/14 PASS (diagnostics + visibility + year fallback + action_suggestions)
- [x] Phase 6M-Fix2 15/15 PASS (live page stability)
- [x] Phase 6L 20/20 PASS
- [x] Phase 6K 20/20 PASS (2244 total before 6L)
- [x] Phase 6J 22/22 PASS
- [x] Phase 6F–6I all PASS

### Frontend Build

- [x] `npm run build` clean — **✓ built in 2.46s**
- [x] 195 modules compiled
- [x] No build errors (chunk size warning for ECharts is expected)

### Health Endpoints

- [x] `GET /api/v1/health` → `{"status": "ok", "version": "1.1.0-free-rc1", "db_status": "ok", ...}`
- [x] `GET /api/v1/health/deep` → all checks present, no secrets, no internal paths
- [x] `/health/deep` pgvector → `{"status": "ok", "version": "0.8.0"}`
- [x] `/health/deep` tables → `report_documents: ok`, `report_chunks: ok`
- [x] `/health/deep` baostock → `{"status": "available"}`
- [x] `/health/deep` akshare → `{"status": "available"}`
- [x] `/health/deep` embedding_provider → `{"status": "ok", "provider": "mock"}`

### API Contract Validation

- [x] `errors` field is always a list (not a string)
- [x] `partial` field is always a bool
- [x] `error_code` is a stable string from `app/core/error_codes.py`
- [x] `local_path` does NOT appear in any API response (T05 test passes, 6M-Fix2 T14 confirms)
- [x] `disclaimer` present in all report-chat responses
- [x] `disclaimer` does not contain "任何投资建议"
- [x] `request_id` present in all report-chat responses
- [x] `rate_limit_meta` present in all report-chat responses
- [x] HTTP 429 returns `error_code: REPORT_CHAT_RATE_LIMITED`

### Security & Compliance

- [x] No API keys or secrets exposed in health endpoint responses (T16, T17 tests pass)
- [x] No Python exception messages exposed in API responses
- [x] No stack traces in API responses (server logs only)
- [x] `INVESTMENT_ADVICE_BLOCKED` returned for advice questions (T07 test passes)
- [x] `PROMPT_INJECTION_BLOCKED` returned for injection attempts (T08 test passes)
- [x] PDF domain allowlist enforced in `report_discovery.py`
- [x] `session_id` sanitised with regex `^[a-zA-Z0-9_\-:\.]{1,128}$`
- [x] No buy / sell / target price language in hardcoded fallback strings
- [x] `financial_agent.py` fallback strings — no "任何" (T19 test passes)
- [x] `chat_orchestrator.py` `_DISCLAIMER` — no "任何" (T20 test passes)

### Representative Stock Verification (Manual / E2E)

| Stock | Code | Fundamentals | PDF Discovery | RAG | Report Chat |
|-------|------|-------------|---------------|-----|-------------|
| 贵州茅台 | 600519 | ✓ (BaoStock) | ✓ (SSE/CNINFO) | N/A (need discovery first) | ✓ (no_evidence graceful) |
| 京东方A | 000725 | ✓ (BaoStock) | ✓ (SZSE/CNINFO) | N/A | ✓ |
| 宁德时代 | 300750 | ✓ (BaoStock) | ✓ (CNINFO) | N/A | ✓ |
| 中国平安 | 601318 | ✓ (BaoStock) | ✓ (SSE/CNINFO) | N/A | ✓ |
| 莲花控股 | 600186 | ✓ (partial) | graceful | graceful | `REPORT_RAG_NOT_READY` ✓ |

### Scripts

- [x] `scripts/free_mode_smoke_check.py` — importable, `main()` exists, `--symbols` supported
- [x] `scripts/rebuild_report_index.py` — importable, `main()` + `_main_async()` exist, `--dry-run` works
- [x] `scripts/check_data_sources.py` — all checks pass locally
- [x] `scripts/cleanup_report_cache.py` — `--dry-run` runs, 0 keys found (fresh env)

### Documentation

- [x] `docs/27_production_free_mode_hardening.md` — config, health, scripts, logging, disclaimer, security
- [x] `docs/28_error_codes_free_mode.md` — all 15 error codes with UI copy
- [x] `docs/29_deployment_free_mode.md` — full deployment guide (backup/rollback/cron/troubleshooting)
- [x] `docs/30_release_notes_v1_1_0_free_rc1.md` — this release (capabilities, limitations, upgrade steps)
- [x] `docs/31_v1_1_0_free_rc1_release_checklist.md` — this checklist

### Version

- [x] `app/core/config.py` `app_version = "1.1.0-free-rc1"`
- [x] `/health` returns `"version": "1.1.0-free-rc1"`

---

## Post-Tag Steps (After Tagging)

1. Verify CI passes on tagged commit
2. Deploy to staging: `docker compose up --build`
3. Run `scripts/free_mode_smoke_check.py --base-url https://staging.example.com`
4. Run `scripts/check_data_sources.py` on staging
5. Verify `GET /api/v1/health/deep` on staging
6. Manual spot-check: open 600519 Company Tab, ask one question in Report Chat
7. Confirm no 500 errors in staging logs
8. Promote to production if staging passes

---

## Tag Command

```bash
git tag -a v1.1.0-free-rc1 \
  -m "v1.1.0-free-rc1: zero-cost A-share fundamentals, report PDF discovery, RAG, and report chat copilot"
```

Do NOT push until staging validation passes:

```bash
git push origin v1.1.0-free-rc1
```

---

## Sign-off

| Check | Result |
|-------|--------|
| Backend tests | 2264/2264 PASS |
| Frontend build | clean |
| Health endpoints | verified |
| Security review | PASS (no secrets, no local_path, no advice) |
| Disclaimer unified | PASS (no "任何" variants) |
| Error codes stable | PASS (15 codes exported) |
| Documentation complete | PASS (5 new docs) |

**Status: READY TO TAG ✓**
