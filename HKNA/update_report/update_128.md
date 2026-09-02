---
目前完成的工作汇总：

已完成

1. `official_company_event_service.py`
- 新增只读 CNINFO 官方事件投影服务，仅消费已持久化官方元数据。
- 强制每个可见事件具有标题、披露日期、CNINFO 官方链接、事件分类与 as_of 字段。
- 支持九类官方事件；过滤证据字段不完整的记录，不输出数据库 ID 或内部状态。

2. `chat_orchestrator.py`
- 新增 `official_company_events` 与 `official_report_analysis` 确定性路由。
- 行业、市场与主题产业链新闻在任何工具调用前返回 `NO_APPROVED_INDUSTRY_NEWS_SOURCE`。
- 官方事件回答固定包含结论摘要、近期官方事件、已知事实与影响边界、数据局限和来源。
- 未修改 LLM Prompt；普通财报分析继续使用既有 Report RAG 路径。

3. `test_phase7c1_cninfo_official_event_research.py`
- 新增 17 项专项测试，覆盖 fulfilled、partial、unavailable、来源字段、事件分类、指定事件类型真实性、零未批准 Provider 调用和公开字段防泄漏。

4. 回归验证
- Phase 7C1：17 passed。
- Report RAG、citation、numeric validation：50 passed。
- 既有 Chat/Report 路由：46 passed。
- 总计 113 passed；原 112 项相关回归全部通过，新增 1 项事件类型真实性测试，没有失败。

5. Phase 7C1 审计交付物
- 生成 `backend/docs/artifacts/phase7c1_cninfo_official_event_research.md`。
- 生成 `backend/docs/artifacts/phase7c1_cninfo_event_runtime_trace.json`。
- 未执行 live 抓取、部署、migration、commit、push、merge 或扩流。

---
下一步：你需要操作

第一步：审阅 `backend/docs/artifacts/phase7c1_cninfo_official_event_research.md` 的覆盖限制，确认当前持久化 CNINFO 数据是否包含普通公告，还是主要只有定期报告。
第二步：在隔离 staging 数据库中只读验证目标公司的已有 CNINFO 记录；不要开启 live discovery 或新闻 Provider。
第三步：若 staging 验证结果符合预期，再另行审批发布流程；本阶段不要部署、执行 migration 或扩流。
