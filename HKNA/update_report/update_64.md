---
目前完成的工作汇总：

已完成

1. Phase 6U-E1.3 live 环境预检
- 新增 backend/scripts/live_environment_preflight.py。
- 输出 backend/docs/artifacts/live_environment_preflight.json。
- 当前本地环境 environment_ready=false，Supabase pooler DNS、CNINFO、BaoStock、RAG 均未通过预检。
- artifact 已脱敏，不记录 DATABASE_URL、DB password、JWT、API key 或完整 IP。

2. DB pool strategy gate
- 新增 backend/scripts/live_db_pool_strategy.py。
- 输出 backend/docs/artifacts/live_db_pool_strategy.json。
- 当前因 preflight 不通过，small QueuePool 与 NullPool A/B 均未执行，selected_strategy=null。

3. Live external / soak 结果 artifact
- 新增 backend/scripts/live_external_test_results.py。
- 输出 backend/docs/artifacts/live_external_test_results.json。
- live_external 当前 15 failed，归类为 environment，原因是 Supabase pooler DNS 解析失败。
- soak 当前 no_tests_collected，原因是当前 marker 没有匹配测试。

4. SecurityMaster live sampling gate
- 新增 backend/scripts/security_entity_live_sampling.py。
- 输出 backend/docs/artifacts/security_entity_live_sampling.json。
- 记录 CN 5166 active、HK 30、US 0 的验收目标；当前 executed=0，原因是 preflight 不通过。

5. Runtime gate 保持关闭
- 更新 financial_agent_runtime_gate.json，recommended_next_intent=null。
- layered_enabled=false。
- authorized_intents=[]。
- decision=do_not_enable_layered_v1。

6. 测试与构建
- E1.3 targeted tests 通过。
- backend 默认 full 通过：3268 passed, 15 skipped。
- frontend Vitest 通过：679 passed。
- npm run build 通过。

---
下一步：你需要操作

第一步：在阿里云首尔 Ubuntu、受保护 secrets 的 GitHub Actions live job，或另一台能稳定访问 Supabase/CNINFO/BaoStock 的环境中运行 live_environment_preflight.py。

第二步：preflight 全部通过后，再执行 live_db_pool_strategy.py、live_external_test_results.py 对应的真实 live_external/soak 套件，以及 security_entity_live_sampling.py。

第三步：只有环境 ready 后，才执行 56 条 CHAT_RUNTIME_MODE=shadow 真实样本；完成后再评估是否可在下一阶段推荐 official_report_pdf 单 intent 授权。
