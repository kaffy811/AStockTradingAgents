# Phase 6T-H Update Report

## 修改文件清单

- `backend/app/core/config.py`
- `backend/app/routers/company_v2_report_rag.py`
- `backend/app/routers/company_v2_debug.py`
- `backend/app/services/company_v2_financial_evidence_fusion_service.py`
- `backend/app/services/company_v2_financial_fusion_rollout_service.py`
- `backend/app/services/company_v2_financial_fusion_cache.py`
- `backend/app/services/company_v2_financial_fusion_singleflight.py`
- `backend/app/services/company_v2_financial_fusion_metrics.py`
- `backend/app/services/company_v2_financial_fusion_health_service.py`
- `backend/app/services/company_v2_financial_fusion_circuit_breaker.py`
- `backend/app/services/company_v2_financial_fusion_review_queue.py`
- `backend/scripts/company_v2_financial_fusion_rollout_audit.py`
- `backend/tests/fundamental/test_phase6th_fusion_rollout.py`
- `backend/tests/fundamental/test_phase6th_fusion_cache.py`
- `backend/tests/fundamental/test_phase6th_fusion_singleflight.py`
- `backend/tests/fundamental/test_phase6th_fusion_metrics.py`
- `backend/tests/fundamental/test_phase6th_fusion_health.py`
- `backend/tests/fundamental/test_phase6th_fusion_circuit_breaker.py`
- `backend/tests/fundamental/test_phase6th_fusion_review_queue.py`
- `backend/tests/fundamental/test_phase6th_fusion_admin_api.py`
- `backend/tests/fundamental/test_phase6th_fusion_api.py`
- `backend/tests/fundamental/test_phase6th_fusion_multistock_acceptance.py`
- `backend/tests/fundamental/test_phase6th_fusion_safety.py`
- `frontend/src/api/companyV2.js`
- `frontend/src/components/company-v2/reports/CompanyV2FinancialEvidenceFusionPanel.vue`
- `frontend/src/components/company-v2/reports/CompanyV2FinancialFusionHealthBadge.vue`
- `frontend/src/components/company-v2/reports/CompanyV2FinancialFusionReviewBadge.vue`
- `frontend/src/tests/companyV2FinancialEvidenceFusion.test.js`
- `backend/docs/artifacts/company_v2_financial_fusion_multistock_phase6th.json`
- `backend/docs/artifacts/company_v2_financial_fusion_rollout_audit_phase6th.json`
- `backend/docs/artifacts/company_v2_financial_fusion_rollout_audit_phase6th.md`
- `backend/docs/artifacts/company_v2_phase6th_final_gate.json`
- `backend/docs/artifacts/company_v2_phase6th_final_gate.md`

## Rollout 配置

- `COMPANY_V2_FINANCIAL_FUSION_ENABLED=false`
- `COMPANY_V2_FINANCIAL_FUSION_ROLLOUT_PERCENT=0`
- `COMPANY_V2_FINANCIAL_FUSION_SYMBOL_ALLOWLIST=601686,600519,300750`
- `COMPANY_V2_FINANCIAL_FUSION_AUTO_RUN=false`
- `COMPANY_V2_FINANCIAL_FUSION_MAX_FIELDS_PER_REQUEST=10`
- `COMPANY_V2_FINANCIAL_FUSION_TIMEOUT_SECONDS=60`
- `COMPANY_V2_FINANCIAL_FUSION_CACHE_TTL_SECONDS=86400`

## Stage 1 / Stage 2 多股票结果

Stage 1 allowlist:
- `601686`

Stage 2 allowlist:
- `601686,600519,300750,000725,000001`

真实回退样本仅对 `601686` 具备可运行的本地已验证报告与 page sidecar，因此：

- `601686`: `eligible=true`, `reason=ALLOWLIST`, `final_status=passed`
- `600519`: `eligible=false`, 仍保持非自动运行
- `300750`: `eligible=false`, 仍保持非自动运行
- `000725`: `eligible=false`, 仍保持非自动运行
- `000001`: `eligible=false`, 仍保持非自动运行

## 监控与缓存

- `cache_hit_rate`: 1.0
- `singleflight_status`: `completed` / `reused`
- `false_conflict`: 0
- `cross_report_leakage`: 0
- `missing_citation`: 0
- `incomplete_source_trace`: 0
- `circuit_state`: `closed`

## 生产健康

- `p50_latency_ms`: 0.0
- `p95_latency_ms`: 0.0
- `review_queue_size`: 0
- `timeout_rate`: 0.0

## 四个 gate

- rollout control: pass
- cache idempotency: pass
- singleflight: pass
- monitoring / health / circuit / safety: pass

## 测试与构建

- 后端全量测试：`2952 passed, 1 skipped`
- 前端全量测试：`52 passed`, `631 passed`
- 前端构建：成功

## 限制

- 默认关闭，`auto_run=false`。
- 不自动索引，不自动下载，不覆盖结构化图表。
- 目前 rollout 只做 Stage 1 / Stage 2 的受控验收，不扩展到全市场自动融合。

## 回滚

- 可通过环境变量立即关闭 `COMPANY_V2_FINANCIAL_FUSION_ENABLED`。
- `circuit reset` 仅用于人工恢复，不会删除既有 fusion 记录。

## 结论

- `phase6th_passed = true`
- 推荐：`proceed_stage_1`
