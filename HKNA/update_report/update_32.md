---
目前完成的工作汇总：

已完成

1. `backend/docs/artifacts/company_v2_phase6to_*`
- 补齐数据库拓扑、DNS 矩阵、测试环境矩阵、SLO evidence、final gate 等 Phase 6T-O 证据。
- 将 hermetic 与 live integration 分层写清楚，避免把公网 DNS 故障当成业务正确性失败。
- 后续用网络权限完成了 live Supabase tests，当前阻塞只剩同区域 runner 未 provision 和 steady-state create 门槛未过。

2. `backend/tests/fundamental/test_phase6tj1_*`
- 将 DB-backed 持久化测试显式标成 `live_supabase`。
- hermetic 集合可稳定通过，live 集合保留真实 DNS 失败结果。

3. `backend/docs/artifacts/company_v2_phase6tp_*`
- 新增 Phase 6T-P 的 endpoint validation、DNS matrix、same-region runner、same-region acceptance、cross-region comparison、live integration tests、deployment recommendation 与 final gate。

4. `backend/docs/artifacts/company_v2_financial_fusion_phase6tn_acceptance.*`
- 将 `minimum_expected_create_ms` 修正为 `estimated_sequential_db_cost_ms`，并说明这是粗略顺序成本估计，不是严格 lower bound。

---
下一步：你需要操作

第一步：如果要继续推进 live acceptance，先把可解析的 same-region runner 建起来，再跑 `live_supabase`。

第二步：如果 runner 不可用，就保留当前 hold 结果，不要调整 300ms gate 来掩盖跨区域网络成本。

第三步：后续只在真实可达的环境里重新采样同区域 create latency 和 endpoint validation。
