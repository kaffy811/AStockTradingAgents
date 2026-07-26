---
目前完成的工作汇总：

已完成

1. `backend/app/agents/financial_runtime/`
- 新增 Phase 6U-E1 分层金融 Agent Runtime 骨架。
- 包含 L0 router、L1 planner/context、L2 tool runtime、L3 domain agents、L4 drafting renderer、L5 compliance gate 和统一 contracts。
- 默认不替换 legacy，通过 `CHAT_RUNTIME_MODE=legacy|layered_v1|shadow` 控制。

2. `backend/app/agents/chat_orchestrator.py`
- 接入 `CHAT_RUNTIME_MODE`。
- `legacy` 默认不变；`shadow` 使用新 DB session 后台运行 layered runtime，不双写消息；`layered_v1` 可直接返回新 runtime 响应，异常回落 legacy。

3. `backend/app/services/company_v2_report_evidence_service.py`
- 新增 async report evidence service。
- layered Chat request path 可通过原生 async RAG document lookup 获取报告证据，避免 legacy sync bridge。

4. `backend/app/services/official_report_domain_service.py`
- 新增官方报告共享 domain service。
- Tool Runtime 通过 service 获取 `annual_full` 报告，不在 Chat Tool 中直接复制报告分类 SQL。

5. `backend/app/services/company_v2_report_rag_db_repository.py`
- 增加 `get_document_async`、`get_any_document_async`、`get_any_document_metadata_async`。
- legacy sync facade 保留，但 layered Chat path 使用 async API。

6. 架构文档
- 新增 `backend/docs/artifacts/financial_agent_runtime_architecture.md`。
- 新增 `backend/docs/artifacts/financial_agent_data_contracts.md`。
- 新增 `backend/docs/artifacts/financial_agent_tool_registry.md`。
- 新增 `backend/docs/artifacts/financial_agent_migration_plan.md`。

7. 测试
- 新增 `backend/tests/fundamental/test_phase6u_e1_layered_runtime.py`。
- 覆盖 L0/L1/L2/L3/L4/L5 职责边界、无 sync RAG bridge、async RAG API、ToolResponse 契约和 disclaimer owner。

8. 验证
- E1 targeted：`10 passed`。
- D6.4 + pool targeted：`10 passed`。
- Python compileall：通过。
- frontend Vitest：`678 passed`。
- npm build：通过。
- full backend：`3257 passed, 2 failed`；两个 live DB 失败项单独重跑 `2 passed`，判定为 full run 中 Supabase/pooler 偶发超时。

---
下一步：你需要操作

第一步：保持默认 `CHAT_RUNTIME_MODE=legacy`，在本地或 staging 设置 `CHAT_RUNTIME_MODE=shadow` 观察 layered route/entities/tools/findings 对比。

第二步：针对首批五个场景跑浏览器验收：显式公司财报、财报比较、官方 PDF、公司财务快照、简单行情。

第三步：shadow 稳定后再短时切换 `CHAT_RUNTIME_MODE=layered_v1`，不要同时开启 Stage 3、auto_run 或 rollout。
