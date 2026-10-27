---
目前完成的工作汇总：

已完成

1. R3.3E migration 全链审计
- 确认 root `4b49004d01a6` 是空操作的 existing-schema baseline，不是空库 bootstrap。
- 识别八张仅由历史 schema/create-all 提供、没有显式创建 migration 的 legacy 表。
- 确认首次依赖 `analysis_reports` 的 revision 是 `3a2f8b4c1d9e`。

2. 隔离 PostgreSQL 验证
- 在全新 pgvector PostgreSQL 与标准 PostgreSQL 中分别执行完整 migration。
- 显式 legacy bootstrap 草案通过了原始缺表失败，但两种数据库均在已发布 pgvector migration `a2c5e8f1b4d7` 阻断。
- 全部测试容器和匿名卷已删除，未访问 production DB。

3. 安全收口
- 因完整 root→head 契约仍不成立，撤回未通过的 bootstrap 草案，没有保留或提交半修复。
- 生成 `backend/docs/artifacts/company_agents_data_r3_3e_empty_db_bootstrap.md`，记录直接证据与后续授权边界。
- 未修改 Dockerfile、main.py、embedding provider、依赖/lockfile、Agent、RAG 或 numeric validator。

---
下一步：你需要操作

第一步：Owner 单独授权处理已发布 revision `a2c5e8f1b4d7` 的 PostgreSQL transaction-safe fallback 或授权增加 pinned Python pgvector dependency。

第二步：在扩展授权后恢复显式 legacy bootstrap migration，并新增真实 PostgreSQL empty/existing-schema contract tests。

第三步：仅在 `alembic upgrade head`、重复升级、关键表/约束、candidate health 全部通过后创建独立 commit；继续保持 `HOLD_1_PERCENT`。
