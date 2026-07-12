# Production Readiness Checklist — TradingAgents

**Purpose:** Final gate before deploying to a production or staging environment.

---

## 1. Environment Variables

### Backend (`.env` or server environment)

| Variable | Required | Notes |
|----------|----------|-------|
| `DATABASE_URL` | Yes | PostgreSQL connection string with pgvector |
| `REDIS_URL` | Yes | `redis://localhost:6379/0` or managed Redis |
| `TUSHARE_TOKEN` | Partial* | Without token, financial modules return 503 |
| `AI_PROVIDER` | Yes | `deepseek` or `openai` |
| `AI_API_KEY` | Yes | API key for the chosen provider |
| `ENABLE_AKSHARE` | Optional | `true` to enable AkShare fallback |
| `DEFAULT_ANALYSIS_ENGINE` | Optional | `langgraph` or `custom_coordinator` |
| `SECRET_KEY` | Yes | JWT signing key — never use default |

*Without TUSHARE_TOKEN: stock search, quotes, news still work. Company fundamentals and ETL-dependent features are partial.

### Frontend (`.env.production`)

| Variable | Required | Notes |
|----------|----------|-------|
| `VITE_API_BASE_URL` | Yes | Full backend URL (e.g. `https://api.yourdomain.com`) |
| `VITE_USE_MOCK` | Must be `false` | Never deploy with mock data enabled |

---

## 2. Backend Health Checks

Run before launching:

```bash
# Health endpoint
curl https://api.yourdomain.com/health

# Database connectivity
curl https://api.yourdomain.com/api/v1/stocks/CN/600519/profile

# Redis (check analysis streaming works)
curl https://api.yourdomain.com/api/v1/analysis/status/test

# Tushare (check token)
curl https://api.yourdomain.com/api/v1/stock/600519/modules/snapshot
# 200 = token OK, 503 = token missing/quota exceeded
```

Expected: `/health` returns `{"status": "ok"}`.

---

## 3. Frontend Build Checklist

```bash
cd frontend
VITE_USE_MOCK=false VITE_API_BASE_URL=https://api.yourdomain.com npm run build
```

- [ ] Build completes with no errors
- [ ] `dist/` generated with `index.html`
- [ ] `echarts` appears as a separate chunk (see chunk sizes in build output)
- [ ] `xlsx` appears as a separate chunk
- [ ] `VITE_USE_MOCK` is **not** `true` in production build
- [ ] No `localhost` references in built JS (grep `dist/` for `localhost`)

---

## 4. Data ETL Tasks

Run these before first production launch (or on a schedule):

| Task | Command | Frequency |
|------|---------|-----------|
| Shenwan industry → stock mapping | `python scripts/refresh_industry_hot_stocks.py` | Daily |
| Industry hot scores refresh | Same script | Daily (after market close) |
| Financial RAG knowledge base | Load documents via `/api/v1/rag/ingest` | On update |

Without ETL: 同行业对比 tab shows EmptyState; industry ranking unavailable.

---

## 5. Compliance Items

- [ ] No investment advice disclaimer visible on analysis reports ("本报告由 AI 生成，仅供参考，不构成投资建议")
- [ ] AI Review Agent (RiskReviewAgent) is active in LangGraph engine — checks for speculative language
- [ ] Chat Copilot includes financial safety postprocessor (`financial_safety_postprocessor.py`)
- [ ] No real user PII stored in analysis reports
- [ ] `SECRET_KEY` rotated from default and stored securely (not in git)

---

## 6. Acceptance Test Stocks

Use these three stocks for final acceptance testing:

| Stock | Code | Market | Why |
|-------|------|--------|-----|
| 贵州茅台 | 600519 | CN | Blue chip, high data availability |
| 京东方 | 000725 | CN | Large cap, electronics sector |
| 荷花莲 | 600186 | CN | Mid-cap, tests edge cases |

For each stock, verify:
- [ ] Stock detail page loads with name and quote
- [ ] K-line chart renders
- [ ] 公司 tab loads financial data (requires Tushare token)
- [ ] 同行业对比 tab shows peers (requires ETL)
- [ ] AI analysis generates a report

---

## 7. Known Limitations

| Limitation | Impact | Workaround |
|-----------|--------|-----------|
| No TUSHARE_TOKEN | Company financials (modules) return 503 | Configure token; fallback banner shown |
| ETL not run | Industry rankings empty | Run `refresh_industry_hot_stocks.py` |
| Redis unavailable | Analysis SSE streaming falls back to MemoryRegistry | Use Redis in production for multi-worker |
| HK stocks | No Shenwan industry data; peer comparison unavailable | Expected behavior, EmptyState shown |
| AkShare rate limits | Intermittent 429 on quote/news endpoints | Enable retry logic, rate-limit is 2req/s |
| LangGraph engine | Requires `DEFAULT_ANALYSIS_ENGINE=langgraph` env var | Defaults to `custom_coordinator` if unset |

---

## 8. Final Go/No-Go

| Check | Status |
|-------|--------|
| All env vars configured | |
| Health endpoint returns 200 | |
| ETL tables populated | |
| Build passes with no mock | |
| Acceptance test stocks verified | |
| Disclaimer text visible on reports | |
| SSL / HTTPS configured | |
| Nginx SSE timeout set (`proxy_read_timeout 300s`) | |
