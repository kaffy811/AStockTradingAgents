---
目前完成的工作汇总：

已完成

1. BaoStock runtime dependency
- `backend/uv.lock` 已写入 `baostock==0.9.3`。
- `uv sync --frozen` 已验证通过。
- `uv pip show baostock` 与 `.venv/bin/python -c "import baostock"` 已验证运行环境可导入。
- BaoStock 缺失时 provider 不再返回 success，而是返回 `PROVIDER_UNAVAILABLE`。

2. Company V2 历史财务状态诊断
- `backend/app/datasource/baostock_client.py`
- `backend/app/datasource/history_financial_provider.py`
- `backend/app/services/company_v2_history_service.py`
- `backend/app/routers/fundamentals_compat.py`
- 修复 provider import failure / empty / partial / success 状态区分。
- annual history 少于 3 个年度点时标记 `insufficient_history`。

3. CNINFO 查询核心统一
- canonical implementation 为 `backend/app/datasource/cninfo_provider.py`。
- `backend/app/tools/reports/cninfo_report_search_tool.py` 改为复用 canonical client/parser。
- `backend/app/agents/official_report_search.py` 改为复用 canonical client/parser。
- 统一 report_type/category/period 映射、Referer/headers、timeout/retry、PDF URL HTTPS 白名单校验和诊断状态。

4. 600519 报告闭环与 RAG 对齐
- 复用 `report_documents`，未创建 `company_reports`。
- `backend/app/services/report_document_service.py` 和 `backend/app/routers/company_v2_debug.py` 修复 `source_url`/`pdf_url` 持久化。
- `backend/app/services/report_rag_service.py` 增加 Company V2 RAG bridge，使 report-chat 可按 `report_id` 读取 `company_v2_report_rag_chunks`。
- 600519 当前最新 report_id=2，download/parse/index 完成，chunk_count=211。

5. Demo readiness 脚本和 artifact
- 新增 `backend/scripts/phase6u_demo_data_readiness.py`。
- 新增 `backend/docs/artifacts/phase6u_demo_data_readiness.json`。
- 新增 `backend/docs/artifacts/phase6u_demo_data_readiness.md`。
- 脚本仅允许 600519、300750、000725、000001、601686。
- artifact 不输出 secret、本地绝对路径，只输出 URL host 和状态。

6. Targeted tests
- 新增 `backend/tests/fundamental/test_phase6u_d1_demo_data_readiness.py`。
- 更新 CNINFO discovery、official report search、C15 real-chain contract 测试。
- affected/targeted 回归：150 passed。
- full 回归：3167 passed。

---
下一步：你需要操作

第一步：如需复核依赖，执行：
`cd backend && uv sync --frozen && uv pip show baostock`

第二步：如需刷新 demo readiness，执行：
`cd backend && .venv/bin/python scripts/phase6u_demo_data_readiness.py --history`

第三步：如需继续准备 601686 报告，执行 allowlist 脚本的 discover/prepare 流程，确认其 download、parse、rag/index 变为 ready。

第四步：如需继续后续阶段，再单独开启 Stage 3 / auto_run / rollout 任务；本轮没有修改这些模块。
