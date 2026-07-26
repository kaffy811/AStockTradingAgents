---
目前完成的工作汇总：

已完成

1. Phase 6U-E1.2 live shadow acceptance artifact
- 新增 backend/scripts/financial_agent_live_shadow_acceptance.py。
- 建立真实 shadow acceptance 的 artifact schema，覆盖 live shadow results、intent gates、runtime gate 和 markdown summary。
- 无 live 授权或外部环境不可用时，不把 planned case 计入 accepted sample，避免将 hermetic 结果冒充真实流量。
- 当前生成 56 个 planned cases，executed_sample_count=0，runtime gate 保持 do_not_enable_layered_v1。

2. Intent 独立 Gate
- 新增 financial_agent_intent_gates.json。
- official_report_pdf、quote_query、financial_snapshot、financial_report、financial_comparison 均独立记录 requested_samples、executed_samples、blockers。
- 本轮未授权任何 intent，authorized_intents=[]。

3. Live external / soak 结果记录
- 单独执行 pytest -q -m "integration_live or live_external"，当前环境因 Supabase pooler DNS 解析失败，15 failed。
- 单独执行 pytest -q -m soak，当前无匹配 soak marker 测试，pytest 返回 no_tests_collected。
- 上述结果已写入 financial_agent_live_shadow_summary.md 和 financial_agent_runtime_gate.json。

4. 测试与构建
- E1.2 targeted tests 通过。
- backend 默认 full 通过：3264 passed, 15 skipped。
- frontend Vitest 通过：679 passed。
- npm run build 通过。

---
下一步：你需要操作

第一步：在具备 Supabase pooler DNS/网络、RAG worker、CNINFO/BaoStock 外部依赖的环境中重新执行 live_external。

第二步：启动真实浏览器会话并在 CHAT_RUNTIME_MODE=shadow 下采集 50-100 条真实 legacy vs layered shadow 样本。

第三步：当 live shadow、browser acceptance、DB reliability 和 per-intent gate 均满足阈值后，再进入下一阶段讨论单 intent 授权。
