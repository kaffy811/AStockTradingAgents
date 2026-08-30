---
目前完成的工作汇总：

已完成

1. f4 database vector capability 修复
- `f4a5b6c7d8e9` 改为查询 `pg_extension`，不再依据 Python pgvector 包能否导入选择 schema。
- Extension 已启用时创建 VECTOR(1536) 与既有 HNSW index；未启用时创建 TEXT 且不建 vector index。

2. 四种隔离数据库验证
- Standard、无权限/未启用、已启用、可用但未启用四条路径全部通过。
- SELECT、INSERT/SELECT 与 repeat upgrade 均成功，连接未进入 aborted 状态。
- 最终测试为 6 collected / 6 passed / 0 failed / 0 skipped / 5.36s。

3. 范围控制
- 本分支以 `4d366ce` 为父提交，没有修改 a2 或 legacy bootstrap。
- 未修改 Agent、Docker、dependency、lockfile、main 或 embedding provider。
- 未 push、merge、部署、执行 production migration 或扩流。

---
下一步：你需要操作

第一步：审阅 `r33i-vector-schema-capability` 的白名单 diff 与独立 commit。

第二步：后续组合 legacy bootstrap、`4d366ce` 和本 commit，重新执行 standard/pgvector empty DB → head。

第三步：如下一首次失败出现在后续维度迁移，保持相同的 database-capability 独立修复边界。
