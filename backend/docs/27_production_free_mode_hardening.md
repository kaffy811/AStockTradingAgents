# Phase 6L — Production Free Mode Hardening

## Overview

Phase 6L consolidates the zero-cost free-mode stack into a production-ready,
deployable configuration. No new AI features are added; the focus is on
operational reliability, security, and compliance.

---

## 1. Environment Configuration

### backend/.env — Production Template

```dotenv
# ── App ────────────────────────────────────────────────────────────────────────
APP_ENV=production
DEBUG=false
APP_VERSION=0.1.0
SECRET_KEY=<generate: openssl rand -hex 32>   # REQUIRED — min 16 chars

# ── Database ───────────────────────────────────────────────────────────────────
DATABASE_URL=postgresql+asyncpg://user:password@host:5432/tradingagents   # REQUIRED
REDIS_URL=redis://:password@host:6379/0                                    # RECOMMENDED

# ── CORS ───────────────────────────────────────────────────────────────────────
CORS_ORIGINS=["https://your-app.example.com"]   # REQUIRED in production

# ── LLM ────────────────────────────────────────────────────────────────────────
DEEPSEEK_API_KEY=<your-key>    # REQUIRED for AI analysis
DEEPSEEK_BASE_URL=https://api.deepseek.com
ENABLE_DEEPSEEK_REASONER=true

# ── Data mode ─────────────────────────────────────────────────────────────────
DATA_MODE=free
ENABLE_TUSHARE=false           # Disable Tushare Pro APIs in free mode
ENABLE_BAOSTOCK=true           # BaoStock (free, requires pip install baostock)
ENABLE_AKSHARE=true            # AkShare (free, requires pip install akshare)

# ── Report PDF + RAG ──────────────────────────────────────────────────────────
ENABLE_REPORT_PDF=true
ENABLE_REPORT_RAG=true

# Embedding provider:
#   mock    — CI-safe, 0-cost, no semantic search (link-test only)
#   local   — sentence-transformers BAAI/bge-small-zh-v1.5 (requires model file)
#   disabled — no embeddings; RAG will not work
REPORT_EMBEDDING_PROVIDER=local
REPORT_EMBEDDING_MODEL=BAAI/bge-small-zh-v1.5
REPORT_EMBEDDING_DIM=384

# ── Report Chat cache + rate limit + memory ───────────────────────────────────
ENABLE_REPORT_CHAT_CACHE=true
REPORT_CHAT_CACHE_TTL_SECONDS=1800
REPORT_CHAT_CACHE_VERSION=v1
ENABLE_REPORT_CHAT_RATE_LIMIT=true
REPORT_CHAT_RATE_LIMIT_PER_MINUTE=10
REPORT_CHAT_RATE_LIMIT_PER_HOUR=100
ENABLE_REPORT_CHAT_MEMORY=true
REPORT_CHAT_MEMORY_TTL_SECONDS=3600
REPORT_CHAT_MEMORY_MAX_TURNS=5

# ── Analysis engine ───────────────────────────────────────────────────────────
DEFAULT_ANALYSIS_ENGINE=custom_coordinator
ANALYSIS_RUN_REGISTRY=redis
ENABLE_MULTI_AGENT_ORCHESTRATOR=false
```

### Required vs Optional

| Variable | Status | Default | Notes |
|----------|--------|---------|-------|
| `DATABASE_URL` | **Required** | — | PostgreSQL + asyncpg |
| `SECRET_KEY` | **Required** | — | min 16 chars; never commit |
| `DEEPSEEK_API_KEY` | **Required** for AI | — | Chat + analysis features |
| `REDIS_URL` | **Recommended** | localhost:6379 | Cache/rate-limit/memory; fail-open if absent |
| `CORS_ORIGINS` | **Required** in prod | localhost variants | JSON array of allowed origins |
| `REPORT_EMBEDDING_PROVIDER` | Optional | `mock` | `local` for real semantic search |
| `REPORT_EMBEDDING_MODEL` | Optional | — | Used when provider=local |
| `DATA_MODE` | Optional | `standard` | Set `free` to disable Tushare Pro APIs |

### Local Embedding Notes

- `REPORT_EMBEDDING_PROVIDER=local` requires `pip install sentence-transformers`
- Model downloads on first use (~100 MB for `BAAI/bge-small-zh-v1.5`)
- For air-gapped deployments, pre-download and set `REPORT_EMBEDDING_MODEL=/path/to/model`
- `mock` embedding is suitable for integration test / CI pipeline only; semantic relevance is random

### Free Data Sources — Stability Caveats

| Source | Notes |
|--------|-------|
| **BaoStock** | Free, requires login. Rate limits may apply. K-line data only through prior trading day. Metric coverage narrower than Tushare Pro. |
| **AkShare** | Free, scraping-based. Interface names and field names may change without notice. Pin the version in `pyproject.toml`. |

---

## 2. Health Check API

### GET /api/v1/health

Fast liveness probe. Suitable for load-balancer health check intervals of 5–30s.

**Response:**
```json
{
  "status": "ok",
  "app": "TradingAgents Backend",
  "version": "0.1.0",
  "env": "production",
  "db_status": "ok",
  "redis_status": "ok",
  "data_mode": "free",
  "report_rag_enabled": true
}
```

`status` is `"ok"` when PostgreSQL is reachable, `"degraded"` otherwise.

### GET /api/v1/health/deep

Comprehensive readiness check. Run on deploy or from monitoring cron. Not for
high-frequency load-balancer polling.

**Response structure:**
```json
{
  "status": "ok",
  "app": "TradingAgents Backend",
  "version": "0.1.0",
  "env": "production",
  "checks": {
    "postgres":               {"status": "ok"},
    "redis":                  {"status": "ok"},
    "pgvector":               {"status": "ok", "version": "0.7.4"},
    "table_report_documents": {"status": "ok"},
    "table_report_chunks":    {"status": "ok"},
    "baostock":               {"status": "available", "version": "0.8.9"},
    "akshare":                {"status": "available", "version": "1.12.99"},
    "embedding_provider":     {"status": "ok", "provider": "local", "model": "BAAI/bge-small-zh-v1.5", "dim": 384},
    "report_chat_cache":      {"status": "enabled", "redis_backing": true, "ttl_seconds": 1800},
    "report_chat_rate_limit": {"status": "enabled", "per_minute": 10, "per_hour": 100},
    "feature_flags":          {"data_mode": "free", "report_rag": true, ...}
  }
}
```

No secrets, tokens, API keys, or filesystem paths are returned.

---

## 3. Utility Scripts

All scripts live in `backend/scripts/`. Run with `uv run python scripts/<name>.py`.

### free_mode_smoke_check.py
Verifies the live API pipeline:
- `GET /api/v1/health`
- `GET /api/v1/health/deep`
- Fundamentals for 3 known A-share stocks
- `POST /api/v1/stock/{code}/report-chat` (first stock, short question)

Options: `--base-url`, `--dry-run`, `--json`

### rebuild_report_index.py
Re-chunks and re-embeds already-downloaded PDF reports into `report_chunks`:
```bash
# Dry-run all:
uv run python scripts/rebuild_report_index.py --dry-run

# Rebuild one stock:
uv run python scripts/rebuild_report_index.py --symbol 600519.SH

# Force re-embed even if chunks exist:
uv run python scripts/rebuild_report_index.py --force --limit 20
```

### check_data_sources.py
Checks library imports, BaoStock login, AkShare callability, DNS for report PDF domains.
Does not make bulk data requests.

### cleanup_report_cache.py
Cleans Redis report-chat cache (`rc:*`) and session memory (`cm:*`).
Does NOT touch `report_documents` or `report_chunks` tables.
```bash
# Dry-run:
uv run python scripts/cleanup_report_cache.py --dry-run

# Clean a specific stock:
uv run python scripts/cleanup_report_cache.py --ts-code 600519.SH
```

---

## 4. Structured Logging Fields

All report-chat requests log these fields at `INFO` level:

| Field | Source |
|-------|--------|
| `request_id` | UUID prefix generated per request |
| `code` | Stock code from URL |
| `rag_status` | `"retrieved"` / `"no_evidence"` / `"rejected"` / `"unavailable"` |
| `partial` | Boolean — whether result is incomplete |
| `cache_hit` | Boolean — whether Redis cache was used |

Rate-limited requests log at `INFO` with `rate_limited` tag.
Unhandled exceptions log at `ERROR` with `unhandled_error` tag and exception class name only (no stack trace in the log line, but full traceback at `exc_info=True`).

**NOT logged:**
- Full question text
- Full LLM prompt or response
- API keys / tokens
- PDF content
- Filesystem paths

---

## 5. Disclaimer Unification

**Canonical disclaimer (report-chat / report-discovery / report-rag context):**
> 本内容基于已接入的公开数据和可用财报片段生成，仅供信息参考，不构成投资建议。

**Chat Copilot disclaimer (`chat_orchestrator.py`):**
> 仅供研究参考，不构成投资建议。

Both are consistent in that they:
1. Do NOT contain "任何投资建议" (banned variant)
2. Do NOT contain buy/sell/target-price language
3. Are present in every AI-generated answer

---

## 6. Security Properties

| Property | Implementation |
|----------|----------------|
| No secret leakage | Health endpoints exclude API keys, DB passwords, secret_key |
| No path disclosure | Error responses exclude `local_path` or Python tracebacks |
| Error codes only | API errors return `error_code` (stable string), not Python exception class |
| Prompt injection blocked | Detected before LLM/RAG call; returns `PROMPT_INJECTION_BLOCKED` |
| Rate limiting | 10/min · 100/hr per session/IP; fail-open if Redis down |
| Investment advice blocked | Keyword classifier rejects advice questions; returns `INVESTMENT_ADVICE_BLOCKED` |
| PDF domain allowlist | Only CNINFO/SSE/SZSE domains; no open redirects |
| session_id sanitised | Regex `^[a-zA-Z0-9_\-:\.]{1,128}$`; invalid IDs silently discarded |

---

## 7. Frontend Production Hints (Verified)

| Component | Check | Status |
|-----------|-------|--------|
| ReportChatPanel | Disclaimer displayed | ✓ |
| ReportChatPanel | Rate limit notice on HTTP 429 | ✓ |
| ReportChatPanel | Cache badge (⚡) | ✓ |
| ReportChatPanel | Memory badge (💬N) | ✓ |
| ReportChatPanel | Free data source note | ✓ |
| ReportChatPanel | IME guard (CJK compose) | ✓ |
| ReportChatPanel | No `v-html` usage | ✓ |
| ReportChatPanel | `target="_blank"` has `rel="noopener noreferrer"` | ✓ |
| AiAnalysisCard | Disclaimer / partial notice | ✓ |
| CompanyTab | Data source limitations notice | ✓ |

---

## 8. Files Changed

### New
- `app/core/error_codes.py` — 15 stable error code constants
- `scripts/free_mode_smoke_check.py`
- `scripts/rebuild_report_index.py`
- `scripts/check_data_sources.py`
- `scripts/cleanup_report_cache.py`
- `tests/fundamental/test_phase6l_production_hardening.py` — 20 tests
- `docs/27_production_free_mode_hardening.md` — this document
- `docs/28_error_codes_free_mode.md`
- `docs/29_deployment_free_mode.md`

### Modified
- `app/routers/health.py` — full `/health` + new `/health/deep`
- `app/routers/report_chat.py` — `_CANONICAL_DISCLAIMER`, `error_code`, `request_id`, structured log
- `app/routers/report_discovery.py` — canonical disclaimer
- `app/routers/report_rag.py` — canonical disclaimer
- `app/core/config.py` — `enable_tushare` flag

---

## 9. Remaining Risks

| Risk | Mitigation |
|------|-----------|
| AkShare interface churn | Pin `akshare==x.y.z` in pyproject.toml; run `check_data_sources.py` after upgrades |
| BaoStock login failures | Retry logic in `baostock_client.py`; `free_mode_smoke_check.py` detects |
| Redis unavailability | All cache/rate-limit/memory features fail-open |
| Local embedding model not downloaded | `health/deep` will show `sentence_transformers not installed` in embedding_provider check |
| Rate limit bucket is per session_id/IP | Not per authenticated user; extend when auth is wired to this router |
| PDF download domain changes | Maintain `_ALLOWED_DOMAINS` in `report_discovery.py` |
