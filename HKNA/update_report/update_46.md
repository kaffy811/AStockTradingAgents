---
目前完成的工作汇总：

已完成

1. Company V2 页面产品化
- 修改 `frontend/src/views/CompanyV2View.vue` 与 `frontend/src/components/company-v2/*`。
- 默认隐藏 Debug、JSON、provider、schema、cache、coverage、内部字段 key 和管理按钮。
- 仅在 `VITE_COMPANY_V2_DEBUG=true` 或开发环境 `?debug=1` 时展示完整 diagnostics。
- 顶部行情摘要移除 PE/PB/PS/PCF，避免与估值模块重复。

2. 财务字段语义集中化
- 新增 `backend/app/services/company_v2_field_metadata.py`。
- 修改 `backend/app/services/company_v2_formatter_registry.py`。
- 将 percentage_fraction、percentage_points、ratio、multiple、currency 等单位规则集中到 metadata，禁止按数值大小猜测百分比。
- API formatter 增量提供 `raw_value`、`normalized_value`、`display_value`、`unit`、`semantic_type`，不删除旧字段。

3. BaoStock 历史覆盖与缓存升级
- 修改 `backend/app/datasource/history_financial_provider.py`、`backend/app/datasource/baostock_client.py`、`backend/app/services/company_v2_history_service.py`、`backend/app/services/company_v2_debug_service.py`。
- 将旧 history/cache key 升级到 Phase 6U-D2 版本，避免继续命中旧单点缓存。
- 年度 history 按 period 升序输出，latest 使用最后一期；000725 annual growth/operation/cashflow/dupont 均确认有 19 个 provider-backed 年度点。

4. 现金流和杜邦语义修复
- `CFOToGr` 与 `CFOToOR` 在 000725 样本中等值，普通页面只展示 `经营现金/收入`，`cashflow_revenue_ratio` 作为 alias 保留。
- `CFOToNP` 异常高值不裁剪，增加 `CFO_TO_NP_DENOMINATOR_SENSITIVE` warning。
- 确认 `dupontPnitoni` 不是销售净利率，改为 `dupont_net_profit_factor`；杜邦净利率使用 `dupontPnitoni * dupontNitogr`。
- 增加杜邦公式校验， mismatch 时输出 `DUPONT_FORMULA_MISMATCH` 并降级页面拆解。

5. 报告列表自动加载
- 修改 `backend/app/routers/company_v2_debug.py` 与 `CompanyV2ReportDocuments.vue`。
- `/reports` 先返回已持久化 `report_documents`；前端加载后自动请求列表，空列表时后台幂等触发 discover，再刷新。
- 普通用户隐藏强制刷新、手工 URL、索引管理、证据融合等入口。

6. 测试与验收
- 新增 `backend/tests/fundamental/test_phase6u_d2_company_v2_productization.py`。
- 新增 `frontend/src/tests/companyV2Phase6UD2Productization.test.js`。
- 更新旧语义测试，覆盖百分比单位、现金流 alias、杜邦 match/mismatch、报告自动加载、Debug gating 和页面去重。
- 验证结果：后端 full pytest `3173 passed, 1 skipped`；前端 vitest `644 passed`；`npm run build` 通过。

---
下一步：你需要操作

第一步：本地打开 `/stocks/CN/000725` 和 `/stocks/CN/600519` 做一次浏览器人工验收，确认普通模式无 Debug 信息、报告自动展示、估值不重复。

第二步：如需查看诊断结构，在开发环境使用 `?debug=1` 或设置 `VITE_COMPANY_V2_DEBUG=true` 后重新构建前端。

第三步：提交建议使用 `fix(company-v2): productize company page and correct financial semantics`。
