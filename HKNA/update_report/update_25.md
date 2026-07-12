# Update 25 - Phase 6T-I Stage 1 Controlled Pilot and Report Readiness Expansion

## 修改文件

- `backend/app/services/company_v2_financial_fusion_metrics.py`
- `backend/app/services/company_v2_financial_fusion_health_service.py`
- `backend/app/services/company_v2_financial_evidence_fusion_service.py`
- `backend/app/services/company_v2_financial_fusion_cache.py`
- `backend/app/services/company_v2_financial_fusion_report_readiness.py`
- `backend/app/routers/company_v2_financial_fusion.py`
- `backend/app/main.py`
- `backend/.env.example`
- `backend/scripts/company_v2_financial_fusion_stage1_pilot.py`
- `backend/tests/fundamental/test_phase6ti_cache_key_normalization.py`
- `backend/tests/fundamental/test_phase6ti_latency_metrics.py`
- `backend/tests/fundamental/test_phase6ti_report_readiness.py`
- `backend/tests/fundamental/test_phase6ti_prepare_step_api.py`
- `backend/tests/fundamental/test_phase6ti_singleflight_observation.py`
- `backend/tests/fundamental/test_phase6ti_stage1_safety.py`
- `backend/tests/fundamental/test_phase6ti_stage1_pilot.py`
- `backend/tests/fundamental/test_phase6th_fusion_health.py`
- `frontend/src/api/companyV2.js`
- `frontend/src/components/company-v2/reports/CompanyV2FinancialEvidenceFusionPanel.vue`
- `frontend/src/tests/companyV2FinancialFusionStage1.test.js`

## Stage 1 Pilot

- 601686 only, allowlist mode
- cold run: `elapsed_ms=43.25`
- warm run: `elapsed_ms=0.39`
- latency sample count: `12`
- p50 latency: `24.84 ms`
- p95 latency: `43.23 ms`
- cache hit rate: `1.0`
- singleflight reused: `2`
- circuit state: `closed`
- safety metrics:
  - false_conflict: `0`
  - cross_report_leakage: `0`
  - missing_citation: `0`
  - incomplete_source_trace: `0`

## Stage 2 Readiness

- `601686`: `ready`
- `600519`: `pdf_not_downloaded`
- `300750`: `pdf_not_downloaded`
- `000725`: `pdf_not_downloaded`
- `000001`: `pdf_not_downloaded`

## Gate Outcome

- `phase6ti_passed=true`
- `stage1_status=ready`
- `stage2_status=partially_ready`
- `recommendation_for_production_fusion_rollout=continue_stage_1`

## Notes

- Zero-sample latency now returns `null` / `insufficient_data` rather than `0.0`.
- Readiness and prepare-step APIs are explicit and manual-only.
- Stage 2 remains partially ready; no rollout beyond Stage 1.
