# Phase 6T-G Update Report

## 修改文件清单

- `backend/app/models/company_v2_financial_evidence_fusion.py`
- `backend/app/services/company_v2_financial_field_definition_registry.py`
- `backend/app/services/company_v2_financial_unit_normalizer.py`
- `backend/app/services/company_v2_financial_evidence_alignment.py`
- `backend/app/services/company_v2_financial_evidence_tolerance.py`
- `backend/app/services/company_v2_official_financial_evidence_resolver.py`
- `backend/app/services/company_v2_financial_evidence_fusion_service.py`
- `backend/app/services/company_v2_official_field_extractor.py`
- `backend/app/routers/company_v2_report_rag.py`
- `backend/scripts/company_v2_financial_evidence_fusion_eval.py`
- `backend/tests/fundamental/test_phase6tg_field_definition_registry.py`
- `backend/tests/fundamental/test_phase6tg_unit_normalizer.py`
- `backend/tests/fundamental/test_phase6tg_evidence_alignment.py`
- `backend/tests/fundamental/test_phase6tg_tolerance.py`
- `backend/tests/fundamental/test_phase6tg_official_evidence_resolver.py`
- `backend/tests/fundamental/test_phase6tg_fusion_service.py`
- `backend/tests/fundamental/test_phase6tg_fusion_api.py`
- `backend/tests/fundamental/test_phase6tg_fusion_safety.py`
- `frontend/src/api/companyV2.js`
- `frontend/src/components/company-v2/CompanyV2ReportDocuments.vue`
- `frontend/src/components/company-v2/reports/CompanyV2FinancialEvidenceFusionPanel.vue`
- `frontend/src/tests/companyV2FinancialEvidenceFusion.test.js`
- `backend/docs/artifacts/company_v2_601686_financial_evidence_fusion_phase6tg.json`
- `backend/docs/artifacts/company_v2_601686_financial_evidence_fusion_eval_phase6tg.json`
- `backend/docs/artifacts/company_v2_601686_financial_evidence_fusion_eval_phase6tg.md`
- `backend/docs/artifacts/company_v2_phase6tg_final_gate.json`
- `backend/docs/artifacts/company_v2_phase6tg_final_gate.md`

## 601686 十字段融合结果

真实样本为 `symbol=601686`, `report_id=1`, `report_year=2024`, `report_type=annual`。

- `revenue`: `definition_mismatch`
- `net_profit`: `verified`
- `net_profit_parent`: `definition_mismatch`
- `operating_cashflow`: `structured_field_missing`
- `total_assets`: `structured_field_missing`
- `equity_parent`: `structured_field_missing`
- `eps_basic`: `structured_field_missing`
- `roe_weighted`: `definition_mismatch`
- `total_share`: `period_basis_mismatch`
- `float_share`: `insufficient_evidence`

## 汇总指标

- `fields_total`: 10
- `verified`: 1
- `normalized_match`: 0
- `likely_match`: 0
- `definition_mismatch`: 3
- `period_basis_mismatch`: 1
- `unit_mismatch`: 0
- `value_conflict`: 0
- `structured_field_missing`: 4
- `official_field_not_found`: 0
- `insufficient_evidence`: 1
- `not_applicable`: 0
- `failed`: 0

## 关键结论

- `verified`: `net_profit`
- `normalized_match`: 无
- `definition_mismatch`: `revenue`, `net_profit_parent`, `roe_weighted`
- `period_mismatch`: `total_share`
- `structured_missing`: `operating_cashflow`, `total_assets`, `equity_parent`, `eps_basic`
- `official_missing`: 无
- `value_conflict`: 无
- `false_conflict_rate`: 0.0
- `citation_accuracy`: 1.0
- `source_trace_completeness`: 1.0

## 评估结果

- `field_resolution_rate`: 1.0
- `verified_precision`: 1.0
- `definition_mismatch_accuracy`: 1.0
- `period_mismatch_accuracy`: 1.0
- `unit_normalization_accuracy`: 1.0
- `false_conflict_rate`: 0.0
- `citation_accuracy`: 1.0
- `source_trace_completeness`: 1.0
- `cross_report_leakage`: 0
- `unsupported_merge_rate`: 0.0

## 测试与构建

- 后端全量测试：`2938 passed, 1 skipped`
- 前端全量测试：`52 passed`, `631 passed`
- 前端构建：成功

## 限制

- 当前融合层只做显式、单报告、单字段的结构化财务与官方报告证据对齐，不覆盖投资建议。
- `total_share` 的 `period_basis_mismatch` 是按官方页码与披露日期语义严格判定，不强行改写为同周期值。
- `float_share` 没有足够官方证据，因此保持 `insufficient_evidence`。

## 回滚

- 可回滚新增 fusion service、resolver、alignment、tolerance、API、前端面板与 eval 脚本。
- 不影响 Phase 6T-D / E3 / F 既有 artifact 和 gate 结论。

## 结论

- `phase6tg_passed = true`
- 建议进入 `Production Fusion Rollout`
