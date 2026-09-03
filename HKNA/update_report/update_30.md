---
目前完成的工作汇总：

已完成

1. `backend/app/services/company_v2_financial_fusion_job_service.py`
- 将 job admission 从先查再插改成 `INSERT ... ON CONFLICT DO NOTHING RETURNING` 路径。
- 为 active job fingerprint 增加了 PostgreSQL 部分唯一索引创建逻辑。
- 增加 trace 计时字段，覆盖 allowlist、insert、commit、refresh 与重复请求分支。

2. `backend/app/routers/company_v2_financial_fusion.py`
- 将 create 路径的 report 加载收窄为轻量字段。
- 避免 job create 时提前 hydration 大对象。

3. `backend/tests/fundamental/test_phase6tn_*`
- 新增 job admission、insert returning、唯一约束、并发去重相关测试。
- 同步更新旧的轻量 admission 测试断言。

4. `backend/scripts/company_v2_financial_fusion_phase6tn_acceptance.py`
- 增加真实 acceptance 脚本，使用真实数据库、真实 job 表和真实 cache。
- 采集 DB floor、create trace、并发去重、连接池与安全性结果。

5. `backend/docs/artifacts/company_v2_financial_fusion_phase6tn_*`
- 写入 Phase 6T-N 的 DB floor、create trace、acceptance 与 final gate artifact。
- 结果显示真实 steady-state create p50 仍为 `1367.75 ms`，门禁未通过。

---
下一步：你需要操作

第一步：保留当前 admission 优化，不再回退到更重的 create 路径。

第二步：如果要继续压 create latency，先只做数据库层面的进一步 profile，重点看 report ownership 查询、commit 和连接池等待，不要扩大业务范围。

第三步：在新的真实结果出现前，维持 `stage2_rollout_status=hold`，不要把 `phase6tn_passed` 误标为 `true`。
