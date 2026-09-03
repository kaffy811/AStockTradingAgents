---
目前完成的工作汇总：

已完成

1. CompanyV2 Formatter Registry
- 新增 `backend/app/services/company_v2_formatter_registry.py`。
- 统一处理 price、percent、ratio、money、shares、integer 等展示格式。
- 修复 numeric `raw_value` 有值但 `display_value` 为 `—` 的问题，0 仍作为有效值展示。

2. CompanyV2 Computed Field Registry
- 新增 `backend/app/services/company_v2_computed_field_registry.py`。
- 统一计算 `market_cap`、`float_market_cap`、`pct_chg` 等字段。
- 支持从 CompanyV2 full context 中复用同一股票的 share capital，不跨股票复用。

3. DebugEnvelope 2.0 元数据
- 更新 `backend/app/schemas/company_v2_debug.py`。
- 增加 `schema_version`、`schema_features`、`field_trace`、`coverage`、`provider_summary`、`agent_summary`。
- `source_chain` 增加 `data_success`，区分 wrapper 成功与业务数据成功。

4. CompanyV2 Debug Service 数据质量修复
- 更新 `backend/app/services/company_v2_debug_service.py`。
- 修复 AkShare wrapper success 但业务失败时误判实时价的问题。
- BaoStock 历史 K 线 fallback 标记为 `price_is_realtime=false`、`price_label=最近收盘价`。
- 增加 field metadata、field_trace、coverage、provider_summary、agent_summary 生成逻辑。
- 修复 report_documents / report_rag 0-count 状态机，0 可见但不作为 OK 或 filled field。

5. Diagnosis 多标签化
- 更新 `backend/app/services/company_v2_debug_diagnosis_service.py`。
- 增加 coverage 驱动的 `OK_WITH_FALLBACK`、`PARTIAL_DATA`、`LOW_COVERAGE`、`VERY_LOW_COVERAGE` 等标签。
- 增加 `TRACE_MISSING`、`PRICE_HISTORICAL_FALLBACK`、`REALTIME_PRICE_UNAVAILABLE` 等诊断标签。

6. CompanyV2 前端数据质量展示
- 更新 `frontend/src/components/company-v2/CompanyV2MetricCards.vue`、`CompanyV2FallbackTable.vue`、`CompanyV2Section.vue`、`CompanyV2DebugPanel.vue`。
- 卡片和表格优先展示后端 `display_value`，tooltip/debug 保留 `raw_value`、provider、raw_field、computed_formula。
- 页面展示 coverage badge、diagnosis tags、provider_summary、field_trace。

7. Phase 6P 测试与 JSON artifacts
- 新增 `backend/tests/fundamental/test_phase6p_company_v2_data_quality.py`。
- 新增 `frontend/src/tests/companyV2DataQuality.test.js`。
- 生成 `backend/docs/artifacts/company_v2_debug_full_600519_phase6p.json`、`company_v2_debug_full_000725_phase6p.json`、`company_v2_debug_full_601686_phase6p.json`。
- 当前本地网络/provider 环境下 BaoStock socket 与公告检索不可用，artifact 保留 structured error 与低 coverage 诊断。

---
下一步：你需要操作

第一步：在正常 dev/staging provider 网络环境重新调用 `/api/v2/company/CN/{symbol}/debug/full?include_raw=true&force_refresh=true`，覆盖 Phase 6P 三股票 JSON artifact。
第二步：核对 `provider_summary.providers_data_success`、`coverage.coverage_pct`、`field_trace` 与前端实际展示是否一致。
第三步：如果正常环境下 `modules_renderable >= 9` 且 provider timeout 为 0，再进入 Phase 6Q：CompanyV2 Data Validation Engine。
