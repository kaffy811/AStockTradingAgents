# Company + Agents + Data Diagnostic Report

**诊断轮次**: MVP-R1.3 Post-Deploy
**诊断日期**: 2026-07-28
**诊断员**: Read-only systematic trace (no code modified)
**声明**: 本轮未实施任何业务修复。所有证据来自静态代码分析和本地 .env 读取。

---

## A. 基线信息

| 项 | 值 |
|---|---|
| Branch | `release/demo-staging` |
| HEAD SHA | `9005c0879295833377ef7009f344afb67f93a2a7` |
| Git Status | Clean (无未提交变更) |
| Backend Version | `1.1.0-free-rc1` (app/core/config.py:17) |
| Frontend Build | Built from same commit (dist/ exists) |
| Docker | 未使用 Docker，本地开发模式 |
| 部署环境访问 | **无**：本轮仅分析本地代码 + `.env`；线上与本地是否一致**未确认** |

**本地 .env 功能开关（不含密钥）**:

| 开关 | 值 |
|---|---|
| APP_ENV | development |
| DATA_MODE | free |
| ENABLE_AKSHARE | true |
| ENABLE_BAOSTOCK | true |
| ENABLE_REPORT_PDF | true |
| enable_report_rag | false (config.py 默认) |
| DEFAULT_ANALYSIS_ENGINE | custom_coordinator |
| enable_multi_agent_orchestrator | false |
| pi_real_provider_kill_switch | true (fail-closed) |
| ANALYSIS_RUN_REGISTRY | memory |
| TUSHARE_TOKEN | 存在 (exists=true, length=56, 内容不输出) |
| embedding_provider | mock |

**警告**: TUSHARE_TOKEN 长度为 56 字符；标准 Tushare token 通常为 32 位十六进制字符。长度异常可能表明 token 包含首尾空格，或 token 本身格式有误。**需在部署环境核实**。

---

## B. 症状定位总表

| # | 症状 | 首次异常层级 | 文件:行号 | 直接证据 | 置信度 |
|---|---|---|---|---|---|
| 1 | `MA5[path]` 出现在技术分析 | 后处理层 — sanitize_specialist_output | `app/agents/specialist_analysis_utils.py:11,106` | `_ABS_PATH_RE = re.compile(r"(/[A-Za-z0-9_.@-]+)+")` 匹配 LLM 输出中路径状字符串 | 高 |
| 2 | `未提供数字` 替换日期/代码/价格 | 数字溯源层 — remove_unsupported_numbers | `app/agents/specialist_analysis_utils.py:85,94,97` | `_NUMERIC_RE` 逐片段匹配数字；evidence 集合为空时全量替换 | 高 |
| 3 | 财报查询无实质分析 | 编排层早返回 | `app/agents/chat_orchestrator.py:603-621` | `OrchestratorResult(status='partial_success')` 在调用 Analysis Agent 前直接返回 | 高 |
| 4 | 行业热股颜色反转(上涨绿/下跌红) | 前端 CSS 层 | `frontend/src/components/IndustryHotStocksPanel.vue:382-383` | `.pct-up { color: var(--success) }` / `.pct-dn { color: var(--danger) }` — A股 色彩规则反置 | 高 |
| 5 | 双重 warning banner 同时显示 | 前端组件层 | `DataSourceBanner.vue:15` + `CompanyFundamentalsPanel.vue:583` | 两处独立触发机制均响应 Tushare 权限失败 | 高 |
| 6 | Tushare 权限错误直接可见 | Provider 层 | `app/datasource/tushare_client.py:202` | `TushareAuthError("Tushare 权限不足或 Token 无效: {exc}")` 使用原始 exc 字符串 | 高 |
| 7 | skeleton 在数据展示后未消失 | 前端 loading 状态 | `CompanyFundamentalsPanel.vue:91,445,729` | `diagnosticsLoading` 受多个异步路径控制；若异常路径未进 finally 则保持 true | 中（需实测） |

---

## C. 四条请求 Trace

### Trace A — 公司 Tab (trace_id: TRACE-A-COMPANY-TAB)

```
用户打开 StockDetailView → 切换到 "公司" Tab
  ↓
frontend: StockDetailView.vue:387 — loadProfile() → GET /api/v1/stocks/{market}/{symbol}/profile
  ↓
API: app/routers/stocks.py — /{market}/{symbol}/profile endpoint
  ↓
Service: app/services/coverage_audit_service.py:257 — _fetch_fina_indicator(ts_code)
  ↓
Provider: app/datasource/tushare_client.py:275 — _call("fina_indicator", ts_code=...)
  ↓
TushareAuthError (tushare_client.py:202): HTTP 200 body含权限错误 → raise TushareAuthError
  ↓
asyncio.gather(return_exceptions=True) 捕获异常 → exception对象进结果列表
  ↓
calling code (profitability.py:47, growth.py:56 等) 需检查 isinstance(result, Exception)
  ↓
API 响应: envelope.partial=True, data中相关字段为null
  ↓
frontend CompanyFundamentalsPanel.vue:582-583:
  overviewSnap.value?.partial === true → overviewBanner = {type:'warn', msg:'部分数据获取不完整...'}
  ↓
frontend DataSourceBanner.vue:15:
  dataSourceUnavailable computed → true → 显示 '部分模块数据不完整，请以已披露财报为准'
  ↓
DOM: 两条 warning 同时显示
```

**字段来源分析**:

| 字段 | Provider | 是否依赖 fina_indicator | 当前状态 |
|---|---|---|---|
| 最新价 | AKShare/BaoStock kline | 否 | 应可用 |
| PE(TTM) | etl_daily_basic 或 AKShare | 间接 | 待确认 |
| PB | etl_daily_basic | 间接 | 待确认 |
| 总市值 | etl_daily_basic | 否 | 应可用 |
| ROE | etl_fina_indicator 首选 | **是** | 被 TushareAuthError 阻断 |
| 股息率 | etl_fina_indicator.dv_ttm | **是** | 被 TushareAuthError 阻断 |

---

### Trace B — 财报查询 (trace_id: TRACE-B-FINANCIAL-REPORT)

```
用户输入: "贵州茅台最新财报表现如何？"
  ↓
Chat frontend → POST /api/v1/chat/sessions/{id}/messages/stream
  ↓
app/agents/chat_orchestrator.py — select_skill() / route_query()
  ↓
ReportExplanationSkill.can_handle() 或直接进 orchestrator 报告路径
  ↓
report_locator: 查找 600519 最新正式报告 → 找到 report_context (2025年年报)
  ↓
chat_orchestrator.py:603-608:
  answer = f"已定位到贵州茅台的2025年年度报告。" + "这轮先基于已索引的正式报告建立上下文..."
  return OrchestratorResult(answer=answer, metadata={'status': 'partial_success'})
  ↓ ← 早返回！以下步骤全部跳过
  ↓ [SKIPPED] RAG chunk retrieval
  ↓ [SKIPPED] financial table extraction
  ↓ [SKIPPED] Data Agent
  ↓ [SKIPPED] Analysis Agent
  ↓ [SKIPPED] Review Agent
  ↓
前端显示固定文案，无营收/利润/现金流分析
```

**关键证据**:
- `chat_orchestrator.py:607-621`: `return OrchestratorResult(answer=answer, ...)` 在调用任何 Agent 前直接返回
- `metadata['status'] = 'partial_success'` 而非 `success`，但前端可能将两者都渲染为"完成"
- 硬编码文案定义位置: `chat_orchestrator.py:603-605` 和 `report_explanation_skill.py:626-627`

---

### Trace C — 技术分析 (trace_id: TRACE-C-TECHNICAL)

```
用户请求贵州茅台技术面分析
  ↓
TechnicalAnalystAgent.analyze() — technical_analyst.py:155
  ↓
S0: technical_indicator_service.calculate(bars) → {ma5: 1255.19, ...}
  ↓
S1: _build_user_prompt() — technical_analyst.py:237
    用户 prompt 包含: "MA5  = 1255.19"
    evidence_text = 整个 user_content (含所有数字)
  ↓
S2: self._llm.chat(messages) → LLM 原始响应 (未可见)
    LLM 可能输出如: "MA5=1255.19", "2026-07-28", "600519"
  ↓
S3: sanitize_specialist_output(report, evidence_text=user_content)
    → specialist_analysis_utils.py:101
  ↓
S4 [路径子]: _ABS_PATH_RE.sub("[path]", text)
    specialist_analysis_utils.py:106
    _ABS_PATH_RE = r"(/[A-Za-z0-9_.@-]+)+"
    如果 LLM 输出含 "/ma/5" 等路径状字符串 → 替换为 [path]
    → "MA5[path]" 出现于此阶段
  ↓
S5 [路径乙]: remove_unsupported_numbers(text, evidence_text)
    specialist_analysis_utils.py:85
    _NUMERIC_RE = r"(?<![A-Za-z])[-+]?\d+(?:\.\d+)?%?"
    将 LLM 输出与 evidence_text 中的数字集合对比
    问题1: 日期 "2026-07-28" → 匹配 "2026", "07", "28" 三个独立 token
            若其中任何一个不在 evidence_text 数字集 → 替换为 "未提供数字"
            → "2026未提供数字-未提供数字-28"  (实际症状符合)
    问题2: 股票代码 "600519" → 一个整体 token
            若 prompt 中此代码格式不同 → 替换 → "未提供数字00519" (实际症状符合)
  ↓
S6: 最终 report 含 "未提供数字" 和 "[path]"，但 status = success
    review_status 在 sanitize 之前已确定
```

**"未提供数字"第一次出现**: `specialist_analysis_utils.py:94` (evidence 为空时) 或 `97` (token 不在 allowed 集)
**"MA5[path]"第一次出现**: `specialist_analysis_utils.py:106`

---

### Trace D — 行业热股颜色 (trace_id: TRACE-D-COLOR)

```
用户查看同行业热门股票列表
  ↓
GET /api/v1/industries/{id}/hot-stocks
  → change_pct: 19.80 (numeric, API 层)
  ↓
前端 IndustryHotStocksPanel.vue:70
  :class="changePctClass(item.score_factors?.change_pct)"
  ↓
IndustryHotStocksPanel.vue:235-238 (本地函数):
  changePctClass(pct):
    if (pct == null || !Number.isFinite(pct)) return ''   ← 如果 pct 为字符串且含%则 NaN → 返回 '' → 黑色
    return pct > 0 ? 'pct-up' : pct < 0 ? 'pct-dn' : ''
  ↓
CSS IndustryHotStocksPanel.vue:382-383:
  .pct-up { color: var(--success); }  ← 绿色 (上涨) — A股应为红色 ← BUG
  .pct-dn { color: var(--danger);  }  ← 红色 (下跌) — A股应为绿色 ← BUG
  ↓
DOM 最终: 上涨股票 class="col-change pct-up" → color: green ← 错误
         下跌股票 class="col-change pct-dn"  → color: red ← 错误
         空值股票  class="col-change"         → color: 继承 (可能黑色) ← 导致"显示黑色"
```

**对比正确实现**:
- `IndustryStockCard.vue:201-202`: `.up { color: var(--danger) }` / `.down { color: var(--success) }` — 正确 A股
- `WatchlistStockCard.vue:296-297`: `.wsc-chg.up { var(--danger) }` / `.wsc-chg.down { var(--success) }` — 正确 A股

---

## D. Tushare Provider/Fallback 调查结果

### 错误识别机制

**文件**: `app/datasource/tushare_client.py:199-203`

```python
except Exception as exc:
    err_msg = str(exc)
    if "40001" in err_msg or "权限" in err_msg or "token" in err_msg.lower():
        raise TushareAuthError(f"Tushare 权限不足或 Token 无效: {exc}") from exc
    raise TushareError(f"Tushare {func_name} 调用失败: {exc}") from exc
```

- Tushare 接口返回 **HTTP 200 + 业务错误 msg** (`{"code":-2001,"msg":"抱歉，您没有接口..."}`)
- TushareAuthError 由字符串匹配触发（`40001` 或 `权限` 或 `token`）
- **无 ProviderPermissionError 统一基类**；只有 `TushareAuthError`（TushareError 子类）

### 权限错误与限流的区别

| 错误类型 | 异常类 | 识别条件 |
|---|---|---|
| Token 无效/无权限 | TushareAuthError | `40001` / `权限` / `token` in msg |
| 限流 | TushareRateLimitError | token bucket超时 (acquire_timeout=10s) |
| 网络/其他 | TushareError | 以上条件均不满足 |

### 模块级 Fallback

`profitability.py:47`, `growth.py:56`, `solvency.py:54`, `operation_capability.py:60` 均用:
```python
fi_result, inc_result = await asyncio.gather(fi_task, inc_task, return_exceptions=True)
```

这意味着 fina_indicator 失败**不会导致整个模块函数抛异常**，而是 `fi_result = TushareAuthError(...)`；调用方需手动检查并标记 `partial=True`。

### 是否反复重试无权限接口

未找到针对 `TushareAuthError` 的重试禁止逻辑。无 capability probe 或权限缓存机制。若每次 Company Tab 加载都调用 `get_fina_indicator`，则会**每次都收到 401 等效错误**，造成不必要的 Tushare API 消耗。

### AKShare/BaoStock Fallback

`coverage_audit_service.py:147` 描述了优先级链:
```
fina（财务）优先级: etl_fina_indicator → akshare(报表/指标) → baostock
```
但该链是否在所有 Company Tab 模块中实际生效，**需逐模块核实**。

---

## E. Company API 与 Frontend Adapter 字段对照

> **注意**: 无法捕获实时 API 响应；以下基于代码静态分析。

### 已知字段路径

| 字段 | 后端字段名 | 来源 Provider | 前端读取路径 | 潜在漂移 |
|---|---|---|---|---|
| ROE | `roe` (etl_fina_indicator) | Tushare ETL | `moduleData['profitability']` | 依赖 Tushare 权限 |
| 股息率 | `dv_ttm` (etl_fina_indicator) | Tushare ETL | 未确认前端字段 | 依赖 Tushare 权限 |
| 总市值 | `total_mv` (etl_daily_basic) | Tushare ETL | 未确认 | 应可用 |
| PE(TTM) | `pe_ttm` (etl_daily_basic) | Tushare ETL | 未确认 | 应可用 |

**API payload 实际结构**: 未确认（需实时抓包）

---

## F. Skill 路由与 RAG/Agent 调用证据

### "贵州茅台最新财报表现如何？" 路由决策

**实际 Skill 选择**:

由 `chat_orchestrator.py` 处理，在 Skill 层之外有一个**报告直接定位路径**，当能找到 entity + report 时直接返回，不进入任何 Skill 的 Agent pipeline。

**关键代码** (`chat_orchestrator.py:600-621`):
```python
report_context = selection.metadata()
report_label = report_context.get("title") or "最新正式财报"
year_label = f"{report_context.get('report_year')}年" if ...
answer = (
    f"已定位到{entity_hint.get('name') or entity_hint['symbol']}的{year_label}{report_label}。"
    "这轮先基于已索引的正式报告建立上下文；如果需要原文，请继续问这份报告的官方 PDF。"
    + _DISCLAIMER
)
return OrchestratorResult(answer=answer, ...)  # ← 直接返回，不调用 Agent
```

**备选定义位置** (`report_explanation_skill.py:626-627`): 相同文案也在该 Skill 内，说明两条路径均有该行为。

**结论**: 报告被"找到"后执行**提前返回**，未触发：
- RAG chunk retrieval
- financial table extraction
- Data Agent
- Analysis Agent
- Review Agent

---

## G. "未提供数字"逐阶段快照

| 阶段 | 内容 | 状态 |
|---|---|---|
| S0 原始指标 | `ma5=1255.19, latest_close=1315.90, last_date='2026-07-28'` | 正常 |
| S1 Prompt | `MA5  = 1255.19` / `截至日期 2026-07-28` | 正常 |
| S2 LLM 原始响应 | **未确认** — 需实时 trace | 未知 |
| S3 _ABS_PATH_RE.sub | 若 LLM 输出含 `/ma/5` → `[path]` | S3 首次出现 `[path]` |
| S4 remove_unsupported_numbers | `_NUMERIC_RE` 匹配 `2026`, `07`, `28` → 逐片替换 | S4 首次出现 `未提供数字` |
| S5 Review Agent | **不运行** — 在 sanitize_specialist_output 之后；review 在 Analysis Agent 内部 | N/A |
| S6 API 响应 | 含 `未提供数字` 和 `[path]`，status=success | 污染已传递 |
| S7 前端渲染 | 原样渲染为 DOM 文本 | 用户可见 |

### 关键问题 — _NUMERIC_RE 逐片匹配

**正则**: `r"(?<![A-Za-z])[-+]?\d+(?:\.\d+)?%?"`

此正则将 `2026-07-28` 拆解为三个 token: `2026`, `07`, `28`。

- `2026` 在 evidence 中（prompt 含 "2026-07-28"）→ 允许
- `07` 在 evidence 中可能有（若月份出现在 prompt 中）→ 允许
- `28` 同上

但问题在于: **LLM 输出的数字格式可能与 prompt 数字格式不同**:
- Prompt: `2026-07-28` → evidence 集包含 `2026`, `07`, `28`
- LLM 输出: `2026年7月28日` → 匹配 `2026`, `7`, `28` → `7` (without leading zero) NOT in `{'07'}` → 替换

---

## H. "MA5[path]"逐阶段快照

| 阶段 | MA5 表达 | 状态 |
|---|---|---|
| 原始数据 | `indicators['ma5'] = 1255.19` (float) | 正常 |
| Prompt 构造 | `MA5  = 1255.19` | 正常 |
| LLM 原始回答 | **未知** — 可能含 `/ma/5` 或其他路径状字符串 | 未确认 |
| _ABS_PATH_RE.sub | `specialist_analysis_utils.py:106` | **首次 MA5[path] 出现位置** |
| 最终响应 | `MA5[path]` 或 `MA5 = [path]` 传递给前端 | 污染 |

**根因**: `_ABS_PATH_RE = re.compile(r"(/[A-Za-z0-9_.@-]+)+")` 过于宽泛。

合法匹配示例: `/usr/local/bin`, `/etc/config.yaml`
误匹配示例: `/ma/5` (在 LLM 输出中如 "MA5=/ma/5" 或 "price MA5 = /some/path/5.0")

---

## I. Review Agent 与 success 状态调查

### success 判定

**文件**: `app/agents/technical_analyst.py:171`
```python
report = self._llm.chat(messages, temperature=0.3)
return sanitize_specialist_output(report, evidence_text=user_content)
```

Technical Analyst 路径中**没有独立 Review Agent**。`sanitize_specialist_output` 执行后直接返回 report 文本，status 由调用者设置。

### 后处理与 Review 的顺序

对于 Technical Analyst:
1. LLM 生成 report
2. `sanitize_specialist_output()` → `_ABS_PATH_RE.sub` + `remove_unsupported_numbers`
3. 返回（已含 `未提供数字` 和 `[path]`）
4. 调用层将 status 设置为 `success`

**Review Agent 在 sanitize 之后运行但对 Technical Analyst 不适用**: Review Agent 是综合分析 (`ComprehensiveAnalysisCoordinator`) 的专用步骤，在 `_finalize_synthesis_report()` 中调用 `_remove_unsupported_numbers()`。对单独的 `technical_only` 路径，只有 `sanitize_specialist_output()`。

### 前端 status badge

`status=success` 由没有抛出异常决定。`未提供数字` 替换本身不触发异常，因此 status 不变。

---

## J. 涨跌颜色 DOM/CSS 调查

### 根因定位

**错误组件**: `frontend/src/components/IndustryHotStocksPanel.vue`

```css
/* LINE 382-383 — WRONG A股 convention */
.pct-up { color: var(--success); font-weight: 600; }  /* 上涨 → 绿色 ← 错误 */
.pct-dn { color: var(--danger);  font-weight: 600; }  /* 下跌 → 红色 ← 错误 */
```

**正确实现** (`IndustryStockCard.vue:201-202`):
```css
.up   { color: var(--danger);  }  /* 上涨 → 红色 ← 正确 A股 */
.down { color: var(--success); }  /* 下跌 → 绿色 ← 正确 A股 */
```

### DOM 预测

| 股票 | pct_chg | changePctClass() | 返回 class | CSS color |
|---|---|---|---|---|
| 上涨 +19.80 | 19.80 | `pct-up` | `col-change pct-up` | var(--success)=绿 ← 错 |
| 下跌 -3.32 | -3.32 | `pct-dn` | `col-change pct-dn` | var(--danger)=红 ← 错 |
| 平盘 0 | 0 | `''` | `col-change` | 继承色(通常黑/灰) |
| 数据为字符串含% | `'19.80%'` | `''` | `col-change` | 继承色(黑) |

### 其他组件对比

| 组件 | 类名约定 | 颜色映射 | 是否正确 |
|---|---|---|---|
| `IndustryHotStocksPanel.vue` | `pct-up` / `pct-dn` | up=success(绿), dn=danger(红) | **错误** |
| `IndustryStockCard.vue` | `up` / `down` | up=danger(红), down=success(绿) | 正确 |
| `WatchlistStockCard.vue` | `up` / `down` | up=danger(红), down=success(绿) | 正确 |
| `HomeDashboardPanel.vue` | inline `'up'`/`'down'` | 依赖父级 CSS | 需核实 |

---

## K. 部署、缓存、版本一致性调查

| 项目 | 状态 |
|---|---|
| 前后端 commit 一致 | 本地一致；线上未确认 |
| API server 与 worker 镜像 | 未使用 Docker；本地单进程 |
| Report chat cache | 启用，TTL=1800s，version="v1"；旧格式 partial_success 可能命中 |
| Analysis run registry | memory (in-process)；部署多 worker 时 SSE 会失效 |
| Alembic 版本 | 最新: p4q5r6s7t8u9 (2026-07-28 add_email_verified_at) |
| Redis schema version | 未发现版本控制；缓存 key 不含 schema_version |
| 浏览器 bundle | 新 build 已生成 (dist/ 存在) |
| CDN 缓存 | 未确认（无 CDN 配置文件检查） |

---

## L. 已确认根因

### RC-1: MA5[path]

**根因**: `specialist_analysis_utils.py:11` 的 `_ABS_PATH_RE = re.compile(r"(/[A-Za-z0-9_.@-]+)+")` 过于宽泛，将 LLM 输出中路径状字符串误匹配，在 `sanitize_specialist_output()` 的 `line:106` 替换为 `[path]`。

**首次出现函数**: `sanitize_specialist_output()` — `specialist_analysis_utils.py:101`
**首次替换行**: `specialist_analysis_utils.py:106`

---

### RC-2: 未提供数字

**根因**: `specialist_analysis_utils.py:85-98` `remove_unsupported_numbers()` 使用 `_NUMERIC_RE` 逐片段匹配数字：

1. 当 `evidence_text` 为空时 (`line:93-94`): 全量替换所有数字
2. 当 LLM 输出数字格式与 evidence 中格式不一致时 (`line:95-97`): 单片 token 不在 allowed 集

日期 `2026-07-28` → 三个 token `2026`/`07`/`28`；股票代码 `600519` → 一个整体 token。若格式稍有差异（如月份有无前导零、代码含市场后缀）则被替换。

**首次出现函数**: `remove_unsupported_numbers()` — `specialist_analysis_utils.py:85`
**首次替换行**: `specialist_analysis_utils.py:94` (空 evidence 时) / `97` (token 不在 allowed 时)

---

### RC-3: 财报查询无实质分析

**根因**: `chat_orchestrator.py:603-621` 在成功定位报告 context 后立即 `return OrchestratorResult`，不调用任何 Agent。这是一个有意的"报告定位"快捷路径，但其响应文案令用户误以为已经进行了财报分析。

**首次出现行**: `chat_orchestrator.py:607`

---

### RC-4: 行业热股颜色反转

**根因**: `IndustryHotStocksPanel.vue:382-383` CSS 使用美股颜色规则（绿=上涨，红=下跌），与同项目中其他组件（`IndustryStockCard.vue`, `WatchlistStockCard.vue`）的 A 股规则（红=上涨，绿=下跌）相反。

**首次出现行**: `IndustryHotStocksPanel.vue:382`

---

### RC-5: 双重 Warning Banner

**根因**: `DataSourceBanner.vue:15` 和 `CompanyFundamentalsPanel.vue:583` 是两个独立的 warning 机制，但两者同时响应同一个 Tushare 权限失败事件，造成重复展示。

---

## M. 尚未确认但高概率的问题

| # | 问题 | 缺少的证据 |
|---|---|---|
| H-1 | Skeleton 持续显示 | 需要浏览器 console.log 或 network tab 确认 `diagnosticsLoading` 何时变为 false，以及是否有未处理异常阻断 finally |
| H-2 | PE/PB/市值等字段显示 "—" | 需要实时抓包 `/stocks/{market}/{symbol}/profile` 的完整 JSON response |
| H-3 | change_pct 为字符串导致 NaN | 需要抓包 API response 确认 change_pct 的实际 JS 类型 |
| H-4 | Tushare token 含首尾空格 | 本地 .env token 长度 56 字符；标准 token 通常 32 字符；需部署环境核实 |
| H-5 | 综合分析 _remove_unsupported_numbers 是否严重影响技术面 | 需要确认 technical_only scope 是否经过 coordinator._finalize_synthesis_report |

---

## N. 推荐的后续修复顺序

> 本轮未实施修复。以下为建议，需项目负责人确认后执行。

**P0 — 立即阻断，影响核心可用性**:

1. **RC-1 + RC-2** (specialist_analysis_utils.py): 两处均在同一文件。建议修复：
   - `_ABS_PATH_RE`: 增加负向前瞻避免误匹配指标格式；或在 path 替换后、LLM 输出阶段前限制适用场景
   - `remove_unsupported_numbers`: 改为整体 number token 匹配（不拆日期）；对日期格式、股票代码格式做归一化；明确添加 symbol、日期、百分比到 allowed 白名单

2. **RC-3** (chat_orchestrator.py): 报告定位后不应直接返回；应继续执行 RAG retrieval + Analysis Agent；或将 partial_success 响应改为引导语，明确说明"分析待启动"

**P1 — 用户体验严重受损**:

3. **RC-4** (IndustryHotStocksPanel.vue): 将 CSS 从美股规则改为 A 股规则：
   - `.pct-up { color: var(--danger); }` (红)
   - `.pct-dn { color: var(--success); }` (绿)

4. **RC-5** (双重 warning): 合并两条 warning 为单一展示逻辑，避免重复

**P2 — 改进性优化**:

5. **Tushare 权限缓存**: 添加 capability probe；一旦检测到 TushareAuthError 则缓存该状态 (TTL 5-15 分钟) 避免重复调用无权限接口
6. **loading skeleton**: 确认 `diagnosticsLoading` 所有异常路径均有 finally 保障
7. **token 验证**: 在 startup 或首次请求时验证 Tushare token 格式（32 字符 hex）

---

*本报告基于本地代码静态分析生成。所有"未确认"项需在实际运行环境中验证。本轮未修改任何业务代码。*
