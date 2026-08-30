---
目前完成的工作汇总：

已完成

1. `a2c5e8f1b4d7` transaction-safe vector fallback
- 使用 `pg_extension` 与 `pg_available_extensions` 判断数据库真实能力。
- extension 与 HNSW DDL 使用 nested transaction/savepoint，失败后 TEXT fallback 仍可继续。
- capability 不再依赖 Python pgvector 包是否安装。

2. 四种隔离数据库兼容测试
- Standard PostgreSQL 无 extension：TEXT fallback 通过。
- extension 可用但用户无权限：安全恢复并使用 TEXT。
- pgvector 已启用与可创建两条路径：VECTOR 与 HNSW index 均通过。
- 四条路径的 SELECT、INSERT/SELECT 与 repeat upgrade 均通过。

3. 范围与发布门禁
- 最终测试为 6 collected / 6 passed / 0 failed / 0 skipped / 5.08s。
- 本分支未包含 bootstrap、Agent、Docker、dependency、embedding provider 或 lockfile 改动。
- 未 push、merge、部署、执行 production migration 或扩流。

---
下一步：你需要操作

第一步：审阅 `r33i-vector-fallback` 的 staged 白名单与独立 commit。

第二步：在后续集成阶段把该 commit 与独立 legacy bootstrap commit 组合，在 standard PostgreSQL 和 pgvector PostgreSQL 上运行 empty DB → head 与 repeat upgrade。

第三步：保持 production 不变，等待完整 release candidate migration contract 通过后再决定集成。
