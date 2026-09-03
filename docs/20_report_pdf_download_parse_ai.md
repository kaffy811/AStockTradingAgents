# Phase 6E — PDF 下载/解析 + AI source_reports 闭环

**日期:** 2026-07-06  
**状态:** 已实现 ✓  
**版本:** Phase 6E

---

## 1. 功能概述

Phase 6E 在 Phase 6D（报告发现）的基础上，实现了完整的 PDF 下载→文本提取→AI 引用闭环：

```
ReportDocumentsPanel「下载」按钮
    ↓
POST /api/v1/stocks/CN/{code}/reports/{id}/download
    ↓
ReportPdfDownloadService
  ├── 域名白名单校验（9个可信域）
  ├── httpx 异步下载
  ├── Content-Type 检查（pdf/octet-stream）
  ├── 50MB 上限
  ├── SHA-256 去重
  └── 写入 local_path / file_size / download_status
    ↓
ReportDocumentsPanel「解析」按钮（download_status=downloaded 才可用）
    ↓
POST /api/v1/stocks/CN/{code}/reports/{id}/parse
    ↓
ReportTextExtractService
  ├── pdfminer.six（首选）
  ├── pypdf（备选 fallback）
  ├── 清理多余空白
  ├── 截取前 8000 字符
  └── 写入 text_excerpt / parse_status / parsed=true
    ↓
FundamentalAnalystAgent.analyze(source_reports=[...])
    ↓
LLM 提示词注入年报摘录（最多 4 份，每份 3000 字符）
    ↓
AI 报告「引用财报」区块展示
```

---

## 2. 新增文件清单

### Backend

| 文件 | 说明 |
|------|------|
| `app/services/report_pdf_download_service.py` | PDF 下载服务（域名校验、大小限制、SHA256） |
| `app/services/report_text_extract_service.py` | 文本提取服务（pdfminer + pypdf fallback） |
| `alembic/versions/2026_07_06_0003-e3f4a5b6c7d8_add_pdf_download_parse_fields.py` | DB migration |
| `scripts/validate_report_discovery_live.py` | 真实公网发现率验证脚本 |
| `tests/fundamental/test_phase6e_report_pdf_download_parse_ai.py` | 13 测试 |

### Frontend

| 文件 | 说明 |
|------|------|
| `components/fundamentals/ReportDocumentsPanel.vue` | 新增下载/解析/查看摘录按钮 + 文本摘录弹窗 |
| `components/fundamentals/AiAnalysisCard.vue` | 新增「引用财报」区块 + sourceReports prop |

### Docs

| 文件 | 说明 |
|------|------|
| `docs/19_report_discovery_live_validation.md` | 验证脚本说明 |
| `docs/20_report_pdf_download_parse_ai.md` | 本文档 |

---

## 3. API 端点

### POST /api/v1/stocks/{market}/{code}/reports/{report_id}/download

触发服务端下载 PDF 到本地缓存。

**响应示例（成功）：**
```json
{
  "status": "downloaded",
  "report_id": 42,
  "local_path": "/tmp/report_pdfs/report_42_abc123def456.pdf",
  "file_size": 2457600,
  "sha256": "abc123...",
  "reason": "ok"
}
```

**响应示例（已存在）：**
```json
{"status": "exists", "report_id": 42, "reason": "already downloaded"}
```

**响应示例（失败）：**
```json
{"status": "failed", "report_id": 42, "reason": "file too large: 55000000 bytes (limit 52428800)"}
```

### POST /api/v1/stocks/{market}/{code}/reports/{report_id}/parse

从已下载 PDF 提取文本摘录（5000-8000 字符）。

**前置条件：** `download_status=downloaded`

**响应示例：**
```json
{"status": "parsed", "report_id": 42, "chars": 7823, "reason": "ok"}
```

### GET /api/v1/stocks/{market}/{code}/reports/{report_id}/text

获取文本摘录全文。

**响应示例：**
```json
{
  "found": true,
  "report_id": 42,
  "ts_code": "600519.SH",
  "title": "贵州茅台2024年年度报告",
  "report_type": "annual",
  "period_end": "2024-12-31",
  "parse_status": "parsed",
  "chars": 7823,
  "text": "贵州茅台酒股份有限公司\n2024年年度报告\n..."
}
```

---

## 4. 数据模型新增字段（migration e3f4a5b6c7d8）

| 字段 | 类型 | 说明 |
|------|------|------|
| `file_size` | Integer | 文件大小（字节） |
| `parse_status` | String(20) | pending/parsed/failed |
| `download_error` | Text | 下载错误信息 |
| `parse_error` | Text | 解析错误信息 |

---

## 5. FundamentalAnalystAgent.analyze() 签名变更

```python
agent.analyze(
    market:          str,
    symbol:          str,
    output_language: str = "zh-CN",
    source_reports:  list[dict] | None = None,   # NEW in Phase 6E
) -> str
```

**source_reports 结构：**
```python
[{
    "title":       "贵州茅台2024年年度报告",
    "report_type": "annual",
    "period_end":  "2024-12-31",
    "text_excerpt": "正文摘录前 3000 字...",
}]
```

**LLM 注入规则：**
- 最多注入 4 份报告
- 每份截取 3000 字符（共 ~12000 字符加入提示词）
- 明确禁止 LLM 编造引用、写"第X页"、写"全部财报完整覆盖"
- 引用格式：`（来源：annual 2024-12-31）`

---

## 6. 前端 ReportDocumentsPanel 新增功能

| 功能 | 触发条件 | API |
|------|----------|-----|
| 「下载」按钮 | 有 pdf_url 且未下载 | POST .../download |
| 「解析」按钮 | download_status=downloaded 且未解析 | POST .../parse |
| 「查看摘录」按钮 | parsed=true | GET .../text |
| 文本摘录弹窗 | 点击「查看摘录」 | 展示 text_excerpt |
| 状态显示 | 所有行 | 待下载/已下载/待解析/已解析/失败 |

---

## 7. AiAnalysisCard「引用财报」区块

新增 `sourceReports` prop（Array），当不为空时在 AI 分析卡片底部展示：

```
📄 引用财报
[年报] 贵州茅台2024年年度报告  2024-12-31  [PDF]
[半年报] 贵州茅台2024年半年报  2024-06-30  [PDF]
```

---

## 8. 安全约束

| 约束 | 实现 |
|------|------|
| 域名白名单 | 同 Phase 6D（9个 cninfo/sse/szse 域） |
| 文件大小上限 | 50MB，超限 → download_error + failed |
| Content-Type 检查 | 仅接受 application/pdf / octet-stream，否则 failed |
| SHA-256 去重 | 同一文件不重复存储 |
| 本地路径不暴露 | GET /text 响应不含 local_path |
| LLM 引用禁令 | 提示词注入 3 条明确禁令防幻觉 |
| pdfminer 异常隔离 | 全部 try/except 捕获，写 parse_error 不抛出 |

---

## 9. 已知限制

| 限制 | 说明 |
|------|------|
| PDF 内容不保证可提取 | 扫描版 PDF 无文本层，text_excerpt 为空 |
| 大型年报下载较慢 | 典型 A 股年报 3-8MB，30s timeout |
| pdfminer 对双栏排版 | 可能乱序，但摘录仍有参考价值 |
| REPORT_PDF_DIR 需可写 | 默认 /tmp/report_pdfs，生产需配置持久路径 |
| source_reports 不自动加载 | 调用 agent.analyze() 时需手动传入已解析文档 |

---

## 10. 测试结果

```
tests/fundamental/test_phase6e_report_pdf_download_parse_ai.py — 13/13 PASS
tests/fundamental/ (全量) — 381/381 PASS
Frontend build — ✓ clean, 2.59s
Migration e3f4a5b6c7d8 — ✓ applied
```

---

## 11. 下一阶段建议

| 阶段 | 内容 |
|------|------|
| Phase 6F | PDF → pgvector 向量入库（利用现有 financial_rag 表） |
| Phase 6G | Chat Copilot 直接引用已入库 PDF 章节（source_reports RAG） |
| Phase 6H | Review Agent 验证 source_reports report_id 真实存在 |
| Phase 6I | REPORT_PDF_DIR 配置持久化 + 定期刷新（cron） |
