---
目前完成的工作汇总：

已完成

1. `backend/app/agents/comprehensive_analysis_coordinator.py`
- 调优默认综合分析协调器的系统 Prompt，统一为十段综合输出结构：综合结论、核心事实卡片、基本面与财务、市场与技术、新闻与事件、同行位置、关键联动、主要风险、数据限制、后续观察。
- 将综合层输入从完整 Markdown 子报告改为结构化证据摘要，优先保留关键事实、数字、风险、limitations、时间范围和来源，避免重复把完整子报告喂给综合 LLM。
- 新增综合后处理校验：数字白名单、symbol/name/market 校正、禁止词清理、来源范围检查、limitations 保留、重复段落去重。
- 新增 partial 与全部缺失降级：任一子报告失败或为空时保留成功维度并标记 `metadata.partial`；四个子报告均缺失时不调用综合 LLM，直接返回数据不足报告。
- 保持外部 schema 兼容：`report`、`sections`、`metadata` 原有字段保留，`sections` 继续保存四个原始子报告。

2. `backend/tests/fixtures/phase6u_production_regression_cases.json`
- 新增 30 条 production regression smoke suite。
- 覆盖财报与基本面 8 条、多轮追问 6 条、综合分析 4 条、技术面 4 条、新闻面 4 条、数据缺失与安全 4 条。
- 每条记录包含 expected_route、expected_skill、expected_agent、required_tools、expected_entity、expected_market、expected_report_context、prohibited_content、required_limitations、expected_output_shape。

3. `backend/tests/fundamental/test_phase6u_production_regression.py`
- 新增 hermetic regression 测试，不触发真实 provider、RAG 或 Fusion。
- 覆盖 fixture 可加载、主链路由合约、多轮实体继承、新实体覆盖旧实体、report_id 继承合约、窄问题输出、综合报告不新增数字、不重复完整子报告、保留 limitations、冲突显式标注、partial、全部缺失不空泛生成、安全输出、schema 不变、前端字段不变、不新增 skip。

4. `backend/docs/artifacts/phase6u_comprehensive_analysis_quality.*`
- 新增综合协调器质量 artifact，记录 fixture_total、route_accuracy、entity_inheritance_accuracy、unsupported_number_count、duplicate_section_count、missing_limitation_count、safety_violation_count、schema_regression_count、targeted tests 和 hermetic tests。

5. `backend/docs/artifacts/phase6u_production_regression_summary.*`
- 新增 30 条生产回归集 summary artifact，记录分组、覆盖点、指标和测试结果。

6. 验证结果
- 已运行：`cd backend && .venv/bin/python -m pytest -q tests/fundamental -k "comprehensive or production_regression or phase6u"`
- 结果：`49 passed, 1282 deselected, 1 warning`
- 已运行：`cd backend && .venv/bin/python -m pytest -q -m "not live_supabase"`
- 结果：`3139 passed, 15 deselected, 206 warnings`
- 未进入部署、Stage 3、auto_run、rollout 或 Canary。

---
下一步：你需要操作

第一步：审阅本轮 diff，重点查看 `backend/app/agents/comprehensive_analysis_coordinator.py` 的综合 Prompt、结构化摘要和 post-validation 逻辑。

第二步：如需提交，使用推荐提交信息：`feat(agent): harden comprehensive synthesis and production regression`。

第三步：进入下一阶段前，先用真实但只读的 shadow 数据复核综合报告可读性；不要在本轮直接开启 Stage 3、Canary 或生产 rollout。
