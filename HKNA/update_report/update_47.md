---
目前完成的工作汇总：

已完成

1. Company V2 页面生命周期修复
- 修改 `frontend/src/views/CompanyV2View.vue` 与 `frontend/src/views/StockDetailView.vue`。
- 引入 `market:symbol:period:schemaVersion` 页面缓存、monotonic request id、AbortController 和 keep-alive activated 恢复逻辑。
- 路由切换、快速切换、返回公司 tab 时会重置视图状态并重新加载；旧响应不会覆盖新 symbol。
- StockDetail 当前停留在公司 tab 时，切换股票后自动保持 Company V2 已访问状态，不再需要重复点击 tab。

2. 公司概览真正接入
- 修改 `backend/app/services/company_v2_stock_basic_service.py` 与 `frontend/src/components/company-v2/CompanyV2CompanyProfileCard.vue`。
- 使用 `ak.stock_profile_cninfo` 获取巨潮公司概况，合并公司全称、简称、交易所、行业、上市日期、注册地址/办公地址、主营业务、经营范围和机构简介。
- 普通页面不显示 provider/source；debug 保留 metadata。
- 长文本默认 4 行截断，支持展开/收起。

3. 普通页面内部信息隐藏
- 修改 `frontend/src/components/company-v2/CompanyV2Section.vue`、`CompanyV2MetricCards.vue`、`CompanyV2StockBasicCard.vue`。
- 普通模式映射内部状态枚举为中文业务状态，不显示 `OK_WITH_FALLBACK`、`LOW_COVERAGE`、`REPORT_PDF_NOT_FOUND` 等字面量。
- 普通模式隐藏 raw table；行情概览只保留最新价、涨跌幅、换手率、总市值，估值字段留在估值模块。
- coverage 数值仅 debug 模式展示；普通模式使用统一完整性标签。

4. 报告状态机收口
- 修改 `backend/app/routers/company_v2_debug.py`、`CompanyV2ReportDocuments.vue`、`CompanyV2ReportTimeline.vue`。
- `/reports` persisted-first，新增兼容 `summary`、`report_status`、`view_state`，summary/list 来自同一 persisted reports 列表。
- 前端状态机覆盖 `idle`、`loading_persisted`、`persisted_found`、`discovering`、`discovered`、`empty`、`error` 等页面状态。
- 普通页面展示中文报告状态、加载态、空态、错误态和“手动添加官方 PDF 链接”；手动链接继续使用 CNINFO/官方白名单校验并入库。

5. 现金流异常图处理
- 修改 `frontend/src/components/company-v2/charts/CompanyV2CashflowQualityChart.vue`。
- 对经营现金流/净利润序列识别极端点，图表使用对称对数尺度展示并标注异常点。
- 原始值不裁剪；tooltip 保留原始百分比。

6. 测试与验收
- 新增 `backend/tests/fundamental/test_phase6u_d3_company_v2_lifecycle.py`。
- 新增 `frontend/src/tests/companyV2Phase6UD3Lifecycle.test.js`。
- 验证结果：backend full `3178 passed, 1 skipped`；frontend vitest `653 passed`；`npm run build` 通过。
- 真实探针确认 000725、600519、688549 公司概览来自 CNINFO；000725/600519 annual history 四个核心模块均为 19 点；600519 report_id=2 persisted 且可分析；688549 已有 2025/2024/2023 年报。

---
下一步：你需要操作

第一步：打开 `/stocks/CN/000725`，按“公司 tab -> 其他 tab -> 公司 tab”和“000725 -> 688549 -> 000725”手工确认模块不消失。

第二步：打开 `/stocks/CN/600519`，确认公司概览、report_id=2、官方 PDF 和“分析此报告”入口。

第三步：提交建议使用 `fix(company-v2): stabilize page lifecycle and unify report states`。
