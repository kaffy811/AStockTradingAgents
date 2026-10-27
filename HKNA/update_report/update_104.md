---
目前完成的工作汇总：

已完成

1. Portable legacy schema bootstrap 隔离实现
- 在 `r33i-migration-bootstrap` 隔离 worktree 中新增显式 legacy root revision，并将原 no-op baseline 接到该 root。
- 覆盖升级至 head 所需的 8 张 legacy 表；不写测试财务数据，不覆盖或删除既有表。
- downgrade 保留 legacy 表和用户数据。

2. Migration contract tests
- 新增 bootstrap graph、legacy table、约束、数据安全与真实 PostgreSQL migration tests。
- pgvector PostgreSQL 的 empty → head、repeat upgrade、既有 schema 数据保留均通过。
- standard PostgreSQL 在既有 `a2c5e8f1b4d7` vector revision 因 transaction-aborted 失败；本阶段未越界修改 vector migration。

3. 发布门禁结论
- 测试结果为 9 collected / 8 passed / 1 failed / 0 skipped / 3.51s。
- 因 standard PostgreSQL 路径未通过，没有创建 commit，也没有 push、merge、部署或扩流。

---
下一步：你需要操作

第一步：由 owner 授权独立的 vector migration portability 修复范围，不要与 legacy bootstrap 或 Agent 可信度 commit 混合。

第二步：修复后在隔离 standard PostgreSQL 与 pgvector PostgreSQL 上分别运行：empty DB → head、release baseline → head、repeat upgrade。

第三步：所有 migration contract tests 全绿后，再审阅并提交 `r33i-migration-bootstrap` 的最小白名单文件。
