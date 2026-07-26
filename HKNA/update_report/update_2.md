---
目前完成的工作汇总：

已完成

1. CompanyV2 staged default 配置
- `frontend/src/views/StockDetailView.vue`：默认策略调整为 dev/staging 使用 v2，production 未显式配置时保持 legacy。
- `frontend/.env.example`：新增 `VITE_COMPANY_TAB_VERSION=v2` 示例。
- `frontend/.env.production.example`：新增 `VITE_COMPANY_TAB_VERSION=legacy` 示例。
- `backend/docs/artifacts/company_v2_staged_rollout.md`：记录 URL 强制 v2/legacy 和生产回退步骤。

2. report_documents / report_rag 语义修正
- `backend/app/services/company_v2_debug_service.py`：`documents_count=0` 不再作为 filled field，也不再显示 OK。
- `report_documents` 空状态返回 `REPORT_PDF_NOT_FOUND`。
- `report_rag` 按 `documents_count/chunks_count/embedding_count` 区分 `REPORT_PDF_NOT_FOUND` 与 `REPORT_NOT_INGESTED`。
- `backend/app/services/company_v2_debug_diagnosis_service.py`：诊断分类器优先识别报告文件与 RAG 空状态。

3. 价格标签与财务 display metadata
- BaoStock/history fallback 增加 `price_is_realtime=false`、`price_label=最近收盘价`、`price_as_of`。
- AkShare 实时源增加 `price_is_realtime=true`、`price_label=最新价`、`price_as_of`。
- 财务比率新增 `raw_value/display_value/display_type`，不改变原始 normalized value。

4. CompanyV2 前端 polish
- `CompanyV2Section.vue`：报告/RAG 空状态显示业务文案，missing fields 折叠展示，中文字段名显示。
- `CompanyV2MetricCards.vue`：卡片优先显示 `display_value`，hover 保留 `raw_value`。
- `CompanyV2FallbackTable.vue`：表格优先显示 `display_fields`，不把 null 转 0。
- `CompanyV2View.vue`：report/RAG/AI 状态模块作为状态 panel 保留展示，不进入旧泛化错误文案。

5. 测试和验收文档
- 新增 `backend/tests/fundamental/test_phase6o5_company_v2_semantics_polish.py`。
- 新增 `frontend/src/tests/companyV2Semantics.test.js`。
- 新增 `backend/docs/artifacts/company_v2_phase6o5_semantics_report.md`。
- 验证结果：Phase 6O-5 后端测试、后端全量、前端全量、前端 build 均通过。

---
下一步：你需要操作

第一步：如需本地人工验收，启动前端时使用 `VITE_COMPANY_TAB_VERSION=v2 npm run dev`，打开 `/stocks/CN/600519`、`/stocks/CN/000725`、`/stocks/CN/601686`。
第二步：用 `/stocks/CN/600519?company_v2=0` 验证 legacy 回退仍可用。
第三步：确认页面中报告文件 0-count 不显示 OK、RAG 0-count 不显示 OK、历史 K 线价格显示“最近收盘价”。
第四步：若人工验收通过，可以进入 Phase 6O-6：Legacy Company Tab Deprecation Plan。
