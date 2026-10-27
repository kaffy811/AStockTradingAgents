# Phase 6W-R1.8 — Production Environment Audit

**Generated:** 2026-08-12  
**Branch:** release/demo-staging  
**HEAD:** a542bc1  
**Purpose:** Audit and document the full production environment configuration gap.  
**Status:** READ-ONLY audit. No changes made.

---

## 1. Source-of-Truth Analysis

### How the Production Backend Container Receives Configuration

```
root .env               ← loaded via env_file: ['.env'] in docker-compose.yml
     ↓
docker-compose.yml      ← environment: section OVERRIDES specific vars
     ↓
backend container runtime environment
     ↓
app/core/config.py      ← SettingsConfigDict(env_file=".env") — reads root .env
                           inside container, the container's /app is mounted,
                           NOT the host's backend/.env
```

**Critical finding:** `backend/.env` is NEVER loaded in production docker-compose deployment.  
It is used ONLY for local development (`uvicorn` run from `backend/` directory).

### How the Production Frontend Bundle Receives Configuration

```
docker-compose.yml build args: VITE_API_BASE=/api/v1
     ↓
frontend/Dockerfile: ARG VITE_API_BASE=/api/v1 → ENV VITE_API_BASE=$VITE_API_BASE
     ↓
npm run build (Vite bakes value into JS bundle)
     ↓
nginx serves static dist/ — value is FROZEN in bundle
```

`frontend/.env` and `frontend/.env.local` are IGNORED in Docker build because:
- `VITE_API_BASE` is passed as Docker build arg → ENV → overrides any .env file
- docker-compose.yml build args take precedence

---

## 2. Environment Variable Matrix

*Secret masking policy: PRESENT/ABSENT, length, 3-char prefix only. No full values.*

| Variable | Root .env | backend/.env | docker-compose.yml override | Production Runtime Value | Config.py Default | R1.8 Target |
|----------|-----------|--------------|------------------------------|--------------------------|-------------------|-------------|
| **DATABASE_URL** | PRESENT (Supabase pooler, ap-northeast-2) | PRESENT (same) | — | Supabase Transaction Pooler | required | PRESENT ✅ |
| **DEEPSEEK_API_KEY** | PRESENT len=35 prefix=sk-8 | PRESENT (same) | — | PRESENT | None | PRESENT ✅ |
| **TUSHARE_TOKEN** | PRESENT len=56 prefix=e81 | PRESENT (same) | — | PRESENT | None | PRESENT ✅ |
| **SECRET_KEY** | PRESENT len=64 | PRESENT (same) | — | PRESENT | required | PRESENT ✅ |
| **APP_ENV** | development | development | **production** | **production** | development | production ✅ |
| **DEBUG** | true | true | **false** | **false** | True | false ✅ |
| **REDIS_URL** | redis://localhost:6379 | redis://localhost:6379 | **redis://redis:6379** | **redis://redis:6379** | redis://localhost:6379 | redis://redis:6379 ✅ |
| **LLM_PROVIDER** | deepseek | deepseek | — | deepseek | deepseek | deepseek ✅ |
| **DEEPSEEK_BASE_URL** | https://api.deepseek.com | https://api.deepseek.com | — | https://api.deepseek.com | https://api.deepseek.com | ✅ |
| **DEEPSEEK_DEFAULT_MODEL** | deepseek-v4-flash | deepseek-v4-flash | — | deepseek-v4-flash | deepseek-v4-flash | ✅ |
| **ENABLE_DEEPSEEK_REASONER** | true | ABSENT | — | true | True | true ✅ |
| **ANALYSIS_RUN_REGISTRY** | memory | memory | — | memory | memory | memory ✅ |
| **DEFAULT_ANALYSIS_ENGINE** | custom_coordinator | custom_coordinator | — | custom_coordinator | custom_coordinator | ✅ |
| **CORS_ORIGINS** | ["https://hugh-focusing-jet-urge.trycloudflare.com","http://localhost:3000","http://127.0.0.1:3000"] | ABSENT | — | Cloudflare tunnel + localhost | localhost list | ⚠️ needs production domain |
| **ACCESS_TOKEN_EXPIRE_MINUTES** | 60 | 60 | — | 60 | 60 | ✅ |
| **REFRESH_TOKEN_EXPIRE_DAYS** | 30 | 30 | — | 30 | 30 | ✅ |
| **DATA_MODE** | **ABSENT** | free | — | **"standard"** (default) | "standard" | **free** ❌ MISSING |
| **ENABLE_BAOSTOCK** | **ABSENT** | true | — | **false** (default) | False | **true** ❌ MISSING |
| **ENABLE_AKSHARE** | **ABSENT** | true | — | **false** (default) | False | **true** ❌ MISSING |
| **ENABLE_REPORT_PDF** | **ABSENT** | true | — | **false** (default) | False | **true** ❌ MISSING |
| **ENABLE_REPORT_RAG** | **ABSENT** | **ABSENT** | — | **false** (default) | False | **true** ❌ MISSING |
| **VITE_API_BASE** (frontend) | http://localhost:8000/api/v1 (frontend/.env) | — | **/api/v1** (build arg) | **/api/v1** baked in bundle | — | /api/v1 ✅ |

---

## 3. Configuration Gap Summary

### Variables Missing from Root `.env` (Production Blockers)

| Variable | Needed Value | Impact if Missing | Risk |
|----------|-------------|-------------------|------|
| `DATA_MODE` | `free` | Production runs in `standard` mode → Tushare primary → all permission denied → Company Overview 6 fields ALL null | HIGH |
| `ENABLE_BAOSTOCK` | `true` | BaoStock provider disabled → no fallback for price/PE/PB/ROE | HIGH |
| `ENABLE_AKSHARE` | `true` | AkShare disabled → no secondary fallback | MEDIUM |
| `ENABLE_REPORT_PDF` | `true` | PDF download/parse disabled → RAG pipeline cannot ingest new reports | HIGH |
| `ENABLE_REPORT_RAG` | `true` | RAG completely disabled → `report_chat` always returns `rag_status: not_indexed` | HIGH (P0) |

### Variables Present but Potentially Stale

| Variable | Current Value | Concern |
|----------|--------------|---------|
| `CORS_ORIGINS` | Cloudflare tunnel URL (temporary) | Tunnel expires; needs production domain |
| `APP_ENV` | `development` in root .env | docker-compose overrides to `production` → OK, but root .env label is misleading |

---

## 4. Docker Compose Configuration Override Audit

### What docker-compose.yml Backend Environment Section Overrides:

```yaml
environment:
  - REDIS_URL=redis://redis:6379    # ✅ overrides localhost → compose service name
  - APP_ENV=production              # ✅ overrides development
  - DEBUG=false                     # ✅ overrides true
```

**What it does NOT override** (relies on root .env `env_file`):
- DATA_MODE
- ENABLE_BAOSTOCK
- ENABLE_AKSHARE
- ENABLE_REPORT_PDF
- ENABLE_REPORT_RAG
- All secrets (DATABASE_URL, DEEPSEEK_API_KEY, TUSHARE_TOKEN, SECRET_KEY)

### Migrate Service Environment:

```yaml
environment:
  - ENABLE_CREATE_ALL=false         # ✅ prevents Base.metadata.create_all at startup
  - APP_ENV=production
  - REDIS_URL=redis://redis:6379
```

---

## 5. Frontend Configuration Audit

| File | VITE_API_BASE | Loaded In |
|------|--------------|-----------|
| `frontend/.env` | `http://localhost:8000/api/v1` | Local dev only |
| `frontend/.env.local` | `http://localhost:8000/api/v1` | Local dev only |
| `frontend/.env.production` | `/api/v1` | Vite `--mode production` |
| docker-compose.yml build arg | `/api/v1` | **Docker build** → **wins** |
| Dockerfile ARG default | `/api/v1` | Docker build default |

**Production bundle verification (dist/assets/index-BxIiHZ4a.js):**
- `localhost` occurrences: **0** ✅
- `"/api/v1"` occurrences: **3** ✅
- Bundle source confirmed: build arg `/api/v1` was baked correctly

---

## 6. Config.py Defaults That Matter

These config.py defaults take effect when the variable is ABSENT from root .env:

```python
data_mode: str = "standard"        # ABSENT from root .env → "standard" in production
enable_akshare: bool = False        # ABSENT → False
enable_baostock: bool = False       # ABSENT → False
enable_report_pdf: bool = False     # ABSENT → False
enable_report_rag: bool = False     # ABSENT → False  ← P0 blocker
```

---

## 7. Recommended Root `.env` Patch

*For project owner review and authorization. Not applied.*

Lines to ADD (append to existing root `.env`):

```bash
# Phase 6W-R1.8: Production feature flags (previously only in backend/.env)
DATA_MODE=free
ENABLE_BAOSTOCK=true
ENABLE_AKSHARE=true
ENABLE_REPORT_PDF=true
ENABLE_REPORT_RAG=true
```

**Existing variables: DO NOT MODIFY.** All current values in root `.env` are preserved.

**CORS_ORIGINS action (separate decision):**  
Current value includes temporary Cloudflare tunnel URL and localhost entries.  
Before production launch, replace with the actual production domain.  
Proposed format: `["https://your-production-domain.com","http://localhost:3000"]`

---

## 8. Gate: Code-Sees vs Container-Sees

**Question: Does "code-sees configuration" equal "container runtime configuration"?**

**Answer: NO — currently diverged.**

| Config Group | Code Sees | Container Sees | Match? |
|---|---|---|---|
| Core secrets (DB, keys) | root .env | root .env via env_file | ✅ |
| REDIS_URL | localhost:6379 (root .env) | redis://redis:6379 (compose override) | ✅ (compose corrects) |
| APP_ENV | development (root .env) | production (compose override) | ✅ (compose corrects) |
| DEBUG | true (root .env) | false (compose override) | ✅ (compose corrects) |
| DATA_MODE | standard (default) | standard (missing, uses default) | ✅ (both wrong) |
| ENABLE_BAOSTOCK | false (default) | false (missing, uses default) | ✅ (both wrong) |
| ENABLE_AKSHARE | false (default) | false (missing, uses default) | ✅ (both wrong) |
| ENABLE_REPORT_PDF | false (default) | false (missing, uses default) | ✅ (both wrong) |
| ENABLE_REPORT_RAG | false (default) | false (missing, uses default) | ✅ (both wrong) |

**Result:** Code and container agree — both are wrong due to missing flags.  
Fixing root `.env` will simultaneously fix both development and production when using docker-compose.

---

*This is an audit document. No files were modified.*
