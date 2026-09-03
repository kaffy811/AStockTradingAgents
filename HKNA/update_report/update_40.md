---
目前完成的工作汇总：

已完成

1. Phase 6U-P1 财报解释主链统一
- 新增 `backend/app/agent/report_context.py`，统一两条财报解释路径的报告选择规则。
- 实现优先级：显式 `report_id`、显式年份/报告期、会话绑定 `report_id`、最新正式报告、找不到报告时明确返回数据限制。
- 显式 `report_id` 不合法或不属于当前公司时不回退其他报告。

2. ReportChatCopilotAgent 调整
- `backend/app/agent/report_chat_copilot_agent.py` 现在在 RAG、Prompt、cache 和 memory 前先解析选定报告。
- Prompt 输入加入 `report_metadata`，并将 RAG 检索限制到选定 `report_id`。
- review 未通过时降级强结论并标记 `partial=true`。

3. ReportExplanationSkill 调整
- `backend/app/agents/chat_skills/report_explanation_skill.py` 主路径改为复用 `ReportChatCopilotAgent`。
- 多轮追问沿用 memory 中的股票和报告上下文。
- 无法确认公司或市场时请求澄清，不默认 CN 或最新报告。

4. Prompt、cache、memory、RAG 支持
- 重写 `backend/app/agent/prompts/report_chat_system.md`，明确事实、解释、数据限制三层边界。
- `backend/app/agent/report_chat_cache.py` 的 cache key 纳入 `report_id`。
- `backend/app/agent/report_chat_session_memory.py` 保存并注入 `report_context`。
- `backend/app/services/report_rag_service.py` 支持按 `report_id` 过滤。

5. 测试与评测
- 新增 `backend/tests/fixtures/phase6u_report_prompt_cases.json`，包含 20 个固定评测案例。
- 新增 `backend/tests/fundamental/test_phase6u_report_chain_alignment.py`。
- 更新既有 report chat 测试以适配显式报告选择。
- 已通过 targeted：`56 passed, 1231 deselected`。
- 已通过 hermetic：`3095 passed, 15 deselected`。

---
下一步：你需要操作

第一步：如需复验 targeted 测试，执行：
`cd backend && .venv/bin/python -m pytest -q tests/fundamental -k "report_chat or report_explanation or phase6u"`

第二步：如需复验 hermetic 全量测试，执行：
`cd backend && .venv/bin/python -m pytest -q -m "not live_supabase"`

第三步：提交前确认当前工作树里已有的 Phase 6T artifact 修改是否需要单独提交或排除；本次 Phase 6U 主要改动集中在 `backend/app/agent`、`backend/app/agents/chat_skills/report_explanation_skill.py`、`backend/app/services/report_rag_service.py`、`backend/app/routers/report_chat.py` 和相关测试。
