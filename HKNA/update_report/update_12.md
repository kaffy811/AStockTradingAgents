---
目前完成的工作汇总：

已完成

1. CompanyV2 Full-History 后端链路
- 更新 `backend/app/datasource/history_financial_provider.py`，将全模块历史财务数据获取改为单次 BaoStock aggregate 复用，避免每个模块重复打 provider。
- 保留 `latest` / `history` / `period_type` / `chart_contract` / `history_coverage` 输出结构。
- 修复 period classifier 对季度序列中 `12-31` 的误判。

2. CompanyV2 Debug Full History 参数
- 更新 `backend/app/routers/company_v2_debug.py` 和 `backend/app/services/company_v2_debug_service.py`。
- `/api/v2/company/{market}/{symbol}/debug/full` 新增 `history=true&period=annual|quarterly|all&start_year&end_year`。
- 默认 snapshot 行为不变；启用 history 时附加 `history` 与 `stock_basic`，并把模块级 history/chart_contract 写入各模块 envelope。

3. CNINFO 报告发现服务
- 新增 `backend/app/services/cninfo_report_discovery_agent.py`。
- 更新 `backend/app/services/cninfo_org_resolver.py`，增加 `resolve_cninfo_stock()`。
- 更新报告 endpoints，支持年报、半年报、一季报、三季报 timeline 合并输出。
- PDF URL 继续通过 CNINFO `adjunctUrl` 派生并由白名单校验。
- 增加 CNINFO fulltext search fallback；当 hisAnnouncement category 查询为空时，通过官方 fulltext JSON 读取 `adjunctUrl`，不枚举 PDF ID。
- 真实网络验证 `601686` 2024 年：发现 1 份年报、1 份三季报，PDF URL 均来自 `https://static.cninfo.com.cn/`。

4. CompanyV2 前端 Dashboard 接入
- 更新 `frontend/src/views/CompanyV2View.vue`，默认请求 `debug/full?history=true&period=quarterly`，并显示 Company Profile + Stock Basic。
- 更新 `frontend/src/components/company-v2/CompanyV2ReportDocuments.vue`，改用 `CompanyV2ReportTimeline.vue` 统一展示报告 timeline、筛选、复制和发现入口。
- 新增 `CompanyV2OperationChart.vue` 与 `CompanyV2SolvencyChart.vue` 兼容组件名，并在 `CompanyV2Section.vue` 中使用。

5. Report/RAG 空状态语义回归
- 修复 `report_documents` / legacy `report_rag` zero-count 语义。
- `documents_count=0` 不再算 displayable/OK，但模块仍 renderable 以展示空状态面板。
- `report_rag` 直连旧测试路径保留严格 RAG-ready 判断。

6. 测试与构建
- 新增/更新 Phase 6T-B regression 测试，覆盖单次 BaoStock aggregate 复用。
- 已通过：
  - `pytest backend/tests/fundamental/test_phase6tb_full_history_financials.py backend/tests/fundamental/test_phase6tb_cninfo_reports.py backend/tests/fundamental/test_phase6tb_company_stock_basic.py -q`
  - `pytest -q`
  - `npm run test`
  - `npm run build`

---
下一步：你需要操作

第一步：在具备正常公开数据源网络的 dev/staging 环境打开 `/stocks/CN/601686`，确认默认 CompanyV2 页面展示公司资料、行情估值、历史财务图表和报告文件 timeline。

第二步：如需真实 CNINFO 验收，执行报告发现接口或页面“发现报告”，确认 PDF URL 来自 `static.cninfo.com.cn` 且 report_rag 不再作为独立主模块展示。

第三步：如果真实 CNINFO 返回为空，保留当前空状态，不要手工猜测 PDF ID；下一阶段进入 `Phase 6T-C：PDF Parsing and Official Disclosure Verification`。
