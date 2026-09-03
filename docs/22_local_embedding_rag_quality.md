# Phase 6G / 6G-1 — 本地 0 成本 Embedding Provider + RAG 检索质量评估

**日期:** 2026-07-06  
**状态:** 已实现 ✓（Phase 6G-1 维度定版完成）  
**版本:** Phase 6G-1

---

## 1. Mock vs Local Embedding

| 特性 | mock（默认） | local（sentence-transformers） | disabled |
|------|-------------|-------------------------------|---------|
| 成本 | $0 | $0（本地 CPU/GPU） | $0 |
| 语义理解 | ✗（hash向量） | ✓ | ✗ |
| 外部依赖 | 无 | sentence-transformers | 无 |
| CI/测试 | ✓（确定性） | ✗（需下载模型） | ✓ |
| 检索质量 | keyword fallback水平 | 语义相关 | keyword fallback only |
| 可用性 | 始终可用 | 需安装+下载模型 | 始终可用 |

**默认：** `REPORT_EMBEDDING_PROVIDER=mock`（CI安全，0成本，链路验证用）

---

## 2. EmbeddingProvider 架构

```
BaseReportEmbeddingProvider (ABC)
├── MockReportEmbeddingProvider
│   └── SHA-256 seeded LCG，L2 normalized，确定性，384维（Phase 6G-1 更新）
├── LocalSentenceTransformerProvider
│   ├── 懒加载 sentence-transformers 模型
│   ├── run_in_executor 避免阻塞 event loop
│   ├── 维度不匹配时 → 标记 unavailable + 明确错误原因（Phase 6G-1）
│   │   （已移除 silent pad/truncate，必须使用维度匹配的模型）
│   └── 初始化失败 graceful fallback 到 mock
└── DisabledReportEmbeddingProvider
    └── is_available()=False，embed_texts() raises，keyword fallback only
```

**Phase 6G-1 关键变更：**
- `REPORT_EMBEDDING_DIM` 默认值：`1536` → **`384`**
- `MockReportEmbeddingProvider` 默认 dim：`1536` → **`384`**
- `LocalSentenceTransformerProvider._adjust_dim()` 已**删除**
- 维度不匹配行为：silent pad/truncate → **RuntimeError + 明确原因**
- pgvector schema：`vector(1536)` → **`vector(384)`**（migration g5h6i7j8k9l0）

**工厂函数：** `get_report_embedding_provider()` — 从 settings 读取配置，失败时返回 mock

---

## 3. 推荐本地模型

### 中文场景

| 模型 | 维度 | 大小 | 说明 |
|------|------|------|------|
| `BAAI/bge-small-zh-v1.5` | 384 | ~95MB | 推荐首选：小、快、中文优秀 |
| `BAAI/bge-base-zh-v1.5`  | 768 | ~380MB | 平衡版 |
| `BAAI/bge-large-zh-v1.5` | 1024 | ~1.3GB | 高质量，资源多 |

### 中英混合（财报中英夹杂）

| 模型 | 维度 | 大小 | 说明 |
|------|------|------|------|
| `intfloat/multilingual-e5-small` | 384 | ~120MB | 推荐：多语言，小巧 |
| `intfloat/multilingual-e5-base`  | 768 | ~560MB | 多语言平衡版 |

**具体模型不硬编码到业务逻辑** — 由 `REPORT_EMBEDDING_MODEL` 配置。

---

## 4. pgvector 维度注意事项

**当前 schema（Phase 6G-1）：** `report_chunks.embedding vector(384)`

**⚠️ Phase 6G-1 起已移除 silent pad/truncate。** 模型维度必须与 `REPORT_EMBEDDING_DIM` 完全匹配，否则 provider 标记为 unavailable 并返回明确错误信息。

### 使用不同维度模型的方案

#### 默认方案（推荐）：使用 384 维模型，无需 migration

schema 已为 `vector(384)`，直接使用：
- `BAAI/bge-small-zh-v1.5`（384-dim，中文）
- `intfloat/multilingual-e5-small`（384-dim，多语言）

#### 其他维度方案：需要 schema migration

如需使用 768/1024/1536 维模型，必须先运行对应维度的 schema migration：

#### 方案：迁移 vector(384) → vector(768)（768维模型）

创建并运行 migration（DROP + ADD，PostgreSQL 不支持直接 ALTER vector dim）：

```sql
DROP INDEX IF EXISTS ix_report_chunks_embedding;
-- DROP + ADD embedding column
ALTER TABLE report_chunks DROP COLUMN embedding;
ALTER TABLE report_chunks ADD COLUMN embedding vector(768);
-- 重建 HNSW 索引
CREATE INDEX ix_report_chunks_embedding
  ON report_chunks USING hnsw (embedding vector_cosine_ops)
  WITH (m = 16, ef_construction = 64);
-- 重置 rag_status 以触发重新 embed
UPDATE report_documents SET rag_status = 'chunked' WHERE rag_status = 'embedded';
```

同时设置：
```env
REPORT_EMBEDDING_DIM=768
REPORT_EMBEDDING_MODEL=BAAI/bge-base-zh-v1.5
REPORT_EMBEDDING_PROVIDER=local
```

**注意：** 维度变更后，所有旧 embedding 作废（已被 DROP），需对所有文档重新运行 rag/build。

---

## 5. 配置说明

```env
# Report RAG embedding（与 financial_rag 的 EMBEDDING_PROVIDER 独立）
REPORT_EMBEDDING_PROVIDER=mock   # mock | local | disabled
REPORT_EMBEDDING_MODEL=BAAI/bge-small-zh-v1.5   # local provider 时必填
REPORT_EMBEDDING_DIM=384         # 必须与 vector(N) schema 匹配（默认 384，Phase 6G-1）

# RAG 功能开关
ENABLE_REPORT_RAG=true
```

### 安装 local provider 依赖

```bash
cd backend
uv pip install sentence-transformers
# 首次使用时自动下载模型（约100MB-1.3GB）
```

---

## 6. RAG 检索质量评估

### 评估脚本

```bash
cd backend
python scripts/evaluate_report_rag_quality.py --symbols 600519,000725,300750,601318 --top-k 6
```

### 前置条件
1. 已完成 PDF 下载：`POST .../reports/{id}/download`
2. 已完成 PDF 解析：`POST .../reports/{id}/parse`
3. 已生成 RAG 索引：`POST .../reports/{id}/rag/build`

### 内置 Query Set（6条）

| ID | 查询 | 预期关键词 |
|----|------|-----------|
| q1_business | 公司的主营业务和收入来源是什么？ | 主营、产品、收入、业务 |
| q2_profitability | 公司的盈利能力变化如何？ | 毛利率、净利率、利润、盈利 |
| q3_cashflow | 公司的经营活动现金流情况如何？ | 经营活动现金流、现金流量、收现 |
| q4_risk | 公司面临哪些主要风险？ | 风险、市场风险、经营风险 |
| q5_strategy | 公司未来发展战略或经营计划是什么？ | 战略、计划、展望、发展 |
| q6_dividend | 公司分红政策或利润分配情况如何？ | 分红、利润分配、股利、派息 |

### 结果 CSV 字段说明

| 字段 | 说明 |
|------|------|
| symbol | 股票代码 |
| query_id | 查询 ID |
| query | 查询文本 |
| provider | embedding provider（mock/local/disabled） |
| top_k | 检索数量 |
| retrieved_count | 实际返回数量（0=无chunk） |
| top_score | 最高相关度分数 |
| top_section_title | 最相关 chunk 的章节标题 |
| contains_expected_keywords | 预期关键词是否出现 |
| matched_keywords | 实际匹配的关键词 |
| fallback_used | 是否使用了 keyword fallback |
| search_mode | vector / keyword / error |
| elapsed_ms | 检索耗时（毫秒） |
| notes | 备注（空=正常） |

输出目录：`docs/artifacts/`

---

## 7. Hybrid Retrieval 设计

`ReportRagService` 支持混合评分：

```
final_score = vector_score + keyword_bonus

vector_score：pgvector cosine similarity（~0.7-0.95 范围）
keyword_bonus：query 词在 content 中出现次数 × 0.03（最大 0.15）
```

**Vector search path：** final_score ≈ 0.85 + keyword_bonus  
**Keyword fallback path：** final_score = 0.30 + keyword_bonus

结果包含 `score_detail`：
```json
{
  "vector_score": 0.85,
  "keyword_bonus": 0.09
}
```

---

## 8. 已知限制

| 限制 | 说明 |
|------|------|
| mock 向量无语义 | hash-based，仅验证链路，不保证检索质量 |
| 零填充影响余弦相似度 | 384→1536 零填充后向量范数改变，相似度计算偏差 |
| sentence-transformers 首次加载慢 | 模型 load 约 3-15s，建议进程启动时预热 |
| 扫描版 PDF 无 chunks | text_excerpt 为空时无法切块 |
| pgvector score 近似 | 当前实现返回固定约 0.85，非真实 cosine score |
| 无语义评分基线 | sanity check 靠关键词规则，非 NDCG/MRR 等标准指标 |

---

## 9. 0 成本部署建议

**开发/CI：** `REPORT_EMBEDDING_PROVIDER=mock`（默认，无需配置）

**Staging（验证语义质量）：**
```env
REPORT_EMBEDDING_PROVIDER=local
REPORT_EMBEDDING_MODEL=BAAI/bge-small-zh-v1.5
REPORT_EMBEDDING_DIM=384
# 同时运行迁移将 vector(1536) → vector(384)
```

**生产（无 GPU）：**
- bge-small-zh: ~10ms/chunk（CPU），16 chunks/batch → 约 160ms/report
- 年报约 50-100 chunks → 建索引约 1-2s（CPU）

**生产（有 GPU）：**
- 批量处理可提速 10-50x，实时性更好

---

## 10. 测试结果

```
tests/fundamental/test_phase6g_local_embedding_and_quality.py — 13/13 PASS（tests 7/8 更新反映 6G-1 行为）
tests/fundamental/test_phase6g1_embedding_dim_migration.py — 9/9 PASS
tests/fundamental/ (全量) — 416/416 PASS
```

---

## 11. 下一阶段建议

| 阶段 | 内容 |
|------|------|
| Phase 6H | source_chunks 注入 FundamentalAnalystAgent 提示词 |
| Phase 6I | Review Agent 校验 chunk_id 存在性，防虚构引用 |
| Phase 6J | pgvector score 真实返回（使用 `<=> AS score` SQL） |
| Phase 6K | 异步后台建索引（避免 HTTP 超时） |
| Phase 6L | Chat Copilot「查年报」技能，调用 rag/query 端点 |
