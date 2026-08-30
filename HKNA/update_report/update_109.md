---
目前完成的工作汇总：

已完成

1. Migration-wide vector capability inventory
- 全量搜索 Alembic graph，确认 e8 为安全 TEXT placeholder、a2/f4 已修复、g5 是唯一剩余 Python importability 风险。
- 未发现 g5 之后的其他 vector schema migration。

2. g5 database capability 与数据契约修复
- g5 改为使用 `pg_extension`，standard PostgreSQL 保留 TEXT column 与已有 TEXT embedding。
- pgvector 保持 1536→384 的已发布维度重置语义，保留业务行并重建 HNSW。
- Upgrade/downgrade 均不再依赖 Python pgvector 包。

3. 四场景验证与范围控制
- 四种隔离数据库路径、SELECT、INSERT/SELECT、数据断言与 repeat upgrade 全部通过。
- 测试为 6 collected / 6 passed / 0 failed / 0 skipped / 5.51s。
- 未修改 bootstrap、a2、f4、Agent、Docker 或 dependency 文件；未 push、merge、部署或扩流。

---
下一步：你需要操作

第一步：审阅 `r33i-g5-vector-capability` 的 g5 白名单 diff 与独立 commit。

第二步：将 a2、f4、g5 三个独立 commits 与 bootstrap overlay 组合，重新执行四场景完整 root → current head。

第三步：只有 full chain 与所有 migration suites 全绿后，再创建 bootstrap 独立 commit。
