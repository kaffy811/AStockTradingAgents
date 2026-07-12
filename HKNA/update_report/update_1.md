---
目前完成的工作汇总：

已完成

1. CompanyV2 页面替换 Gate
- 在 `frontend/src/views/StockDetailView.vue` 增加 `VITE_COMPANY_TAB_VERSION=legacy|v2` 支持。
- `company_v2=1` 继续进入 CompanyV2 full-page；`company_v2=0` 强制 legacy。
- `VITE_COMPANY_TAB_VERSION=v2` 仅替换公司 Tab，不影响顶部、K 线、新闻、同行业和历史报告 Tab。

2. CompanyV2 滚动与页面验收
- 在 `frontend/src/views/CompanyV2View.vue` 增加 `data-testid="company-v2-bottom-sentinel"`。
- 保持 body/main 作为主滚动路径，未新增纵向嵌套滚动容器。
- RawJsonDrawer 仍为 inline 展开，不锁定 body overflow。

3. CompanyV2 Debug 文案与展示
- 在 `frontend/src/components/company-v2/CompanyV2DebugPanel.vue` 显示 `baostock_aggregate_calls`。
- 使用结构化诊断文案替代旧泛化 DATA_MODE 文案。
- 恢复 legacy DataSourceBanner auth 文案以满足既有测试契约。

4. CompanyV2 full API 稳定性修复
- 在 `backend/app/services/company_v2_debug_service.py` 复用 quote_overview 数据给 valuation，避免重复 provider 调用耗尽 full 预算。
- 为财务模块增加 BaoStock provider timeout 的模块级 grace，避免外层 module timeout 抢先吞掉 provider envelope。
- 版本化 module/full snapshot cache key，隔离旧的 bad snapshot。
- summary 增加逻辑 `baostock_aggregate_calls`，cache 命中时仍能看到 aggregate 来源。

5. 验收报告与测试
- 新增 `backend/tests/fundamental/test_phase6o3_company_v2_replacement_gate.py`。
- 新增 `frontend/src/tests/companyV2Gate.test.js`。
- 新增验收文档 `backend/docs/artifacts/company_v2_page_acceptance_report.md`。
- 已运行：`pytest -q`、`npm run test`、`npm run build`，均通过。

---
下一步：你需要操作

第一步：本地浏览器打开 `/stocks/CN/600519?company_v2=1`、`/stocks/CN/000725?company_v2=1`、`/stocks/CN/601686?company_v2=1`，人工确认底部 sentinel 可见且 RawJsonDrawer 展开/关闭后仍可滚动到底。
第二步：如人工验收无 console error，可在测试环境设置 `VITE_COMPANY_TAB_VERSION=v2`，仅将 Company Tab 默认切到 CompanyV2。
第三步：保留 legacy Company Tab 一轮灰度；确认无回退需求后进入 Phase 6O-4 替换旧 Company Tab。
