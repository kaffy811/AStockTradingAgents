# Update 27 - Phase 6T-K Stage 2 Manual Rollout

## 本次更新概览

Phase 6T-K 已完成 Stage 2 allowlist/manual trigger/async job/API/frontend/job persistence/profile/soak 的实现与验证，但 final gate 未通过，当前推荐 `hold`。

## 主要变更

- 新增 DB-backed `CompanyV2FinancialFusionJobService` 与 `company_v2_financial_fusion_jobs` 持久化表。
- 新增 financial fusion job API：create/status/result/cancel。
- 前端官方证据核验改为用户点击后创建 job，页面加载不触发 fusion/RAG/LLM/extractor。
- 新增 Stage 2 allowlist 配置模板，不修改真实生产 `.env`。
- 新增真实 profile/soak/job audit artifacts。

## 真实验证结果

- Backend targeted：23 passed。
- Backend full：3044 passed。
- Frontend tests：55 files / 638 tests passed。
- Frontend build：passed。
- Soak requests_total：65。
- Singleflight：reused=10，all_results_equal=True。
- Warm p95：10569.73 ms。
- Job create p95：9698.44 ms。

## Gate 结论

`phase6tk_passed=false`，`stage2_rollout_status=hold`，`recommendation_for_next_step=hold`。

阻塞项：

- warm_result_p95_ms 超过 1500ms。
- job_create_p95_ms 超过 1000ms。
- 601686 当前 RAG_NOT_INDEXED，不能完成真实 job cancel soak。
- cancel soak 完成 4/5。

## 后续建议

先优化 job create 的轻量化 readiness/cache 路径和 warm result path，再补齐 601686 RAG readiness，重新运行 Phase 6T-K soak gate。
