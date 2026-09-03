# Phase 6T-J Stage 2 Index 验收（2026-07-11）

## 结论：index 步执行成功（进程内 4/4），但**永久性 FAIL** → index_gate_passed=false

| symbol | report_id | rag_doc_id | status | pages | chunks | embedded | generation |
|---|---|---|---|---|---|---|---|
| 600519 | 2 | 1 | indexed | 143 | 211 | 211 | 1 |
| 300750 | 3 | 2 | indexed | 232 | 299 | 299 | 1 |
| 000725 | 4 | 3 | indexed | 227 | 311 | 311 | 1 |
| 000001 | 5 | 4 | indexed | 288 | 396 | 396 | 1 |

## Chunk 校验（单进程内）
```json
{"invalid_page_chunks": 0, "empty_chunks": 0, "duplicate_chunks": 0, "cross_symbol_chunks": 0, "cross_report_chunks": 0}
```

## 检索 smoke：16/16 evidence found，0 隔离违规，引用页码全部有效

## 幂等：4/4 duplicate_index_avoided；stale：hash 变化→新 generation、旧代 stale、审计历史保留

## 永久性检查（决定性）
- 新进程读取：4 只全部 pending / chunk_count=0
- DB `company_v2_report_rag_documents` = 0 行，`company_v2_report_rag_chunks` = 0 行
- 根因：`CompanyV2ReportRagRepository` 仅内存 dict；DB 表已建（与 dataclass 1:1）但无任何写入代码

## Blocking Issue
- `RAG_INDEX_NOT_PERSISTENT`

## 版本元数据（真实常量，非伪造）
- parser_version=company-v2-pages-v1 / embedding=company-v2-hash-keyword-v1（deterministic hash-keyword，非 LLM embedding）

## 下一步选项（需授权）
- 将 repository 接线到既有 `company_v2_report_rag_documents/chunks` 表（schema 已 1:1 匹配）后重跑 index