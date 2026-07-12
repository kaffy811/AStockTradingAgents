# Phase 6D — ReportDiscoveryAgent 设计文档

**日期:** 2026-07-06  
**状态:** 已实现 ✓  
**版本:** Phase 6D

---

## 1. 功能概述

Phase 6D 实现了自动搜索上市公司公开财报 PDF 的完整链路：

```
前端"自动查找财报"按钮
    ↓
POST /api/v1/stocks/CN/{code}/reports/discover/latest
    ↓
ReportDiscoveryAgent (并发搜索 3 个来源)
    ├── CNINFO (巨潮资讯)   ← 通用 A 股，优先
    ├── SSE (上交所)        ← 沪市股票
    └── SZSE (深交所)       ← 深市股票
    ↓
候选去重 + 置信度打分
    ↓
confidence >= 0.75 → 自动录入 report_documents
confidence < 0.75  → 返回候选，需人工确认
    ↓
前端 ReportDocumentsPanel 显示 PDF 图标
    ↓
点击 GET /api/v1/stocks/{market}/{code}/reports/{report_id}/pdf
    ↓
安全 302 Redirect → 公开 PDF URL
```

---

## 2. 数据源说明

### 2.1 CNINFO（巨潮资讯）— 主要来源

- **URL:** `http://www.cninfo.com.cn/new/hisAnnouncement/query`
- **协议:** POST，application/x-www-form-urlencoded
- **覆盖:** 所有 A 股（沪市、深市、北交所、科创板）
- **鉴权:** 无需 API Key，公开接口
- **PDF 域名:** `static.cninfo.com.cn`
- **Rate limit:** 每次请求前等待 1.5 秒

### 2.2 SSE（上交所）— 沪市补充

- **URL:** `https://query.sse.com.cn/search/getSearchList.do`
- **覆盖:** 仅沪市股票（代码以 6、5 开头）
- **注意:** 响应格式可能因 API 版本变化，工具已实现多字段名兼容

### 2.3 SZSE（深交所）— 深市补充

- **URL:** `http://www.szse.cn/api/search/announcement`
- **协议:** POST，application/json
- **覆盖:** 仅深市股票（代码以 0、2、3 开头）
- **PDF 域名:** `disc.szse.cn`

---

## 3. 新增文件清单

### Backend

| 文件 | 说明 |
|---|---|
| `app/tools/reports/__init__.py` | 包初始化 |
| `app/tools/reports/base.py` | BaseReportSearchTool + score_candidate 打分函数 |
| `app/tools/reports/cninfo_report_search_tool.py` | 巨潮资讯搜索工具 |
| `app/tools/reports/sse_report_search_tool.py` | 上交所搜索工具 |
| `app/tools/reports/szse_report_search_tool.py` | 深交所搜索工具 |
| `app/agents/report_discovery_agent.py` | ReportDiscoveryAgent 协调器 |
| `app/services/report_document_service.py` | upsert + 查询服务 |
| `app/routers/report_discovery.py` | 3 个 API 端点 |
| `alembic/versions/2026_07_06_0002-d2e3f4a5b6c7_add_report_discovery_fields.py` | DB migration |
| `tests/fundamental/test_phase6d_report_discovery.py` | 15 测试 |

### Frontend

| 文件 | 说明 |
|---|---|
| `components/fundamentals/ReportDocumentsPanel.vue` | 全量重写，新增发现按钮/PDF 图标/状态展示 |
| `components/CompanyFundamentalsPanel.vue` | 传入 market/stockCode props |

### Docs

| 文件 | 说明 |
|---|---|
| `docs/18_report_discovery_agent.md` | 本文档 |

---

## 4. ReportDiscoveryAgent 设计

### 4.1 discover() 方法

```python
agent.discover(
    stock_code: str,    # e.g. "600519"
    company_name: str,  # e.g. "贵州茅台"
    report_type: str,   # annual/semi/q1/q3
    report_year: int,   # e.g. 2024
) -> dict
```

**流程:**
1. 并发调用 3 个 tool.search() (asyncio.gather)
2. 合并所有候选
3. 按 pdf_url 去重（不同来源找到同一 PDF 只保留一条）
4. 过滤 confidence < 0.35 的候选
5. 按 confidence 降序排列
6. 返回 candidates / high_confidence / errors / partial

### 4.2 discover_latest() 方法

```python
agent.discover_latest(
    stock_code: str,
    company_name: str,
    report_year: int,
) -> dict
```

**流程:**
1. 并发搜索 4 种 report_type: [annual, semi, q1, q3]
2. 每种取最高置信度的候选
3. 返回合并结果

---

## 5. Confidence Scoring 规则

| 条件 | 分值变化 |
|---|---|
| 基础分 | +0.50 |
| stock_code 在标题中出现 | +0.15 |
| company_name（前4字）在标题中出现 | +0.10 |
| report_type 关键词匹配 | +0.15 |
| report_year 在标题中出现 | +0.10 |
| 标题含「摘要」 | -0.25，加 warning |
| 标题含「审计报告」「社会责任」等非定期报告关键词 | -0.50（直接返回） |
| 最高分 | 1.00 |
| 最低分 | 0.00 |

**自动入库阈值:** `confidence >= 0.75`  
**最低展示阈值:** `confidence >= 0.35`（低于此值不展示）

---

## 6. report_documents 新增字段（migration d2e3f4a5b6c7）

| 字段 | 类型 | 说明 |
|---|---|---|
| `pdf_url` | String(500) | 直接 PDF 下载 URL |
| `report_year` | Integer | 报告年份（如 2024） |
| `source` | String(20) | cninfo/sse/szse/manual |
| `download_status` | String(20) | pending/downloaded/failed |
| `confidence` | Float | 置信度 0.0-1.0 |
| `warnings_json` | Text | JSON 格式警告列表 |

**去重逻辑:**
1. 先按 `pdf_url` 去重（同一 PDF 文件）
2. 再按 `ts_code + report_type + period_end + source` 去重

---

## 7. API 端点说明

### POST /api/v1/stocks/{market}/{code}/reports/discover

按指定报告类型和年份搜索。

**请求体:**
```json
{
  "report_type": "annual",
  "report_year": 2024,
  "company_name": "贵州茅台",
  "auto_insert": true
}
```

**响应:**
```json
{
  "candidates": [...],
  "inserted": [...],
  "skipped": [...],
  "errors": [],
  "partial": false,
  "sources_searched": ["cninfo", "sse", "szse"],
  "total_found": 1,
  "disclaimer": "..."
}
```

### POST /api/v1/stocks/{market}/{code}/reports/discover/latest

一键查找最新 4 种报告（annual/semi/q1/q3）。

**请求参数:** `?report_year=2024&company_name=贵州茅台`

### GET /api/v1/stocks/{market}/{code}/reports/{report_id}/pdf

安全 PDF 查看代理。

- 验证 report_id 存在于 DB
- 验证 report 属于请求的股票
- 验证 pdf_url 域名在白名单（9 个可信域）
- 302 Redirect 到 PDF URL

---

## 8. 前端 ReportDocumentsPanel 功能

### 新增功能

1. **年份选择器** — 下拉选择 report_year（默认上一年）
2. **「自动查找财报」按钮** — 调用 discover/latest API
3. **PDF 图标（📄）** — 每条有 pdf_url 的记录显示，点击打开
4. **来源 Badge** — CNINFO / SSE / SZSE / 手动
5. **置信度显示** — 百分比形式
6. **「查看」「下载」按钮** — 通过后端代理路由打开
7. **低置信度候选展示** — 需人工确认的候选显示在底部
8. **空状态提示** — 引导用户点击查找或手动上传

### PDF 打开方式

```
点击 PDF 图标 / 查看按钮
    ↓
window.open(`/api/v1/stocks/{market}/{code}/reports/{report_id}/pdf`, '_blank')
    ↓
后端验证 report_id → 302 Redirect → CNINFO/SSE/SZSE PDF URL
```

**不直接拼接外部 URL**，防止任意 open redirect。

---

## 9. 安全与合规边界

| 规则 | 实现 |
|---|---|
| 不高频爬取 | 每个来源每次请求前等待 1.5 秒 |
| 不绕过验证码/登录 | 只调用公开无鉴权 API |
| 不允许任意 redirect | PDF 路由验证域名白名单（9 个 CNINFO/SSE/SZSE 域） |
| 不暴露 local_path | API 响应不包含 local_path |
| 不编造 PDF | 只返回搜索结果，无 LLM 生成 URL |
| 不生成投资建议 | 本模块不调用 LLM |
| Rate limit | httpx timeout=10s，retry 最多 2 次，指数退避 |
| 失败不崩溃 | 所有 tool.search() 异常被捕获，返回空列表 |
| DB 不入库 | confidence < 0.75 的候选不自动入库 |

---

## 10. 已知限制

| 限制 | 说明 |
|---|---|
| 仅 A 股（CN 市场） | HK/US 市场暂不支持，返回 partial=true + reason |
| CNINFO API 稳定性 | 公开 API，结构可能变化；变化时返回 partial reason，不崩溃 |
| SSE/SZSE 响应格式 | 多字段名兼容已实现，但不保证覆盖所有变体 |
| PDF 仅发现 URL | 不自动下载，download_status 保持 "pending" |
| PDF 内容未解析 | parsed=false，AI source_reports 无 text_excerpt |
| 季报搜索可能误匹配 | q1/q3 共用同一 category，需靠 title 关键词过滤 |
| BaoStock 无报告索引 | BaoStock 不提供 PDF 链接，不在搜索范围 |

---

## 11. 测试结果

```
tests/fundamental/test_phase6d_report_discovery.py — 15/15 PASS
tests/fundamental/test_phase6b_free_mode_real_mapping.py — 17/17 PASS
Frontend build — ✓ clean, 2.45s
```

---

## 12. 下一阶段建议

| 阶段 | 内容 |
|---|---|
| Phase 6E | PDF 本地下载 + 文本提取（pdfminer/pymupdf） |
| Phase 6F | PDF → RAG 向量入库（利用现有 pgvector + financial_rag） |
| Phase 6G | AI Analysis Agent 引用已入库 PDF 章节（source_reports 增强） |
| Phase 6H | Review Agent 验证 source_reports report_id 真实存在 |
