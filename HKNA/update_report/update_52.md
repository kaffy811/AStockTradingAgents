---
目前完成的工作汇总：

已完成

1. Company V2 普通页面状态简化
- 修改 `frontend/src/components/company-v2/CompanyV2Section.vue` 和 `CompanyV2UnavailablePanel.vue`。
- 普通模式默认隐藏“数据完整 / 数据正常 / 覆盖有限 / 暂无可用数据”等阅读噪音。
- 仅保留影响判断的提示：行业不适用、指标口径待确认、历史数据不足、极端值低基数、报告处理/失败/无正式报告。
- 空模块统一显示“当前暂无该类数据。”，debug 模式继续保留原始诊断。

2. completeness 与 validity 状态拆分
- 修改 `backend/app/services/company_v2_history_service.py`。
- 为历史模块增加 `completeness_status`、`semantic_status`、`outlier_status`、`formula_status` 和 `user_message`。
- 修改 `backend/app/datasource/history_financial_provider.py`，对 CFO/净利润等极端比例标记 `semantic_status=warning`、`outlier_status=extreme`。
- 301396 类 7041.10% 极端比例保留原值，但不再被普通 UI 呈现为“数据正常”。

3. 正式报告分类和 annual_full 过滤
- 新增 `backend/app/services/report_document_classifier.py`。
- 增量返回 `report_document_kind`、`classification_version`、`classification_reason`，无数据库 migration。
- 年报列表和正式报告选择排除问询函回复、风险提示、延期披露、更正/修订/补充、审计报告、董事会决议、提示性公告和英文版。
- 修改 `backend/app/routers/company_v2_debug.py` 和 `backend/app/agent/report_context.py`，annual 列表只返回 `annual_full`。
- 修改 `frontend/src/components/company-v2/CompanyV2ReportTimeline.vue`，普通模式二次防守过滤非 `annual_full` 公告，debug 模式可见全部。

4. 多轮财报对比上下文
- 新增 `backend/app/services/company_alias_resolver.py`，支持贵州茅台/茅台、五粮液、宁德时代、京东方A/京东方。
- 修改 `backend/app/agents/chat_orchestrator.py`，成功财报回答后写入 recent symbol 与 `last_report_id`。
- 修改 `backend/app/agents/central_planning_agent.py`，识别“它和五粮液比呢”等带上下文的财报比较追问，并规划为 `report_financial_comparison`。
- 保持公开 Skill 清单为 7 个，未破坏 C9/C10/C15 manifest；`ReportComparisonSkill` 由 `ReportExplanationSkill` 内部委派执行。

5. 财报比较 Skill
- 新增 `backend/app/agents/chat_skills/report_comparison_skill.py`。
- 工作流：解析左右公司、选择正式年报、对齐报告年份、读取 indexed report chunks、抽取结构化字段、生成确定性 Markdown 对比表。
- 缺失字段保留“暂无可靠证据”，不填 0、不跨年替代。
- 使用现有 `company_v2_snapshot_cache_service` 缓存 `report_compare:{left_report_id}:{right_report_id}:metric_v1:v1` 对齐结果。

6. 测试与构建
- 新增 `backend/tests/fundamental/test_phase6u_d6_states_reports_comparison.py`。
- 新增 `frontend/src/tests/companyV2Phase6UD6StatesReportsChat.test.js`。
- 更新 `frontend/src/tests/companyV2Phase6UD5IndustryReport.test.js` 以符合 D6 空状态文案。
- targeted backend：17 passed；失败修复后相关回归 11 passed。
- full backend：3210 passed, 1 skipped。
- frontend vitest：674 passed。
- npm build：passed。

---
下一步：你需要操作

第一步：在真实浏览器访问 `/stocks/CN/301396`，确认经营现金流/净利润极端值保留原值，普通页不显示“数据正常”，并显示低基数提示。

第二步：访问 `/stocks/CN/300209`，确认年报列表不再把问询函回复、延期披露、风险提示等公告作为正式年报正文展示。

第三步：在 Chat 新会话中先问“贵州茅台最新财报表现如何？”，再追问“那它和五粮液比呢”，确认继承 600519 上下文、识别 000858、进入财报比较路径并输出对比表。

第四步：如需复跑验证，执行：
- `uv run pytest -q`
- `npm --prefix frontend run test -- --run`
- `npm --prefix frontend run build`
