---
目前完成的工作汇总：

已完成

1. backend/app/agents/specialist_analysis_utils.py
- 新增四个专业分析 Agent 共用的数值与输出边界辅助逻辑。
- 覆盖百分比、金额、普通数值、日期、缺失值、0 值保留、NaN/inf/None 清洗、绝对路径和 credential 形态清洗。
- 增加窄问题 focus 检测和统一 observed_facts / analysis / limitations / watch_items 边界提示。

2. backend/app/agents/fundamental_analyst.py
- 保持现有 analyze 调用兼容，支持可选 question。
- 强化估值缺失固定口径：PE/PB 缺失时必须写“本次未提供可用估值数据”或“估值数据缺失，暂不评价估值水平”。
- 输出经过 specialist sanitizer，避免无来源数字、买卖指令、None/NaN/inf、路径或 credential 形态进入用户输出。

3. backend/app/agents/technical_analyst.py
- 当前分支已具备 P3 结构：支持可选 question/focus、明确日 K 周期和截至日期、quote 与 K 线价格来源分离、无证据支撑压力不生成精确价位。
- 输出经过 specialist sanitizer，避免确定性预测、直接买卖指令和无来源数字。

4. backend/app/agents/news_analyst.py
- 新增新闻去重、来源类型分类、可选 question/focus 和统一四层回答边界。
- 新闻工具异常时不暴露 traceback、路径或密钥形态，不把工具失败写成公司没有新闻。
- 空新闻、来源缺失和 keyword search 情况要求降级说明。

5. backend/app/agents/peer_comparison_analyst.py
- 新增可选 question/focus，sync/async 两条调用保持兼容。
- 报告期不一致时加入禁止直接排序的警告；样本少于 2 家时明确“无法形成稳定同行结论”。
- 字段缺失、全体缺失、target 缺失和估值缺失保留不可比边界。

6. backend/tests/fixtures/phase6u_specialist_analysis_cases.json
- 新增固定评测集 40 个案例，Fundamental、Technical、News、Peer 四类各 10 个。

7. backend/tests/fundamental/test_phase6u_specialist_analysis.py
- 新增 hermetic 单元测试覆盖 40-case fixture、公共格式化、0 值保留、None/NaN/inf 清洗、财务报告期、技术时间范围、新闻日期/来源/去重、同行样本和报告期、无来源数字清洗、买卖指令清洗、route schema 和 ComprehensiveAnalysisCoordinator 初始化兼容。

8. backend/docs/artifacts/phase6u_specialist_analysis_quality_baseline.json
- 新增当前版本质量基线记录。
- 说明本 session 未在修改前采集真实 live route 输出，因此不伪造 before/after；当前 baseline 记录为 hermetic 验证基线。

9. 验证结果
- 新增测试：`11 passed, 1 warning`。
- targeted：`31 passed, 1281 deselected, 1 warning`。
- full hermetic：`3120 passed, 15 deselected, 208 warnings`。

---
下一步：你需要操作

第一步：如需真实人工质量 before/after，请在干净基线分支先运行四个 `/analysis/*` route 并保存输出，再与当前分支输出对比。
第二步：提交前注意当前 worktree 还包含 Phase 6U-P1/P2 的既有未提交改动；如需只提交 P3，请按文件显式 stage。
第三步：推荐提交信息：`feat(agent): harden specialist analysis prompts and data boundaries`。
