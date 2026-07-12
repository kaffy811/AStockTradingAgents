# Phase 6T-J1 — Persistent RAG Repository Wiring 验收（2026-07-12）

## 结论

`RAG_INDEX_NOT_PERSISTENT` blocker 已消除：Company V2 RAG 索引现持久化于 PostgreSQL
（`company_v2_report_rag_documents` / `company_v2_report_rag_chunks`），独立进程只读 DB 检索 16/16 PASS。

## Schema 审计（修正了"无需 migration"的判断）

- 实际 DDL 落后于 ORM model（表由 `create_all` 创建、无 migration 治理）：缺
  `active_index / supersedes_rag_document_id / stale_reason / indexed_at / deleted_at / index_generation` 6 列，
  且 `report_id` 有 UNIQUE 索引（阻止多 generation 审计保留）。
- **新增 migration `i7j8k9l0m1n2`**：补 6 列、`report_id` 改普通索引、新增 `(report_id, index_generation)` 唯一约束。

## Repository

- `DatabaseCompanyV2ReportRagRepository`（backend=database, persistent=true）：
  私有 daemon-loop AsyncEngine（仅 asyncpg 可用）、NullPool + `statement_cache_size=0`（Supabase pgbouncer 兼容）、
  Core executemany 批量插入（batch size 可配 `COMPANY_V2_RAG_CHUNK_BATCH_SIZE` 默认 200）。
- 事务原子：pending generation → 批量 chunks → persisted count 校验 → 新代 active → 旧代 stale →单事务 COMMIT；
  失败全量 rollback，旧 active 保留（真实 DB 测试验证）。
- 幂等身份：(report_id, pdf_hash, parse_version, embedding_version)——相同身份复用 active generation，0 插入。
- 无 memory fallback：backend 非法或 DB 失败抛 `CompanyV2RagRepositoryError`（错误信息不含凭证）。
- 工厂 `company_v2_report_rag_repository_factory`；生产默认 database，测试经 conftest 显式注入 memory。

## 真实 Re-index（report_id 2-5）

- checkpoint 复核：ok=true 但 DB 无 active doc → `PERSISTENCE_MISSING_REINDEX_REQUIRED` 强制重索引（不删 checkpoint）。
- 过程记录（如实）：首次 DB 运行遇 pgbouncer prepared-statement 错误（已修）；ORM 逐行 INSERT 超时 180s
  （改 executemany 后解决）；3 只超时轮的事务在超时后原子完成；最终 `--resume` 幂等收敛 4/4 ok。

## DB 直接核验

| 指标 | 值 |
|---|---|
| active documents | 4（每 report 唯一） |
| chunks | **1217**（211/299/311/396） |
| orphan / invalid page / cross-report / empty / dup chunks | 全 0 |
| 缺 embedding chunks | 0 |
| 版本元数据 | company-v2-pages-v1 / company-v2-hash-keyword-v1（真实常量） |

## 独立进程验收（scripts/company_v2_rag_persistence_smoke.py）

新进程只读 DB：4/4 `retrieved_after_restart=true`，chunk 数全部匹配，检索 16/16 evidence found，
citation 页码有效，0 跨股票/跨报告泄漏，`repository_backend=database, persistent=true`。

## QA / Fusion 接线

index service / manager / retriever / comparison retriever+answer / fusion（经 index service）
全部为同一工厂单例（对象同一性验证）；`status()` 暴露 `repository_backend` + `persistent`。
本轮未运行 multistock fusion（依赖 smoke 仅验证接线）。

## 测试

- targeted：22/22 phase6tj1 测试 PASS（含真实 DB 的 rollback/批量/restart/独立进程）
- 测试数据隔离：report_id ≥ 990000 + cleanup，验收数据（2-5）核验无污染
- canonical full：见 final gate
