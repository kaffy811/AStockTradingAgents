---
目前完成的工作汇总：

已完成

1. `backend/app/services/company_v2_data_validation_engine.py`
- 完成 Phase 6Q-1 财务公式语义校准。
- 为 validation check 增加 `check_strength`、`tags`、`formula_context`。
- 将 Dupont provider-defined 口径差异和净利率 context 不完整从 data failure 校准为 semantic warning。
- 保留 expected / actual / relative_diff_pct / evidence，不隐藏问题。

2. `backend/app/services/company_v2_debug_service.py`
- Field Metadata 和 field_trace 增加 `formula_context`。
- 新 debug 响应可追踪 period、report_period_type、value_basis、provider_definition、source_module、raw_field。

3. `backend/scripts/validate_company_v2_artifacts.py`
- CLI 汇总新增 `strong_failed_count`、`weak_warning_count`、`semantic_warning_count`、`skipped_due_to_context_count`、`formula_context_missing_count`。
- 生成 `company_v2_validation_summary_phase6q1.json/md`。
- 生成 `company_v2_formula_semantics_audit.json/md`。

4. 前端 CompanyV2 Data Quality UI
- `CompanyV2DebugPanel.vue` 和 `CompanyV2Section.vue` 增加 weak formula / Dupont provider-defined / net margin context 文案。
- 文案明确为数据质量和口径提示，不输出交易建议。

5. 测试与验收
- 新增 `backend/tests/fundamental/test_phase6q1_formula_semantics_calibration.py`。
- 新增 `frontend/src/tests/companyV2FormulaSemantics.test.js`。
- `pytest -q`：2614 passed, 1 skipped。
- `npm run test`：481 passed。
- `npm run build`：passed。

---
下一步：你需要操作

第一步：查看 `backend/docs/artifacts/company_v2_validation_summary_phase6q1.md` 确认三股票已从 fail 校准为 warning。
第二步：查看 `backend/docs/artifacts/company_v2_formula_semantics_audit.md` 复核 Dupont 和净利率口径差异。
第三步：如接受 semantic warning 语义，可进入 Phase 6R：CompanyV2 Production Cutover Monitoring。
