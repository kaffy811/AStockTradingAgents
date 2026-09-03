# Phase 6N-8B 综合修复交付报告

生成时间：2025-07  
版本：RC Final Candidate

---

## 一、变更文件清单

### 后端（Python / FastAPI）

| 文件 | 变更类型 | 核心变更内容 |
|------|----------|-------------|
| `backend/app/core/error_codes.py` | 修改 | 新增 8 个错误码：`QUOTE_PROVIDER_UNAVAILABLE`、`SHARE_CAPITAL_MISSING`、`ALL_NULL_ROWS`、`CACHE_UNAVAILABLE`、`DATA_PACK_EMPTY`、`REPORT_NOT_INGESTED`、`AI_KEY_MISSING`、`SOURCE_CHUNKS_EMPTY` |
| `backend/app/services/cache_service.py` | 修改 | Redis 熔断器（5 次失败触发，45s 冷却）；fail-open；60s 去重告警；`cache_status()` 公开函数 |
| `backend/app/routers/fundamentals_compat.py` | 修改 | diagnostics 端点增强：`cache_status`、`auth_status`、`provider_status`、`pdf_status`、`module_fill_chains`；新增 `_get_cache_status()`、`_get_provider_status()`、`_build_fill_chains()` |
| `backend/app/tools/reports/sse_report_search_tool.py` | 修改 | SSE 404 不重试（直接 `return []`）；`_sse_log_once()` 去重 debug 日志 |
| `backend/app/services/report_metric_extract_service.py` | 新建 | PDF 年报指标提取服务；9 个指标定义；`extract_metrics_from_text()`、`filter_confirmed()`、`extract_and_store_metrics()`、`get_confirmed_metrics_for_stock()` |
| `backend/tests/fundamental/test_phase6n8b_data_completion_and_errors.py` | 新建 | 28 个验收测试 |

### 前端（Vue 3 / Pinia）

| 文件 | 变更类型 | 核心变更内容 |
|------|----------|-------------|
| `frontend/src/stores/auth.js` | 修改 | 新增 `authReady` computed（同步 localStorage，无 async 等待） |
| `frontend/src/components/fundamentals/AiAnalysisCard.vue` | 修改 | `_classifyAiUnavailMsg()` 细分 AI 不可用原因（AUTH_REQUIRED / DATA_PACK_EMPTY / REPORT_NOT_INGESTED / AI_KEY_MISSING / SOURCE_CHUNKS_EMPTY） |
| `frontend/src/components/fundamentals/DataSourceBanner.vue` | 修改 | 新增 5 种 banner 类型：`cache_timeout`、`provider_network`、`provider_empty`、`all_null_rows_hidden`、`pdf_not_found`；`auth_required` 文案更新 |
| `frontend/src/utils/fundamentalAdapters.js` | 修改 | 新增 `hasDisplayableData(rows, coreFields)` 导出函数；0 = 有效值，null/undefined/""/"-"/NaN = 空 |
| `frontend/src/components/CompanyFundamentalsPanel.vue` | 修改 | `moduleHasRows()` 改用 `hasDisplayableData()`，全空行模块自动隐藏 |
| `frontend/src/components/fundamentals/UnavailableModulesPanel.vue` | 修改 | 新增 `sectionReasons` prop；`REASON_HINTS` 映射；标题改为"暂无可展示数据"；`ALL_NULL_ROWS` 时专项提示 |
| `frontend/src/components/fundamentals/ReportDocumentsPanel.vue` | 修改 | 空状态下展示 `discovery_attempts`（提供商 / 年份 / 状态列表） |

---

## 二、各项修复详述

### 1. Auth 401 归因修正

**问题根因**：后端 BaoStock / AkShare 网络错误被 baseFetch 误判为 401 → 前端弹"登录失效"。  
**修复**：  
- 新增 `QUOTE_PROVIDER_UNAVAILABLE` 错误码，HTTP 状态保持 502/503  
- `DataSourceBanner` 识别新错误码，展示"数据源暂时不可用"而非触发重新登录  
- `auth_required` Banner 文案明确为"登录已过期，请重新登录后查看行情、新闻和自选股数据"

### 2. Redis 熔断器

```
失败计数 ≥ 5 次 → 熔断器 OPEN（持续 45s）
熔断器 OPEN 期间：sync_get_json / sync_set_json / sync_exists 立即返回 None/False（fail-open）
同一 key 60s 内只打一次 WARNING 日志（去重）
cache_status() → "unavailable" | "ok"
```

### 3. 行情模块数据填充链（Quote Fill Chain）

`fundamentals_compat.py` diagnostics 端点的 `module_fill_chains` 字段描述每个模块的数据来源顺序：

```
quote_snapshot:   Cache → Eastmoney → Sina → AkShare → BaoStock kline
overview:         Cache → Eastmoney → AkShare
financial_ratios: Cache → AkShare → BaoStock
...
```

### 4. 财务模块数据填充链（Financial Fill Chain）

每个模块（growth / profitability / solvency / cashflow / capital_structure）均在 `_MODULE_FALLBACK_CHAINS` 中注册，diagnostics 端点返回实际填充情况及 `filled_by` 字段。

### 5. PDF 年报指标提取（`report_metric_extract_service.py`）

- 9 个目标指标：营业收入、归母净利润、经营活动现金流量净额、总资产、归母净资产、基本 EPS、加权 ROE、资产负债率、每股股利  
- 正则 + 单位缩放（亿元/万元/元）  
- `confidence ≥ 0.75` → `extracted_confirmed`，进入核心卡片  
- `confidence < 0.75` → `candidate`，不进入核心卡片  
- 不编造数值；RAG chunk 仅作证据  
- 异步 upsert 写入 `report_extracted_metrics` 表

### 6. 全空行自动隐藏（All-Null Row Detection）

```js
// fundamentalAdapters.js
export function hasDisplayableData(rows, coreFields) {
  // 0 视为有效值；null/undefined/""/"-"/NaN 视为空
  // 任意一行有 ≥1 个有效值 → return true
}
```

`CompanyFundamentalsPanel.moduleHasRows()` 调用此函数，全空行模块移入 `UnavailableModulesPanel` 并显示 `ALL_NULL_ROWS` 原因提示。

### 7. SSE 404 去重降噪

```python
# sse_report_search_tool.py
if resp.status_code == 404:
    _sse_log_once(url)   # 同一 URL 只打一次 debug 日志
    return []            # 不重试，不抛异常
```

### 8. AI 不可用原因细分

`AiAnalysisCard._classifyAiUnavailMsg()` 根据 `envelope.errorCode` 映射：

| 错误码 | 展示文案 |
|--------|----------|
| `AUTH_REQUIRED` | 请登录后查看 AI 分析。 |
| `DATA_PACK_EMPTY` | 当前结构化财务数据不足，AI 无法生成分析。 |
| `REPORT_NOT_INGESTED` | 尚未接入可检索的年报 PDF，AI 分析暂不可用。 |
| `AI_KEY_MISSING` | AI 服务未配置，暂不可用。 |
| `SOURCE_CHUNKS_EMPTY` | 未检索到可引用的年报片段，AI 分析暂无法生成。 |

### 9. Diagnostics fallback_chain 端点

`GET /api/v1/fundamentals/{ts_code}/diagnostics` 新增字段：

```json
{
  "cache_status": "ok | unavailable",
  "auth_status": "authenticated | unauthenticated",
  "provider_status": "ok | degraded | unavailable",
  "pdf_status": "ingested | not_ingested | error",
  "module_fill_chains": [
    {
      "module": "quote_snapshot",
      "chain": ["cache", "eastmoney", "sina", "akshare", "baostock"],
      "filled_by": "eastmoney",
      "status": "ok"
    },
    ...
  ]
}
```

---

## 三、测试结果

### Phase 6N-8B 验收测试

```
backend/tests/fundamental/test_phase6n8b_data_completion_and_errors.py
28 passed, 1 warning (passlib/crypt 弃用，与本次变更无关)
```

测试覆盖：
- Auth 错误码区分（401 vs 502）
- Redis 熔断器触发与恢复
- `cache_status()` 函数
- Quote provider 错误码
- SSE 404 不重试
- PDF 指标提取（基础 / 多值 / 低置信度过滤 / 空文本）
- `hasDisplayableData` 全空行检测
- 错误码无重复
- Diagnostics 结构字段完整性
- 去重告警窗口

### 全量回归

```
2515 passed, 96 warnings, 0 failed
运行时间：4 分 27 秒
```

### 前端构建

```
✓ built in 2.58s（无 TypeScript/ESLint 错误，仅 chunk size 信息提示）
```

---

## 四、已知局限 / 后续待办

| 项目 | 状态 | 说明 |
|------|------|------|
| BaoStock kline 行情填充（实际数据管道） | 未实现 | 目前 fill chain 元数据已注册，但 `quote_snapshot` 工具层 BaoStock kline fallback 逻辑尚未接入 |
| AkShare 财务报表填充（growth/solvency 等） | 未实现 | fill chain 元数据已注册，工具层实际调用需在下一 sprint 完成 |
| `report_extracted_metrics` DB migration | 未创建 | 需 `alembic revision --autogenerate` 后部署 |
| coverage_audit.py 脚本运行 | 未运行 | 需在 DB + 行情服务启动后执行 |

---

## 五、RC Final Walkthrough 就绪评估

| 维度 | 状态 |
|------|------|
| 后端服务无崩溃（2515 tests pass） | ✅ |
| 前端构建无报错 | ✅ |
| 401 不再被误判为 BaoStock/AkShare 错误 | ✅ |
| Redis 不可用时 fail-open（不 500） | ✅ |
| AI 不可用时有明确分类提示（非通用"暂不可用"） | ✅ |
| 全空行模块自动隐藏 | ✅ |
| SSE 404 不刷屏日志 | ✅ |
| Diagnostics 端点字段完整 | ✅ |
| PDF 指标提取服务可导入、可测 | ✅ |
| 行情/财务模块 fill chain 元数据注册 | ✅ |
| 行情/财务模块 fill chain 实际数据管道 | ⏳ 下一 sprint |

**结论**：核心 UX 路径（行情、财务面板、AI 分析、报告文档、Diagnostics）已达到 RC 质量门槛，可进行 advisor demo。fill chain 数据管道为后台优化项，不阻塞演示。
