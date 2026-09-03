---
目前完成的工作汇总：

已完成

1. backend/app/agents/chat_skills/general_financial_answer_skill.py
- 收紧通用金融兜底技能的 can_handle 边界，保留最低优先级兜底，但不主动抢占财报解释、新闻催化、异动、风险、比较和需要确认的 action intent。
- 增加 RoutingDecision 元数据，普通问候和非金融问题不进入金融分析；指代问题在无明确会话实体时返回澄清。
- FinancialAgent 技术失败后才进入 RAG/LLM fallback；无可靠 evidence 时返回固定降级摘要，不调用 LLM、不编造具体股票事实。
- fallback 错误信息会清洗路径、密钥类字段和内部细节。

2. backend/app/agents/financial_agent.py
- 强化系统 prompt 的证据边界：所有数字、日期、涨跌幅、财务指标和新闻事实必须来自本轮工具结果、审核 RAG 或明确继承的实体上下文。
- 将 final_answer 定义为唯一结构化事实源，answer_text 改为 final_answer 的 markdown 视图，不再生成第二套结论。
- 增加 final_answer hardening：无 evidence 时降级为 insufficient；source 去重；risk/disclaimer 去重；unsupported numeric claim 替换为“未提供数字”并写入 warning flag。
- 工具异常经公开错误文案清洗，避免把 provider 异常写成公司无数据，也避免泄露 traceback、路径或 secret。

3. backend/app/agents/chat_llm_answerer.py
- fallback 模式新增 data_quality 输入和证据限制。
- fallback 无 evidence 时直接返回有限信息研究摘要，不调用 LLM，不输出具体数字、公司事实或完整工具分析。
- 保持原有 generate_answer 调用兼容，新增参数均为可选默认值。

4. backend/tests/fixtures/phase6u_general_financial_cases.json
- 新增 Phase 6U-P2 固定评测集，共 30 个案例，覆盖通用金融问题、具体 skill 分流、多轮继承、工具缺失、provider 异常、直接买卖指令、确定涨跌预测、重复来源和 answer/data_points 不一致等场景。

5. backend/tests/fundamental/test_phase6u_general_financial_fallback.py
- 新增 10 个 hermetic 测试，覆盖 can_handle 边界、无实体澄清、多轮 symbol 继承、新实体覆盖、比较分流、无 evidence 降级、source 去重、unsupported number 清理、fallback 不调用 LLM 和 answer_text/final_answer 一致性。

6. backend/tests/test_c14_fallback_answer.py 与 backend/tests/test_c16_financial_agent_phase1.py
- 更新既有测试预期以匹配新兜底边界和 final_answer 单一事实源契约。
- 保持 AgentResponse、FinalAnswer 和流式 final_answer 事件结构兼容。

7. 验证结果
- targeted：`cd backend && .venv/bin/python -m pytest -q tests/fundamental tests -k "general_financial or financial_agent or chat_llm or phase6u"`，结果 61 passed。
- hermetic：`cd backend && .venv/bin/python -m pytest -q -m "not live_supabase"`，结果 3105 passed, 15 deselected。
- 额外编译检查通过：`python -m py_compile` 覆盖三个主链文件和新增测试。

---
下一步：你需要操作

第一步：查看 P2 范围 diff：
`git diff -- backend/app/agents/chat_skills/general_financial_answer_skill.py backend/app/agents/financial_agent.py backend/app/agents/chat_llm_answerer.py backend/tests/test_c14_fallback_answer.py backend/tests/test_c16_financial_agent_phase1.py`

第二步：查看新增评测和测试：
`git diff -- backend/tests/fixtures/phase6u_general_financial_cases.json backend/tests/fundamental/test_phase6u_general_financial_fallback.py`

第三步：提交前注意当前 worktree 还包含 Phase 6U-P1 和 Phase 6T 的既有未提交改动；如需只提交 P2，请按文件显式 stage。
