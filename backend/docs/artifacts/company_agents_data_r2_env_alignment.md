# Phase 6W-R2.0 — Root Environment Alignment

**Generated:** 2026-08-12  
**Branch:** release/demo-staging  
**HEAD:** a542bc1  
**Action:** ADD 5 feature flag lines to root `.env` — no existing values removed or modified.

---

## Change Applied

Root `.env` is in `.gitignore` — it will NOT be committed.

The following lines were appended to root `.env`:

```bash
# Phase 6W-R2.0: Production feature flags (synchronized from backend/.env)
DATA_MODE=free
ENABLE_BAOSTOCK=true
ENABLE_AKSHARE=true
ENABLE_REPORT_PDF=true
ENABLE_REPORT_RAG=true
```

---

## Before / After Matrix

| Variable | Before (root .env) | backend/.env (dev only) | After (root .env) | Production Runtime (docker-compose) | Correct? |
|----------|-------------------|--------------------------|--------------------|-------------------------------------|---------|
| `DATA_MODE` | ABSENT → `"standard"` | `free` | `free` | `free` | ✅ |
| `ENABLE_BAOSTOCK` | ABSENT → `false` | `true` | `true` | `true` | ✅ |
| `ENABLE_AKSHARE` | ABSENT → `false` | `true` | `true` | `true` | ✅ |
| `ENABLE_REPORT_PDF` | ABSENT → `false` | `true` | `true` | `true` | ✅ |
| `ENABLE_REPORT_RAG` | ABSENT → `false` | ABSENT → `false` | `true` | `true` | ✅ |
| `DEEPSEEK_API_KEY` | PRESENT (len=35, sk-8***) | PRESENT (same) | **UNCHANGED** | PRESENT | ✅ |
| `TUSHARE_TOKEN` | PRESENT (len=56, e81***) | PRESENT (same) | **UNCHANGED** | PRESENT | ✅ |
| `DATABASE_URL` | PRESENT (Supabase pooler) | PRESENT (same) | **UNCHANGED** | PRESENT | ✅ |
| `SECRET_KEY` | PRESENT (len=64) | PRESENT (same) | **UNCHANGED** | PRESENT | ✅ |
| `APP_ENV` | `development` | `development` | **UNCHANGED** | `production` (compose override) | ✅ |
| `DEBUG` | `true` | `true` | **UNCHANGED** | `false` (compose override) | ✅ |
| `REDIS_URL` | `redis://localhost:6379` | same | **UNCHANGED** | `redis://redis:6379` (compose override) | ✅ |

---

## Verification

Post-append confirmation (variable names + values only, no secrets):

```
DATA_MODE=free         ✅ present
ENABLE_BAOSTOCK=true   ✅ present
ENABLE_AKSHARE=true    ✅ present
ENABLE_REPORT_PDF=true ✅ present
ENABLE_REPORT_RAG=true ✅ present
```

Duplicate check: each flag appears exactly **1 time** in root `.env`.  
Secrets: DEEPSEEK_API_KEY len=35 UNCHANGED, TUSHARE_TOKEN len=56 UNCHANGED, SECRET_KEY len=64 UNCHANGED.

---

## Effect on Production Deployment

When `docker compose up -d` is next run:
- `env_file: ['.env']` loads root `.env` → all 5 new flags now present
- `environment:` overrides (APP_ENV=production, DEBUG=false, REDIS_URL=redis://redis:6379) still apply
- Backend container effective configuration: all 5 flags active
- **No rebuild required** — env vars are injected at container start, not build time

---

## Known Remaining Gap

`CORS_ORIGINS` in root `.env` currently contains:
```
["https://hugh-focusing-jet-urge.trycloudflare.com","http://localhost:3000","http://127.0.0.1:3000"]
```

The Cloudflare tunnel URL is temporary and will expire. This must be updated to the production domain before public launch. Not blocking for invite-only 1% canary (access is authenticated/invite-gated).

---

*Secret masking policy: no full token values appear in this document.*
