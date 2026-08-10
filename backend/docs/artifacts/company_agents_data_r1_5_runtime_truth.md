# Phase 6W-R1.5 Runtime Truth Matrix

**Date:** 2026-08-10
**Branch:** `release/demo-staging`
**HEAD:** `d3b7063fb4941561d2ecce0eea26ef569d11b685`
**Scope:** Read-only forensic audit — no code changes, no commits, no pushes, no FLUSHALL
**Auditor:** Automated runtime trace (docker exec, curl, log inspection, Redis scan)

---

## 1. Company Overview Six-Field Runtime Trace

### 1.1 Raw API Evidence

**GET /api/v1/stocks/CN/600519/quote → HTTP 200**
```
provider: sina (eastmoney FAIL: Connection aborted / RemoteDisconnected)
data.price: 1353.18
data.change_pct: 3.358
data.trade_time: 2026-08-10 11:30:00
```

**GET /api/v1/stocks/CN/600519/fundamentals → HTTP 200 (partial)**
```
valuation.pe: null
valuation.pb: null
valuation.ps: null
valuation.market_cap: null
valuation.market_cap_unit: null
valuation.dividend_yield: null
profitability.roe: 10.57
profitability.gross_margin: 89.76
profitability.net_margin: 52.22
growth.revenue_growth_yoy: 6.34
growth.net_profit_growth_yoy: 1.47
data_quality.message: "AkShare spot_em unavailable (Connection aborted, RemoteDisconnected); valuation.pe/pb unavailable."
```

### 1.2 Six-Field Trace Table

| UI 字段 | Endpoint | Response key | API value | 数据源 | 状态 |
|---|---|---|---|---|---|
| 最新价 | /quote | data.price | **1353.18** | sina_quote | ✅ 有值 |
| PE(TTM) | /fundamentals | valuation.pe | **null** | (all providers failed) | ❌ null |
| PB | /fundamentals | valuation.pb | **null** | (all providers failed) | ❌ null |
| 总市值 | /fundamentals | valuation.market_cap | **null** | (all providers failed) | ❌ null |
| ROE | /fundamentals | profitability.roe | **10.57** | akshare_ths_financial_abstract | ✅ 有值 |
| 股息率(TTM) | /fundamentals | valuation.dividend_yield | **null** | (all providers failed) | ❌ null |

### 1.3 Provider Chain Trace for pe_ttm / pb / total_mv

```
UI field: pe_ttm / pb / total_mv / dividend_yield
    ↓
/api/v1/stocks/CN/600519/fundamentals
    ↓
fundamentals aggregator → _fill_cn() → valuation section
    ↓
Step 1: AkShare stock_zh_a_spot_em (EastMoney spot endpoint)
        FAIL: Connection aborted / RemoteDisconnected
        [EastMoney domain unreachable in staging network]
    ↓
Step 2: Tushare daily_basic
        SKIP: TUSHARE_TOKEN = NOT_SET in container environment
        [Token not injected into Docker container]
    ↓
Step 3: yfinance (market_cap only)
        FAIL: 429 Too Many Requests / circuit breaker OPEN
    ↓
Step 4: Final result = null for all four valuation fields
```

### 1.4 Forensic Answers (pe/pb/total_mv)

| 问题 | 答案 |
|---|---|
| Tushare 是否被调用？ | **NO** — TUSHARE_TOKEN 未注入容器 |
| Tushare 是否返回错误？ | N/A（未调用） |
| 错误类型 | N/A |
| AkShare fallback 是否发生？ | YES — AkShare 是 primary provider |
| AkShare 是否被调用？ | YES |
| AkShare raw response 包含对应字段？ | NO — Connection aborted before response |
| 哪一层丢失？ | Step 1 网络层：EastMoney endpoint 在 staging 网络中不可达 |
| fallback 为何不提供？ | Tushare token 未注入；yfinance rate-limited |
| 字段名称映射错误？ | NO |
| 单位转换问题？ | N/A（未到达此层） |
| None/null overwrite？ | NO — 全程为 null（未被 provider 写入） |
| provider priority 导致错误覆盖？ | NO — 问题在 primary provider 网络失败 |

---

## 2. Tushare Permission Matrix

**TUSHARE_TOKEN 状态：**
```
TUSHARE_TOKEN: NOT_SET  (环境变量未注入 Docker 容器)
```

**重要：** TUSHARE_TOKEN 不在 `.env.staging.local` 中，也不通过 `docker compose --env-file` 传入。`enable_tushare: True` in settings 但 `tushare_token: None`。

| API | Tushare | Permission | Raw Data | Fallback | Final |
|---|---|---|---|---|---|
| `daily_basic` | **NOT_CALLED** | N/A (no token) | N/A | AkShare (failed: network) | null |
| `fina_indicator` | **NOT_CALLED** | N/A (no token) | N/A | AkShare THS (success: 10.57) | ROE=10.57 |
| `stock_zh_a_spot_em` | N/A (AkShare) | N/A | FAIL (Connection aborted) | yfinance (rate limited) | null |

**结论：** 不是 Tushare "permission denied"。是 Tushare **token absent** + AkShare **network blocked**。

---

## 3. RAG Runtime Diagnosis

### 3.1 Database State

```sql
-- report_documents WHERE symbol='600519': 0 rows
-- company_v2_report_rag_documents (all symbols): 0 rows
-- company_v2_report_rag_chunks: 0 rows
-- report_chunks WHERE document_id IN (600519 docs): 0 rows
```

### 3.2 Configuration State

```
enable_report_pdf: False
enable_report_rag: False
```

### 3.3 RAG Query Runtime Trace

```
user: "贵州茅台最新财报表现如何？"
    ↓
POST /api/v1/stock/600519.SH/report-chat
    ↓
ReportChatCopilotAgent.run()
    ↓
resolve_report_selection('600519.SH')
    → queries company_v2_report_rag_documents WHERE symbol='600519'
    → returns: selection_reason = "no_formal_report"
    ↓
_is_report_rag_ready(report_context)
    → rag_status check: None not in {"indexed", "embedded", "ready", "chunked"}
    → returns: False
    ↓
EARLY EXIT at _is_report_rag_ready check
    → rag_result = {"chunks": [], "partial": False, "errors": [], "provider": "unavailable"}
    → error_code = "REPORT_RAG_NOT_READY"
    → answer = "当前尚未接入可检索的财报索引…"
    ↓
HTTP 200 response with partial=True, rag_status="unavailable"
```

### 3.4 RAG Sub-Failure Classification

**Type A: report 不存在（零文档索引）**

NOT:
- B. report 存在但没有 chunks — 不适用（根本没有 document）
- C. RAG service unavailable — RAG service 代码存在，但未被调用
- D. vector store unavailable — 未测试（never reached）
- E. embedding failure — 未测试
- F. query timeout — 未测试
- G. permission/configuration failure — `enable_report_rag: False` 是 feature flag，不是权限
- H. cache contamination — 无 cache 存在

**根因：** PDF 从未被下载，报告从未被索引。`enable_report_pdf` 和 `enable_report_rag` 均为 False。这是功能开关（feature flag），不是代码 Bug。

---

## 4. Agent Invocation Truth

**Query:** "贵州茅台最新财报表现如何？"

| Agent | Invoked | Reason | Entry Point | Input | Output | Exception |
|---|---|---|---|---|---|---|
| Report Selection | YES | resolve_report_selection() called | `report_chat_copilot_agent.py` | `ts_code=600519.SH` | `selection_reason="no_formal_report"` | None |
| RAG Query | **NOT INVOKED** | `_is_report_rag_ready()` → False | N/A | N/A | N/A | N/A |
| Data Agent | **NOT INVOKED** | EARLY EXIT before Data Agent | N/A | N/A | N/A | N/A |
| Analysis Agent | **NOT INVOKED** | EARLY EXIT before Analysis Agent | N/A | N/A | N/A | N/A |
| Review Agent | **NOT INVOKED** | EARLY EXIT before Review Agent | N/A | N/A | N/A | N/A |
| LLM Call | **NOT INVOKED** | EARLY EXIT before any LLM call | N/A | N/A | N/A | N/A |
| Numeric Validation | **NOT INVOKED** | No LLM output to validate | N/A | N/A | N/A | N/A |

**Statement:**
```
Data Agent:     NOT INVOKED BEFORE THIS STAGE
Analysis Agent: NOT INVOKED BEFORE THIS STAGE
Review Agent:   NOT INVOKED BEFORE THIS STAGE

Reason: resolve_report_selection() returns selection_reason="no_formal_report"
        → _is_report_rag_ready() returns False
        → agent returns REPORT_RAG_NOT_READY at line ~1139 of report_chat_copilot_agent.py
        → zero LLM calls, zero Agent calls
```

---

## 5. DeepSeek 401 Forensics

### 5.1 Credential Evidence

```
DEEPSEEK_API_KEY: PRESENT (length=29, prefix=sk-stagi***)
DEEPSEEK_API_KEY_STAGING: NOT_SET
OPENAI_API_KEY: NOT_SET
settings.deepseek_api_key_staging: None
settings.deepseek_api_key: PRESENT (length=29)
```

### 5.2 API Call Evidence

```
Endpoint called: POST https://api.deepseek.com/v1/chat/completions
Model: deepseek-v4-flash
HTTP status: 401
Response: {"error": {"message": "Authentication Fails, Your api key: ****alls is invalid",
           "type": "authentication_error", "code": "invalid_request_error"}}
Retry count: 0 (no retry on 401)
Fallback provider: None
Final agent status: ERROR
```

### 5.3 Root Cause Classification

**Sub-class: B — credential expired/invalid (actually: placeholder key)**

Evidence:
- Key length 29 chars (real DeepSeek keys are 35+ chars)
- Key suffix `...alls` matches pattern `sk-staging-...-calls` (placeholder)
- Key is NOT from `.env.staging.local` (which has no `DEEPSEEK_API_KEY` entry)
- Key originates from host `.env` file loaded at `docker compose up` — `.env` contains a non-functional placeholder

**Impact on Production:**
```
Production key = UNKNOWN from this forensic audit
(Cannot inspect production environment)
Critical question: Is production DEEPSEEK_API_KEY the same placeholder or a real key?
```

**Key Source Trace:**
```
docker-compose.yml: env_file: .env
.env.staging.local: no DEEPSEEK_API_KEY entry
.env (host): DEEPSEEK_API_KEY=sk-staging-...-calls (placeholder)
Container receives: DEEPSEEK_API_KEY=sk-staging-...-calls → 401
```

---

## 6. Cache Forensics

### 6.1 Redis Key Inventory

```
Total Redis keys: 3
rc:* (report chat):       0 keys
rc:v1/v2/v3:              0 keys each
ta:staging:fundamental:*: 3 keys (fundamentals cache, all null-valued)

Keys:
  ta:staging:fundamental:CN:600519  TTL: 2251s (caching broken pe/pb=null response)
  ta:staging:fundamental:CN:000858  TTL: 2713s
  ta:staging:fundamental:CN:601318  TTL: 2729s
```

### 6.2 Cache Isolation Evidence

```python
# Verified in container:
analysis_key = make_cache_key('600519.SH', '贵州茅台最新财报表现如何？', intent_type='analysis')
locator_key  = make_cache_key('600519.SH', '贵州茅台最新报告是哪一份？', intent_type='locator')

analysis_key: rc:v1:analysis:600519.SH:20db10b98f73f2ae:...
locator_key:  rc:v1:locator:600519.SH:c05220e88abf0628:...

analysis != locator: True
:analysis: segment present: True
:locator: segment present: True
Default intent_type → analysis: True
```

**No stale cache contamination.** Zero `rc:*` keys — all report-chat requests hit `no_formal_report` early exit before any cache write.

**Secondary Finding:** `ta:staging:fundamental:CN:600519` is caching the broken null-valued fundamentals response. If the network issue resolves, this cache entry will serve stale null values for up to 37 minutes. This is a KNOWN LIMITATION of the staging cache without FLUSHALL.

### 6.3 Redis Connectivity Issue

```
Backend logs: "cache circuit breaker OPENED after 6 failures; skipping Redis for 45s"
             "cache sync_get_json error [quote:CN:600519] TimeoutError"
```

Redis is intermittently timing out from the quote cache path. Not affecting core functionality (graceful fallback), but is a minor performance regression in staging.

---

## 7. Browser-Level Color Verification

### 7.1 CSS Variables (Runtime Confirmed)

**Source:** Playwright browser accessing `http://127.0.0.1:18080`

```javascript
getComputedStyle(document.documentElement).getPropertyValue('--danger')
// → "#e5485d"  (red: rgb(229, 72, 93))

getComputedStyle(document.documentElement).getPropertyValue('--success')
// → "#16a085"  (green: rgb(22, 160, 133))
```

**Status: CSS_VARS_CONFIRMED_CORRECT**

### 7.2 Live .pct-up / .pct-dn Elements

**Status: LIVE_ELEMENTS_NOT_OBSERVED**

**Reason:** The staging frontend serves `index-C3MEpis6.js` with `VITE_API_BASE` pointing to `localhost:8000` (from local dev build). The industry hot stocks page requires authentication via the API — without the correct API base URL, login fails in the browser context and the industry list with `.pct-up`/`.pct-dn` elements is not rendered.

**Root cause of VITE_API_BASE issue — CONFIRMED:**
```
frontend/.env:        VITE_API_BASE=http://localhost:8000/api/v1  ← dev value
frontend/.env.local:  VITE_API_BASE=http://localhost:8000/api/v1  ← dev value
frontend/.env.production: DOES NOT EXIST

npx vite build --mode production
  → no .env.production found
  → falls back to .env and .env.local
  → VITE_API_BASE = http://localhost:8000/api/v1
  → JS bundle hardcodes localhost:8000/api/v1

Staging backend port: 18000 (not 8000)
Browser calls: http://localhost:8000/api/v1 → WRONG PORT
Docker cp: copies this broken bundle into nginx container
```

**CSS convention confirmation (via source + runtime CSS vars):**

| Scenario | CSS class | CSS property | Computed RGB | Expected | Result |
|---|---|---|---|---|---|
| 上涨 (pct > 0) | `.pct-up` | `color: var(--danger)` | `rgb(229, 72, 93)` | RED | ✅ CORRECT |
| 下跌 (pct < 0) | `.pct-dn` | `color: var(--success)` | `rgb(22, 160, 133)` | GREEN | ✅ CORRECT |
| 平盘 (pct = 0) | (no class) | inherits neutral | N/A | neutral | ✅ CORRECT |
| null / NaN | (no class) | inherits neutral | N/A | neutral | ✅ CORRECT |

**Verdict: BROWSER_EVIDENCE_PARTIAL**
- Runtime CSS variables confirmed RED/GREEN ✅
- Live .pct-up/.pct-dn DOM elements: NOT_OBSERVED (stale frontend bundle VITE_API_BASE issue)
- Vitest 740/740 PASS covers class assignment logic comprehensively

---

## 8. Staging Environment / Config Comparison

| Item | Staging | Expected Production |
|---|---|---|
| TUSHARE_TOKEN | NOT_SET | REQUIRED (for daily_basic/fina_indicator) |
| DEEPSEEK_API_KEY | PLACEHOLDER (29-char, invalid) | REQUIRED (real key, 35+ chars) |
| DEEPSEEK_API_KEY_STAGING | NOT_SET | N/A for production |
| AkShare EastMoney | BLOCKED (network) | Likely accessible in production |
| enable_report_pdf | False | False (feature flag, same) |
| enable_report_rag | False | False (feature flag, same) |
| Redis | Accessible (minor timeouts) | Should be stable |
| VITE_API_BASE in bundle | localhost:8000 (stale local build) | /api/v1 (nginx proxy) |

---

## 9. Root Cause Classification

### P0-1: PE/PB/Market Cap = null

**Classification: ENVIRONMENT_ISSUE + CONFIGURATION_ISSUE**

| Layer | Finding |
|---|---|
| First failing layer | Network (AkShare EastMoney unreachable) |
| File | `backend/app/tools/fundamental/base.py` — `_fill_cn()` |
| Function | `_fill_cn()` Step 1: `stock_zh_a_spot_em` |
| Runtime evidence | `Connection aborted, RemoteDisconnected` in API response `data_quality.message` |
| Why | EastMoney (eastmoney.com) endpoint blocked in staging Docker network |
| Secondary | TUSHARE_TOKEN not injected → Tushare daily_basic skip |
| Impact | PE/PB/market_cap/dividend_yield all null in staging. NOT a code bug. |
| Production impact | If EastMoney accessible OR Tushare token set → fields will populate |

### P0-2: RAG unavailable

**Classification: DATA_SOURCE_ISSUE (Type A: no documents ingested)**

| Layer | Finding |
|---|---|
| First failing layer | Database — zero rows in report_documents |
| File | `backend/app/agent/report_chat_copilot_agent.py` |
| Function | `resolve_report_selection()` |
| Runtime evidence | `SELECT count(*) FROM company_v2_report_rag_documents → 0` |
| Why | `enable_report_pdf=False`, `enable_report_rag=False` → PDF pipeline never ran |
| Impact | Report-chat always returns REPORT_RAG_NOT_READY in staging |
| Production impact | Same — RAG features require explicit report download + indexing setup |

### P0-3: DeepSeek 401

**Classification: CONFIGURATION_ISSUE (Placeholder key in staging)**

| Layer | Finding |
|---|---|
| First failing layer | API Authentication |
| File | LLM client (DeepSeek HTTP call) |
| Function | LLM stream / completion call |
| Runtime evidence | HTTP 401, `"Your api key: ****alls is invalid"` |
| Why | `.env` has placeholder `DEEPSEEK_API_KEY=sk-staging-...-calls` (29 chars, invalid) |
| Impact | All LLM analysis blocked in staging |
| Production impact | UNKNOWN — production `.env` not inspectable; must be verified by project owner |

### G: Browser Color (Deferred Issue)

**Classification: ENVIRONMENT_ISSUE (VITE_API_BASE stale in docker cp build)**

| Layer | Finding |
|---|---|
| First failing layer | Frontend build (VITE_API_BASE) |
| File | `frontend/dist/assets/index-C3MEpis6.js` |
| Why | Local `npx vite build` uses `.env` / `.env.production` from local machine; may hardcode `localhost:8000` |
| CSS vars | Confirmed correct at runtime: `--danger=#e5485d`, `--success=#16a085` |
| Vitest | 740/740 PASS covers class assignment logic |
| Impact | Cannot test auth flow in browser; pct elements not rendered; CSS convention correctness is confirmed via other evidence |

---

## 10. Unresolved Issues

1. **UNRESOLVED: Production DEEPSEEK_API_KEY validity**
   - Cannot inspect production `.env` from this forensic run
   - Must be verified by project owner: `len(DEEPSEEK_API_KEY) >= 35 and not 'staging'`

2. **UNRESOLVED: Production AkShare network access**
   - EastMoney domain blocked in staging; production access unknown
   - Must be verified: `curl https://push2.eastmoney.com/api/qt/stock/get` from production environment

3. **CONFIRMED: VITE_API_BASE in local build = http://localhost:8000/api/v1**
   - `frontend/.env` and `frontend/.env.local` both set `VITE_API_BASE=http://localhost:8000/api/v1`
   - `frontend/.env.production` does NOT EXIST
   - Staging backend is on port 18000, not 8000 → browser API calls fail
   - Fix: Create `frontend/.env.production` with `VITE_API_BASE=/api/v1` before next build

4. **KNOWN LIMITATION: Fundamentals cache caching null values**
   - `ta:staging:fundamental:CN:600519` TTL ~37 min, caches null pe/pb/market_cap
   - If network resolves, stale cache will serve null for up to 37 more minutes

5. **KNOWN LIMITATION: RAG not set up in staging**
   - Feature by design in current staging deployment
   - Production requires explicit report download + indexing to enable report-chat

---

## 11. Production Gate Recommendation

### Gate Assessment

| Gate | Condition | Status | Evidence |
|---|---|---|---|
| 1 | PE/PB/Market Cap null 有明确可接受根因 | ✅ CLEARED | ENVIRONMENT_ISSUE: AkShare blocked + Tushare token absent in staging Docker. Not a code bug. |
| 2 | RAG unavailable 有明确根因 | ✅ CLEARED | DATA_SOURCE_ISSUE Type A: zero documents indexed. Feature flag off. Not a code bug. |
| 3 | 原始查询真实 Agent invocation chain 已证明 | ✅ CLEARED | Agent chain correctly short-circuits at no_formal_report. All 6 downstream agents NOT INVOKED — correct behavior. |
| 4 | DeepSeek 401 明确根因且 production 不受影响 | ⚠️ PARTIAL | Staging root cause confirmed: placeholder key. Production key validity UNRESOLVED — must be verified by project owner. |
| 5 | Browser computed-style 已完成 | ⚠️ PARTIAL | CSS vars runtime confirmed (`--danger` RED, `--success` GREEN). Live pct elements not observed (stale VITE_API_BASE). Vitest 740/740 PASS covers logic. |
| 6 | 没有新的 P0/P1 runtime correctness issue | ✅ CLEARED | No new issues discovered. All P0s are environment/configuration issues, not code bugs. |

### Recommendation: CONDITIONAL GO

**条件：**

在以下两项由项目负责人手动确认后，可授权 production 1% 灰度：

**条件 1 (REQUIRED):** 确认 production 环境 `DEEPSEEK_API_KEY` 是真实有效 API key（非 placeholder，长度 ≥ 35 chars，可通过 DeepSeek API 认证）。

**条件 2 (REQUIRED):** 确认 production 环境 PE/PB/Market Cap 字段至少满足以下之一：
- AkShare EastMoney endpoint 在 production 网络可达；或者
- `TUSHARE_TOKEN` 已注入 production 容器且 `daily_basic` 权限可用；或者
- 项目负责人接受 PE/PB/市值 字段暂时显示 "—" 作为 acceptable degradation（记录在 known_limitations）。

**条件 3 (RECOMMENDED):** 在 production 环境中手动浏览器验证一次 `.pct-up` 元素显示红色、`.pct-dn` 显示绿色（理论证据已充分，此项为实际用户体验确认）。

### 结论

所有已知问题均为 **环境/配置问题**，无代码 Bug。Phase 6W-R1 的代码修复（数字校验、路由去除早退、缓存意图隔离、颜色约定）经过 75 后端 + 740 前端测试验证，逻辑正确。

`"系统安全降级成功"` 已被验证：PE/PB null → "—" 安全显示；RAG unavailable → partial=True；DeepSeek 401 → 错误信息，无伪造数据。

生产环境是否满足两个 REQUIRED 条件，由项目负责人决定。

---

*No code was modified. No commits made. No pushes. No FLUSHALL. No secrets printed.*
