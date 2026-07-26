---
目前完成的工作汇总：

已完成

1. Phase 6T-C1 年报年度期核验闸口
- 更新 `backend/app/services/company_v2_official_verification_service.py`。
- 核验 2024 年年报时只允许匹配 `2024-12-31` / `report_year=2024` 的 annual history row。
- 如果 annual row 缺失，返回 `STRUCTURED_ANNUAL_ROW_NOT_FOUND`，不再 fallback 到 latest/current snapshot。
- 如果只有季度行，返回 `ANNUAL_PERIOD_REQUIRED`，不做强核验。

2. 冲突分类
- 增加 `PROVIDER_VALUE_CONFLICT`、`UNIT_SCALE_MISMATCH`、`FIELD_EXTRACTION_LOW_CONFIDENCE`、`FIELD_DEFINITION_MISMATCH`、`ROUNDING_DIFFERENCE` 等分类。
- `PERIOD_MISMATCH` / annual row 缺失不再算真实 provider value conflict。
- 每个字段输出 `official_value`、`structured_value`、`structured_period`、`official_report_year`、`relative_diff_pct`、`reason`、`conflict_type`。

3. Live API report_id 闭环
- 更新 `backend/app/routers/company_v2_debug.py`。
- CNINFO discover 返回的 report 会写入 `report_documents`，并返回真实 `id/report_id`。
- download / parse / verify 使用同一个 DB report_id。
- verify endpoint 使用 `history=true&period=annual&start_year=end_year=report_year` 构建年度结构化数据。

4. PDF 解析侧车文件
- 更新 `backend/app/services/company_v2_pdf_text_parser.py`。
- parse 后将完整 page text 存为本地 `.pages.json` sidecar，仅供后端字段抽取使用。
- API 仍只返回 excerpt/metrics，不返回完整 PDF 原文，不泄露 local_path。

5. 官方字段抽取修正
- 更新 `backend/app/services/company_v2_official_field_extractor.py`。
- 支持 PDF 表格标签中的空格，例如 `归属于上市公司股东的净 利润`。
- 支持从附近 `单位：元/万元/亿元` 推断单位。
- 支持 `加权平均净资产收益率（%）`。
- 避免将“扣除非经常性损益的净利润”误当作普通净利润。

6. 历史财务字段对齐
- 更新 `backend/app/datasource/history_financial_provider.py`。
- annual profitability history 中补充 `net_profit_parent`，用于与年报归母净利润字段核验。

7. 前端核验文案
- 更新 `frontend/src/components/company-v2/CompanyV2ReportTimeline.vue`。
- 更新 `frontend/src/components/company-v2/CompanyV2ReportDocuments.vue`。
- 增加 verified / partial / conflict / period mismatch 语义文案。
- period mismatch 显示为“已跳过强核验”，不误导为数据冲突。

8. Live artifact
- 新增/刷新：
  - `backend/docs/artifacts/company_v2_601686_live_discover_phase6tc1.json`
  - `backend/docs/artifacts/company_v2_601686_live_download_phase6tc1.json`
  - `backend/docs/artifacts/company_v2_601686_live_parse_phase6tc1.json`
  - `backend/docs/artifacts/company_v2_601686_live_verify_phase6tc1.json`
  - `backend/docs/artifacts/company_v2_601686_live_verification_summary_phase6tc1.md`
- live report_id = 1。
- structured_period_matched = `2024-12-31`。
- final status = conflict；其中 provider value conflict = 1，field definition mismatch = 1，period mismatch = 0。

9. 测试与构建
- 新增 `backend/tests/fundamental/test_phase6tc1_live_annual_verification_gate.py`。
- 新增 `frontend/src/tests/companyV2LiveOfficialVerification.test.js`。
- 验证结果：
  - `pytest backend/tests/fundamental/test_phase6tc1_live_annual_verification_gate.py -q`：9 passed
  - `pytest -q`：2757 passed, 1 skipped
  - `npm run test`：559 passed
  - `npm run build`：passed

---
下一步：你需要操作

第一步：打开 `backend/docs/artifacts/company_v2_601686_live_verification_summary_phase6tc1.md`，确认 live 核验摘要中 `structured_period_matched` 为 `2024-12-31`。

第二步：对 `revenue` 的 `PROVIDER_VALUE_CONFLICT` 做数据源口径复核，确认 BaoStock annual history 的 `mb_revenue` 与 CNINFO 年报营业收入为何存在差异。

第三步：对 `net_profit_parent` 的 `FIELD_DEFINITION_MISMATCH` 做字段定义复核，避免把净利润、归母净利润、扣非归母净利润混用。

第四步：完成上述口径复核后，再进入 Phase 6T-D：Report RAG Ingestion and QA。
