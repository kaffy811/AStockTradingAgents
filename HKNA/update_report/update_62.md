---
目前完成的工作汇总：

已完成

1. Phase 6U-E1.1 测试分层与默认后端门禁
- 新增 pytest marker：unit、integration_local、integration_live、live_external、soak，并兼容 legacy live_supabase。
- 默认 pytest -q 仅运行本地确定性测试，自动跳过 Supabase、CNINFO、BaoStock、live RAG worker、soak 等外部依赖用例。
- 将此前 15 个 live Supabase/RAG/worker 失败归类为 live external，不再阻塞默认 full backend。
- 已补充测试分层说明文档：backend/docs/artifacts/test_suite_layering.md。

2. Layered runtime shadow gate artifact
- 新增 hermetic contract shadow gate 脚本：backend/scripts/financial_agent_shadow_gate.py。
- 生成 shadow 对比 artifact：financial_agent_shadow_results.json、financial_agent_shadow_summary.md、financial_agent_runtime_gate.json。
- 覆盖首批五类 intent：financial_report、financial_comparison、official_report_pdf、financial_snapshot、quote_query。
- 当前 gate 明确保持 layered_v1 关闭，authorized_intents 为空。

3. Shadow gate 测试与默认 full 验证
- 新增 backend/tests/fundamental/test_phase6u_e1_1_shadow_gate.py。
- targeted shadow gate 测试通过。
- backend 默认 full：3260 passed, 15 skipped。
- frontend Vitest 与 npm build 已通过。

4. 切流状态
- CHAT_RUNTIME_MODE 仍保持 legacy。
- Stage 3 未开启。
- auto_run=false、rollout_percent=0 未变更。
- 未新增 migration，未破坏公开 schema。

---
下一步：你需要操作

第一步：在具备 Supabase、RAG worker、CNINFO/BaoStock 网络条件的环境中单独执行 live_external 和 soak。

第二步：补充真实 legacy vs layered_v1 shadow 浏览器验收，尤其是多轮财报比较、RAG unavailable、Auth 503、stale cache、conversation reload。

第三步：只有 runtime gate 中 blocker 清零且 shadow/entity/fact/latency 指标满足阈值后，再按 intent allowlist 逐项切 layered_v1。
