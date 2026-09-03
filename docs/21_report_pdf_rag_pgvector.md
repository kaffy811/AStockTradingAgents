# Phase 6F — PDF → pgvector RAG 向量入库 + 财报片段检索

**日期:** 2026-07-06  
**状态:** 已实现 ✓  
**版本:** Phase 6F

---

## 1. 功能概述

Phase 6F 在 Phase 6E（PDF 下载/解析）的基础上，实现了完整的 RAG（Retrieval-Augmented Generation）闭环：

```
PDF 文本（text_excerpt 或本地全文）
    ↓ ReportChunkService
切块（800-1200 字，150 字 overlap）
    ↓ ReportEmbeddingService  
embedding_service（mock=0成本 / openai / deepseek）
    ↓ pgvector vector(384)
report_chunks 表
    ↓ ReportRagService
语义搜索（cosine similarity → keyword fallback）
    ↓ AI Data Agent
report_rag_context（6-10 chunks × 1500 字）
    ↓ Analysis Agent
source_chunks 引用标注
    ↓ AiAnalysisCard
「引用财报片段」区块（展开/收起）
```

---

## 2. 数据库设计

### 2.1 report_chunks 表（migration f4a5b6c7d8e9）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | Integer PK | 自增主键 |
| report_id | Integer FK | 关联 report_documents.id（CASCADE DELETE） |
| ts_code | String(20) | Tushare 股票代码，如 600519.SH |
| symbol | String(20) | 纯股票代码，如 600519 |
| market | String(10) | CN / HK / US |
| report_type | String(20) | annual / semi / q1 / q3 |
| report_year | Integer | 报告年份 |
| period | String(10) | 报告期 YYYY-MM-DD |
| chunk_index | Integer | chunk 在文档内的序号 |
| section_title | String(200) | 从 chunk 开头检测的章节标题 |
| page_start | Integer | 页码起始（预留，当前 null） |
| page_end | Integer | 页码结束（预留，当前 null） |
| content | Text | chunk 正文（800-1200 字） |
| content_hash | String(64) | SHA-256，全局唯一，用于去重 |
| embedding | vector(384) | pgvector 向量 |
| embedding_model | String(100) | 模型名（如 report-rag-mock） |
| token_count | Integer | 近似 token 数（CJK: 1字≈1token） |
| embed_error | Text | embedding 失败信息 |
| created_at | DateTime | 创建时间（UTC） |
| updated_at | DateTime | 更新时间（UTC） |

**索引：**
- `ix_report_chunks_report_id`（BTree）
- `ix_report_chunks_ts_code`（BTree）
- `ix_report_chunks_content_hash`（BTree, UNIQUE）
- `ix_report_chunks_embedding`（HNSW, m=16, ef_construction=64，cosine）

### 2.2 report_documents 新增字段

| 字段 | 类型 | 说明 |
|------|------|------|
| rag_status | String(20) | pending / chunked / embedded / partial / failed |
| chunk_count | Integer | chunk 数量 |
| rag_error | Text | RAG 处理错误信息 |

---

## 3. Chunking 策略

### 参数
- **目标 chunk 大小：** 1000 中文字符（_CHUNK_SIZE）
- **相邻 chunk 重叠：** 150 字符（_CHUNK_OVERLAP）
- **最小 chunk 大小：** 100 字符（_MIN_CHUNK_SIZE）

### 切分逻辑
1. 优先按双换行（段落边界）切分
2. 段落超过 chunk_size 时，强制按字符切分
3. 相邻 chunk 保留尾部 150 字重叠，保证语义连贯
4. section_title 检测：chunk 头部 5 行内的 `### 标题` 或中文章节格式

### 去重
- 每个 chunk 计算 `SHA-256(content)`
- content_hash 全局唯一（跨 report_id）
- 重复 hash 的 chunk 跳过，不插入

### 文本来源优先级
1. `local_path` 本地 PDF（pdfminer.six 全文提取，无截断）
2. `text_excerpt`（最多 8000 字符，Phase 6E 截取）

---

## 4. Embedding Provider

**设计目标：** 0 成本可用，接口可切换。

| Provider | 成本 | 说明 |
|----------|------|------|
| `mock`（默认） | $0 | SHA-256 seeded PRNG，确定性，384 维，无外部调用（Phase 6G-1） |
| `local` | $0 | sentence-transformers 本地模型，384 维原生支持（Phase 6G-1） |
| `openai` | 按量 | text-embedding-3-small，1536 维，需 schema migration + OPENAI_API_KEY |
| `deepseek` | 占位 | 暂时 fallback 到 mock |

**配置（.env）：**
```env
EMBEDDING_PROVIDER=mock       # mock / openai / deepseek
EMBEDDING_MODEL=              # 覆盖默认模型名
ENABLE_REPORT_RAG=true        # 开启 RAG 功能
```

**故障保护：**
- embedding 失败时写 `embed_error`，不阻塞 chunk 入库
- `rag_status=partial`：部分 chunk 有 embedding，keyword 回退仍可用
- 无 embedding 时自动回退到关键词检索

---

## 5. API 端点

### POST /api/v1/stocks/{market}/{code}/reports/{report_id}/chunk

将 PDF 文本切分为 chunks 并入库。幂等：重复调用先删旧 chunks 再重建。

**响应：**
```json
{"status": "chunked", "report_id": 1, "chunk_count": 12, "reason": "ok"}
```

### POST /api/v1/stocks/{market}/{code}/reports/{report_id}/embed

为已切分 chunks 生成 embedding 向量。

**响应：**
```json
{"status": "embedded", "report_id": 1, "embedded": 12, "failed": 0, "reason": "ok"}
```

### POST /api/v1/stocks/{market}/{code}/reports/{report_id}/rag/build

一键执行 chunk + embed 两步。

**响应：**
```json
{
  "status": "embedded",
  "report_id": 1,
  "chunk_result": {"status": "chunked", "chunk_count": 12},
  "embed_result": {"status": "embedded", "embedded": 12, "failed": 0},
  "reason": "ok"
}
```

### POST /api/v1/stocks/{market}/{code}/reports/rag/query

语义检索该股票年报片段。

**请求：**
```json
{
  "query": "公司现金流质量如何？",
  "report_types": ["annual"],
  "years": [2024],
  "top_k": 6
}
```

**响应：**
```json
{
  "chunks": [
    {
      "chunk_id": 42,
      "report_id": 1,
      "report_type": "annual",
      "report_year": 2024,
      "period": "2024-12-31",
      "section_title": "现金流量分析",
      "content": "经营活动现金流净额为…（最多 1500 字）",
      "has_embedding": true,
      "pdf_url": "/api/v1/stocks/CN/600519/reports/1/pdf"
    }
  ],
  "partial": false,
  "errors": [],
  "search_mode": "vector",
  "total": 6,
  "disclaimer": "财报片段来自公开披露文件，仅供参考，不构成投资建议。"
}
```

---

## 6. AI source_chunks 集成

### FundamentalAnalystAgent.analyze()
`source_reports` 参数（Phase 6E）已支持注入年报摘录。

下一步（Phase 6G）可进一步注入 RAG 检索结果作为 `report_rag_context`：

```python
agent.analyze(
    market="CN",
    symbol="600519",
    output_language="zh-CN",
    source_reports=parsed_reports,        # Phase 6E: text_excerpt
    # source_chunks=rag_results,          # Phase 6G: chunk-level RAG（待实现）
)
```

### Analysis Agent 输出 source_chunks（待实现）

```json
{
  "source_chunks": [
    {
      "chunk_id": 42,
      "report_id": 1,
      "title": "贵州茅台2024年年度报告",
      "section_title": "现金流量分析",
      "score": 0.82,
      "pdf_url": "/api/v1/stocks/CN/600519/reports/1/pdf"
    }
  ]
}
```

---

## 7. 前端展示

### ReportDocumentsPanel 新增

| 功能 | 触发条件 | 说明 |
|------|----------|------|
| RAG 状态 badge | 有 rag_status | 已向量化/已切分/部分/失败 |
| chunk_count 显示 | chunk_count > 0 | "12 片" |
| 「生成索引」按钮 | parsed=true 且 rag_status≠embedded | 触发 rag/build |

### AiAnalysisCard 新增

- `sourceChunks` prop（Array）
- 「🔍 引用财报片段」区块
- 每条 chunk：报告类型 badge + 章节标题 + 报告期 + PDF 链接 + 展开/收起按钮

---

## 8. 0 成本模式边界

| 配置 | 成本 |
|------|------|
| EMBEDDING_PROVIDER=mock | $0（默认） |
| EMBEDDING_PROVIDER=openai | 按量，约 $0.02/1M tokens |
| DATA_MODE=free | $0（BaoStock+AkShare） |

mock 模式下：
- embedding 为确定性 hash 向量，不保证语义准确
- keyword fallback 仍可用
- RAG 检索可运行，结果质量取决于关键词匹配

---

## 9. 安全合规说明

| 约束 | 实现 |
|------|------|
| 不跨股票泄露 | RAG query 强制过滤 ts_code |
| 不暴露 local_path | API 响应不含 local_path |
| content 截断 | 每个 chunk 最多 1500 字回传给前端 |
| 不生成投资建议 | Analysis Agent 系统提示禁令保留 |
| 不引用虚构 chunk | Review Agent 校验 chunk_id 存在性（Phase 6H） |
| 不打印全文日志 | logging 只记录 report_id + chunk_count |

---

## 10. 测试结果

```
tests/fundamental/test_phase6f_report_rag.py — 13/13 PASS
tests/fundamental/ (全量) — 394/394 PASS
Frontend build — ✓ clean, 2.46s
Migration f4a5b6c7d8e9 — ✓ applied
```

---

## 11. 剩余风险

| 风险 | 说明 |
|------|------|
| mock embedding 语义准确性 | hash-based 向量无语义，关键词回退质量有限 |
| 扫描版 PDF 无文本层 | chunk 为空，RAG 不可用 |
| HNSW 建索引需时间 | 首次向量化较慢，适合异步/后台任务 |
| pdfminer 双栏排版乱序 | chunk 内容可能不连贯 |
| rag_status 无 webhook | 前端需手动点击，不自动感知后台完成 |

---

## 12. 下一阶段建议

| 阶段 | 内容 |
|------|------|
| Phase 6G | source_chunks 注入 Analysis Agent 提示词 |
| Phase 6H | Review Agent 校验 chunk_id 存在于输入 source_chunks |
| Phase 6I | RAG 后台任务化（Celery/asyncio Queue），不阻塞 HTTP |
| Phase 6J | Chat Copilot 支持「查年报」技能，调用 rag/query |
