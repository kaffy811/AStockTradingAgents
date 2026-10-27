---
目前完成的工作汇总：

已完成

1. 数据管道与 Agent 代码导读
- 新增 `docs/DATA_PIPELINE_AND_AGENTS_GUIDE.md`，基于当前工作区梳理行情 Provider 回退、Redis / 内存缓存、基本面和新闻数据域、技术面 Agent、综合编排、LangGraph 与 Chat runtime 分流。
- 说明指标计算公式及边界，特别是均量包含最新 K 线、短历史极值仍可返回、缺失值过滤压缩序列、非有限值过滤不足及 Agent 接口未传递完整数据质量元信息。
- 区分源码默认值、可选路径和部署配置，未把旧文档中的规划当作当前执行事实。

2. 指标单元测试
- 新增 `backend/tests/test_technical_indicator_service.py`，11 个测试函数、30 个参数化用例，直接验证公开 `calculate()` 接口。
- 覆盖 MA5/10/20/60、正负收益与 N+1 根边界、均线偏离、滚动极值、成交量均值与量比、趋势和量能阈值、信号优先级、零分母、字段缺失、空结果及 JSON 序列化。
- 使用本地确定性数据，无网络、数据库或 LLM 依赖；本次未改动生产计算逻辑，保留工作区原有修改。

3. 验证
- 执行 `backend/.venv/bin/python -m pytest -q backend/tests/test_technical_indicator_service.py backend/tests/fundamental/test_phase6u_specialist_analysis.py`。
- 结果：58 passed（新增指标测试 30 项、已有专业 Agent 回归 28 项）。
- 一条 passlib 导入 `crypt` 的弃用警告；未执行全量测试、实时数据源检查或线上部署。

---
下一步：你需要操作

第一步：查看 `docs/DATA_PIPELINE_AND_AGENTS_GUIDE.md`，按入口、数据层、指标层、Agent 和编排顺序阅读。
第二步：如需单独复跑指标测试，在项目根目录执行 `backend/.venv/bin/python -m pytest -q backend/tests/test_technical_indicator_service.py`。
第三步：如需复跑本次完整验证，在项目根目录执行 `backend/.venv/bin/python -m pytest -q backend/tests/test_technical_indicator_service.py backend/tests/fundamental/test_phase6u_specialist_analysis.py`。本次修改无需额外配置或部署操作。
