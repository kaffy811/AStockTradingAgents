---
目前完成的工作汇总：

已完成

1. `backend/app/agents/financial_runtime/contracts.py`
- 建立 layered runtime 数据契约，补齐 `RuntimeRequest`、`IntentRoutingResult`、`SecurityEntity`、`FinancialSessionContext`、`ExecutionPlan`、`ToolResponse`、`AgentResponse`、`StructuredAnswer`、`ComplianceReview`、`FinalChatResponse` 等结构。
- 统一状态枚举为 `success`、`partial_success`、`failed`、`clarification_required`、`unavailable`、`cancelled`。
- 所有顶层 contract 增加 `request_id`、`completed_at`、`warnings`、`metadata`。

2. `backend/app/agents/financial_runtime/router.py`
- 实现 L0 Intent & Safety Router。
- 支持首批迁移 intent：财报分析、财报比较、官方 PDF、财务快照、行情查询。
- 低置信和歧义证券进入 clarification，不直接猜测。

3. `backend/app/agents/financial_runtime/planner.py`
- 实现 L1 Context Builder 与 Execution Planner。
- 输出结构化 DAG plan 和普通 UI stage，不生成最终回答。
- 官方 PDF 走轻量 `get_official_report_url`，不触发重型 RAG/LLM。

4. `backend/app/agents/financial_runtime/tool_runtime.py`
- 实现 L2 Financial Tool Registry / Tool Runtime。
- 注册完整 capability 表，首批实现 Company profile、quote、financial snapshot/history、official reports、structured report financials、report evidence、financial comparison。
- Tool 复用 `CompanyChatDataService`、`stock_data_service`、`official_report_domain_service` 等页面背后的共享 Domain Service，不通过 localhost HTTP。
- Tool 执行支持 DAG 层级并发、单步 timeout budget、timeout 后结构化失败。

5. `backend/app/agents/financial_runtime/domain_agents.py`
- 实现 L3 Domain Agents 的标准输出契约。
- Agent 只消费 ToolResponse，不解析证券、不查询 DB、不调用 provider、不渲染 Markdown、不追加免责声明。

6. `backend/app/agents/financial_runtime/drafting.py` / `compliance.py`
- 实现 L4 deterministic StructuredAnswer 与 Markdown renderer。
- 实现 L5 rule-based compliance gate，输出结构化 edit instructions，不做全局字符串替换。
- 普通回答来源进入折叠区域，免责声明仍由前端 footer 单一 owner 负责。

7. `backend/app/agents/chat_orchestrator.py` / `backend/app/core/config.py`
- 增加 `CHAT_RUNTIME_MODE=legacy|layered_v1|shadow` 与 `CHAT_LAYERED_INTENTS`。
- 默认保持 `legacy`，不自动切换。
- `layered_v1` 只处理首批已迁移 intent，未迁移 intent 返回 `unavailable` 并回退 legacy。

8. RAG async facade
- `DatabaseCompanyV2ReportRagRepository` 增加 `query_chunks_async`、`get_structured_fields_async`、`get_latest_indexed_report_async`。
- layered runtime 路径静态 gate 确认不含 `run_coroutine_threadsafe`、`.result()`、`new_event_loop`、`asyncio.run(`。

9. 文档
- 更新 `financial_agent_runtime_architecture.md` 为 L-1 到 L5 七层架构。
- 更新 `financial_agent_data_contracts.md` 与 `financial_agent_tool_registry.md`。
- 新增 `page_domain_service_inventory.md`，梳理 Company、行情、财务、报告、新闻、行业等页面服务与 Chat capability 的对应关系。

10. 测试与验证
- E0/E0.1/E1 targeted backend：`27 passed, 1 warning`。
- E1 architecture targeted：`13 passed`。
- Frontend Vitest：`679 passed`。
- Frontend build：passed。
- Python compileall：passed。
- Full backend：`3258 passed, 15 failed, 298 warnings`；剩余失败集中在 live Supabase/RAG/worker 连接依赖。

---
下一步：你需要操作

第一步：保持 `CHAT_RUNTIME_MODE=legacy`，在测试环境显式切 `CHAT_RUNTIME_MODE=shadow` 观察 layered runtime 的 routing/entities/tools/findings 差异。
第二步：对首批五个 intent 分别开启 `layered_v1` 验证，不要一次迁移全部 legacy skill。
第三步：继续把技术面、资金面、新闻、行业数据接入 Tool Registry 的 deferred capability，并保持 Agent 只消费 ToolResponse。
