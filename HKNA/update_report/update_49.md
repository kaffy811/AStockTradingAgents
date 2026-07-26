---
目前完成的工作汇总：

已完成

1. backend/app/agent/report_chat_copilot_agent.py
- 为 ReportChatCopilotAgent 增加整体 60 秒超时，任一 RAG、embedding、LLM、review 环节卡住时返回 failed + REPORT_AGENT_TIMEOUT + 非空用户提示。
- 增加 LLM/agent 响应字段抽取兼容，统一支持 answer、final_answer、content、response、text、message、result、choices[0].message.content。
- 对 LLM 空响应、JSON 解析失败、LLM 子调用超时建立非空降级回答，不编造财务数字。

2. backend/app/agents/chat_streaming.py
- 新增 answer_completed 与 message_persisted 事件，保证 agent_completed 之前已有明确最终正文事件和持久化事件。
- agent_completed 终态新增 assistant_message_id、answer_length、status、error_code。
- 增加 EMPTY_FINAL_ANSWER 最后防线，禁止 completed + 空正文。
- 修正 finally/exception 分支，answer_completed 后不再补发晚到的 fallback final_answer。

3. backend/app/agents/chat_orchestrator.py 与 report_explanation_skill.py
- SkillRegistry 路径统一将空 SkillResult 降级为 failed + EMPTY_FINAL_ANSWER。
- ReportExplanationSkill 使用 canonical answer 抽取，并透传 report agent 的 status、error_code、rag_status、source_chunks 等结构化信息。
- 保持 P1-P4 Prompt 未修改。

4. backend/app/services/chat_service.py
- 持久化层增加约束：无 confirmation 的 assistant message content 不允许为空。

5. frontend/src/utils/chatEventNormalizer.js 与 chatReducer.js
- 前端识别 answer_completed 与 message_persisted。
- ui_done 保留后端 terminal payload，不再丢弃 status/answer_length/message_id。
- completed + answer_length=0 且无正文时进入可恢复错误态，显示“回答生成失败，请重试”。
- 空 final answer 不覆盖已累计的 answer_delta；failed terminal 不再把 trace 强行标记为“已完成”。

6. 测试
- 新增/更新后端 stream、ReportChatCopilotAgent、LLM 字段兼容、timeout、空答案 guard 测试。
- 新增/更新前端 normalizer/reducer 测试，覆盖 final answer、空 final、failed terminal、message persisted。
- targeted backend: 34 passed。
- backend full: 3187 passed, 1 skipped。
- frontend vitest: 59 files passed, 665 tests passed。
- npm build: passed。

---
下一步：你需要操作

第一步：在真实 UI 新会话中再次发送“贵州茅台最新财报表现如何？”，确认超时时显示失败与重试，不再显示“已完成分析”但无正文。
第二步：如需完整正文而非 timeout 降级，继续单独排查 ReportRagService/embedding/LLM 慢点；本次已保证不会空白完成。
第三步：建议提交：
`fix(chat): guarantee final report answers and isolate financial providers`
