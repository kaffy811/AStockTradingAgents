# Release Notes — v1.1.0-free-rc1

**Release name:** Free Mode Release Candidate 1  
**Version:** `1.1.0-free-rc1`  
**Date:** 2026-07-07  
**Type:** Release Candidate  

---

## What's in this Release

v1.1.0-free-rc1 is the first release candidate of the **Free Mode** stack:
a fully operational, zero-cost A-share equity research platform that requires
no Tushare Pro subscription and no paid embedding service.

---

## Core Capabilities

### 1. Free-Mode Data Pipeline (DATA_MODE=free)

- **BaoStock** — K-line, financial metrics, index composition (free, registration required)
- **AkShare** — Spot quotes, news, industry data (free, scraping-based)
- Data falls back gracefully: Tushare Pro calls are skipped; partial results surface cleanly
- All data sourced from A-share public markets only (CN market)

### 2. Company Tab — Fundamental Analysis

- 11 analysis modules: growth / profitability / solvency / DuPont / cash flow quality / operating capability / capital occupation / asset structure / expense analysis / industry ranking / reference info
- ECharts interactive charts for all numeric modules
- DataSourceBanner shows free-mode notice when BaoStock/AkShare is primary source
- partial=true surfaces gracefully with data_limitations list

### 3. Report PDF Discovery & Download

- Auto-discovers annual and semi-annual reports from CNINFO / SSE / SZSE
- Confidence scoring (high / medium / low) based on disclosure source
- PDF domain allowlist: only CNINFO/SSE/SZSE domains; no open redirects
- local_path is never exposed in API responses

### 4. PDF Parse & RAG Index

- Text extraction from PDF (PyMuPDF)
- Chunking with configurable chunk_size / overlap
- Three embedding modes:
  - `mock` — CI-safe, deterministic random vectors, 0-cost (link-test only)
  - `local` — `sentence-transformers` BAAI/bge-small-zh-v1.5 (384d), offline-capable
  - `disabled` — no embedding; RAG unavailable
- vector(384) fixed dimension; pgvector 0.7+ required
- Hybrid scoring: vector + BM25 keyword + source boost + recency boost

### 5. 问财报 — Report Chat Copilot

- POST `/api/v1/stock/{code}/report-chat`
- Question normalization: whitespace collapse + Unicode NFC + fullwidth punctuation
- Prompt injection detection (CN + EN patterns) → hard-reject before LLM
- Investment advice keyword detection → reject with `INVESTMENT_ADVICE_BLOCKED`
- Review Agent validates source_chunks alignment with answer
- Redis TTL cache (30 min, version-keyed, fail-open)
- Fixed-window rate limiting (10/min · 100/hr per session/IP, fail-open)
- Session memory per (session_id, ts_code) — max 5 turns, 1h TTL (fail-open)

### 6. Health & Operations

- `GET /api/v1/health` — fast liveness probe (DB + Redis)
- `GET /api/v1/health/deep` — full readiness check (pgvector, tables, libs, embedding, flags)
- 15 stable error codes (`app/core/error_codes.py`)
- Structured log fields: request_id, rag_status, partial, cache_hit
- 4 operational scripts: smoke-check, rebuild-index, check-sources, cleanup-cache

### 7. Multi-language UI

- 6 locales: zh-CN, zh-TW, en-US, ja-JP, ko-KR, es-ES
- Full coverage: fundamentals, report chat, industry, watchlist, compare, history
- Theme system: light / dark / sepia

---

## Test Coverage

| Suite | Tests | Status |
|-------|-------|--------|
| Phase 1 Fundamentals | ✓ | PASS |
| Phase 2A–2D Financial modules | ✓ | PASS |
| Phase 6E PDF download/parse | ✓ | PASS |
| Phase 6F RAG pgvector | ✓ | PASS |
| Phase 6G local embedding | ✓ | PASS |
| Phase 6H source_chunks AI | ✓ | PASS |
| Phase 6I Review strict validation | ✓ | PASS |
| Phase 6J Report Chat Copilot | ✓ | PASS |
| Phase 6K Cache / rate limit / memory | ✓ | PASS |
| Phase 6L Production hardening | ✓ | PASS |
| Chat Copilot (C2–C32) | ✓ | PASS |
| **Total** | **2264** | **2264/2264 PASS** |

---

## Frontend Build

- `npm run build` — **clean** (no errors)
- 195 modules compiled
- Chunk size warnings for ECharts vendor bundle (expected; use code-splitting in future)

---

## Known Limitations

| Limitation | Impact | Mitigation |
|------------|--------|-----------|
| BaoStock field coverage narrower than Tushare Pro | Some financial metrics return `partial=true` | DataSourceBanner, data_limitations field |
| AkShare scraping-based; interface names may change | Module failure on AkShare version upgrade | Pin `akshare` version; run `check_data_sources.py` after upgrade |
| BaoStock login requires free registration | First-run login step | Documented in deployment guide |
| `mock` embedding has no semantic relevance | RAG returns syntactically valid but semantically random results | Use `local` embedding in production |
| `local` embedding requires model download (~100 MB) | First-run latency; fails in air-gapped environments without pre-downloaded model | Pre-download model; document path |
| PDF discovery depends on public disclosure page structure | Discovery fails if CNINFO/SSE/SZSE change page structure | Report and patch `report_discovery_agent.py` |
| Rate limit bucket is per session_id/IP, not authenticated user | Multi-user deployments share budget per IP behind NAT | Extend when auth is wired to report_chat router |
| Session memory is Redis plaintext | Non-PII financial Q&A content is stored unencrypted | Acceptable for public financial data |
| SZSE domain (`disclosure.szse.cn`) DNS resolution may fail in some environments | PDF discovery from SZSE may not work | Fallback to CNINFO; update `_ALLOWED_DOMAINS` as needed |
| No buy/sell/target-price recommendations | By design | Clearly documented; classifier blocks advice questions |
| `DATA_MODE=free` coverage: HK/US markets return partial=true | Only A-share (CN) market is fully supported | Clearly surfaced in UI |

---

## API Contract

All report-chat API responses include:
- `partial: bool` — always present
- `disclaimer: str` — "本内容基于已接入的公开数据和可用财报片段生成，仅供信息参考，不构成投资建议。"
- `error_code: str | null` — stable string from `app/core/error_codes.py`
- `request_id: str` — 8-char UUID prefix for log correlation
- `rate_limit_meta: dict` — rate limit state
- `cache_meta: dict` — cache hit/miss state
- `memory_meta: dict` — session memory state
- `safety_meta: dict` — normalization + injection detection state

`local_path` is never included in any API response.

---

## Upgrade Steps from v1.0.x

1. Pull the new code
2. `cd backend && uv sync`
3. `uv run alembic upgrade head`
4. Update `.env` with new free-mode variables (see `.env.example`)
5. Verify: `uv run python scripts/check_data_sources.py`
6. Verify: `uv run python scripts/free_mode_smoke_check.py --dry-run`
7. Optional: rebuild RAG index: `uv run python scripts/rebuild_report_index.py`
8. `cd frontend && npm install && npm run build`

---

## Rollback

1. `git checkout v1.0.x-tag`
2. `uv run alembic downgrade -1` (if new migrations were applied)
3. Restore PostgreSQL from backup if needed
4. To invalidate cache without downgrade: `REPORT_CHAT_CACHE_VERSION=v2`

---

## Compliance

All AI-generated content:
- Carries the canonical disclaimer in every response
- Does NOT contain buy / sell / target price / guaranteed return language
- Does NOT expose user prompts, full PDF text, or API keys in API responses
- Is reviewed by `FundamentalReviewAgent` for source chunk alignment

---

## Files Changed (Phase 6L additions)

See `docs/27_production_free_mode_hardening.md` for the full Phase 6L file list.

v1.1.0-free-rc1 spans Phases 6A–6L:
- Phase 6A: Free mode data sources
- Phase 6B–6C: BaoStock/AkShare integration
- Phase 6D: Report PDF discovery
- Phase 6E: PDF download & parse
- Phase 6F: pgvector RAG
- Phase 6G: Local embedding
- Phase 6H: Source chunks in AI analysis
- Phase 6I: Review Agent strict validation
- Phase 6J: Report Chat Copilot
- Phase 6K: Cache / rate limit / session memory
- Phase 6L: Production hardening (health, error codes, docs, scripts)
- Phase 6M: Release candidate validation (this release)
- Phase 6M-Fix2: Live page stability (BaoStock concurrency, pgvector cast, local_path leak, fallback price label)
- Phase 6M-Fix3: Free mode diagnostics + dynamic section visibility + PDF year fallback + report-chat action suggestions
- Phase 6M-Fix4: Diagnostics-driven rendering (no empty cards) + BaoStock series→rows normalization + PDF discovery_attempts + action buttons
