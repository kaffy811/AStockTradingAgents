---
目前完成的工作汇总：

已完成

1. CompanyV2 年报 PDF 下载服务
- 新增 `backend/app/services/company_v2_report_pdf_service.py`。
- 只允许 CNINFO HTTPS PDF URL，阻断 `file://`、localhost、内网地址、非 PDF、非白名单 host。
- 下载后计算 SHA-256、文件大小、页数，内部保存 `local_path`，API 返回中不泄露本地路径。

2. CompanyV2 PDF 文本解析服务
- 新增 `backend/app/services/company_v2_pdf_text_parser.py`。
- 使用 `pypdf` 优先、`pdfminer.six` 兜底，输出 page-level text 的内部解析结果。
- Debug/API 只返回摘要与 excerpt，不把 PDF 全文塞进前端响应。

3. 官方披露字段抽取与核验
- 新增 `backend/app/services/company_v2_official_field_extractor.py`。
- 新增 `backend/app/services/company_v2_official_verification_service.py`。
- 支持抽取营业收入、归母净利润、净利润、经营活动现金流量净额、总资产、归母净资产、基本每股收益、加权 ROE、总股本、流通股本。
- 支持元、万元、亿元、股、万股、亿股与百分比单位归一。
- 结构化字段核验支持金额、EPS、比率、股本差异阈值，并输出 verified / conflict / unverified。

4. Accuracy Audit 官方核验分级
- 更新 `backend/app/services/company_v2_accuracy_audit_service.py`。
- 新增 official disclosure verified / conflict / found but unparsed 等来源分级。
- 保持 BaoStock/AkShare 等公开源不伪装成官方核验来源。

5. Report API 与前端核验展示
- 更新 `backend/app/routers/company_v2_debug.py`，新增下载、解析、核验与查询核验结果 API。
- 更新 `frontend/src/api/companyV2.js`。
- 更新 `CompanyV2ReportDocuments.vue`、`CompanyV2ReportTimeline.vue`、`CompanyV2MetricCards.vue`、`CompanyV2Section.vue`。
- 报告时间线显示 PDF discovered/downloaded/parsed/verified 状态，字段卡展示 CNINFO verified / Public provider / Computed / Unverified / Conflict badge。

6. 601686 真实 CNINFO 年报 artifact
- 已下载并解析 601686 2024 年报 PDF。
- 已保存：
  - `backend/docs/artifacts/company_v2_601686_pdf_download_phase6tc.json`
  - `backend/docs/artifacts/company_v2_601686_pdf_parse_phase6tc.json`
  - `backend/docs/artifacts/company_v2_601686_official_fields_phase6tc.json`
  - `backend/docs/artifacts/company_v2_601686_official_verification_phase6tc.json`
- 解析结果：PDF 265 页，文本解析状态 parsed，抽取到 revenue、net_profit_parent、net_profit、operating_cashflow、total_assets、eps_basic、total_share。

7. 测试与构建
- 新增后端测试：
  - `backend/tests/fundamental/test_phase6tc_pdf_download_parse.py`
  - `backend/tests/fundamental/test_phase6tc_official_field_extraction.py`
  - `backend/tests/fundamental/test_phase6tc_official_verification.py`
- 新增前端测试：
  - `frontend/src/tests/companyV2OfficialVerification.test.js`
- 验证结果：
  - `pytest -q`：2745 passed, 1 skipped
  - `npm run test`：553 passed
  - `npm run build`：passed

---
下一步：你需要操作

第一步：如需在数据库环境启用 PDF 页数持久化，执行 Alembic migration：`backend/alembic/versions/2026_07_10_0001-i6j7k8l9m0n1_add_report_document_page_count.py`。

第二步：在真实页面打开 `/stocks/CN/601686`，进入报告文件模块，验证 2024 年报显示 PDF 状态、解析按钮、核验结果入口和字段 source badge。

第三步：进入 Phase 6T-D 前，建议先补强“按 report_year 匹配历史财务行”的真实 API 验收，避免用最新一期结构化字段与 2024 年报字段直接比较导致 period mismatch conflict。
