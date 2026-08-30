---
目前完成的工作汇总：

已完成

1. Portable legacy bootstrap migration
- 新增 `r3e4f5g6h7i8` Alembic root，仅在缺失时创建升级到 head 所需的 8 张 legacy 表。
- 将既有 baseline `4b49004d01a6` 接到 bootstrap revision；已存在表与数据不删除、不覆盖，downgrade 不执行破坏性操作。

2. Standard PostgreSQL 与 pgvector 完整链验证
- 四个隔离场景全部完成 root/fixture → `q5r6s7t8u9v0`、repeat upgrade、SELECT 和 INSERT/SELECT。
- standard PostgreSQL 选择 TEXT 且无 HNSW；pgvector 选择 VECTOR(1536)/VECTOR(384) 并创建预期 HNSW；fixture sentinel 全部保留。

3. Migration 测试门禁
- bootstrap 9 passed、a2 6 passed、f4 6 passed、g5 6 passed。
- 合并 full migration contract suite：27 passed、0 failed、0 skipped，19.74s。

4. 审计交付物
- 生成 `backend/docs/artifacts/company_agents_data_r3_3i2_7_8_final_portable_migration_contract.md` 与 `.json`。
- 未访问或修改 production 数据库/容器；未 push、merge、deploy、production migration 或扩流。

---
下一步：你需要操作

第一步：在隔离分支审阅 bootstrap 独立 commit 与三个 vector compatibility ancestors 的文件边界。
第二步：由 release owner 决定是否将最小 migration commit 链纳入后续 release candidate；本阶段不要直接合并 production release。
第三步：继续保持流量 `HOLD_1_PERCENT`，任何部署与扩流需另行审批。
