---
目前完成的工作汇总：

已完成

1. `backend/docs/artifacts/company_v2_production_monitoring_plan.md`
- 新增 CompanyV2 production monitoring 指标设计。
- 覆盖 API Health、Provider Health、Render Health、Data Quality Health、Frontend Runtime Health。
- 明确 p95、error_rate、modules_renderable、data_quality_score、strong failures、semantic warnings 等阈值。

2. `backend/app/core/structured_debug_logger.py` / `backend/app/services/company_v2_debug_service.py`
- 新增 `log_company_v2_event()`。
- CompanyV2 debug/full 完成后输出 `company_v2_debug_full_completed` 生产监控事件。
- 日志事件包含 request_id、providers_data_success、modules_renderable、coverage_avg、validation_status、data_quality_score、strong_failed_count、semantic_warning_count。

3. `backend/scripts/company_v2_production_smoke_test.py`
- 新增 production smoke gate CLI。
- 支持 `--base-url` 真实 API 和本地 artifact fallback。
- 已生成 `backend/docs/artifacts/company_v2_production_smoke_summary.json/md`。

4. `backend/scripts/company_v2_daily_health_snapshot.py`
- 新增 daily health snapshot CLI。
- 输出每日三股票健康汇总。
- 已生成 `backend/docs/artifacts/company_v2_daily_health_20260709.json/md`。

5. `backend/docs/artifacts/company_v2_production_cutover_monitoring_checklist.md`
- 新增 production cutover checklist。
- 包含 pre-cutover、cutover、post-cutover、rollback triggers、rollback steps。

6. 前端 Production Health Summary
- `frontend/src/components/company-v2/CompanyV2DebugPanel.vue` 增加生产健康汇总。
- 展示 providers_data_success、modules_renderable、coverage_avg、validation_status、data_quality_score、strong_failed_count、semantic_warning_count、cache_hit_count、fallback_to_legacy_count。

7. 测试与验收
- 新增 `backend/tests/fundamental/test_phase6r_production_cutover_monitoring.py`。
- 新增 `frontend/src/tests/companyV2ProductionMonitoring.test.js`。
- `pytest -q`：2622 passed, 1 skipped。
- `npm run test`：484 passed。
- `npm run build`：passed。

---
下一步：你需要操作

第一步：生产切换前执行 `python backend/scripts/company_v2_production_smoke_test.py --base-url <prod-url> --symbols 600519,000725,601686 --market CN --include-raw false --force-refresh false`。
第二步：确认 `backend/docs/artifacts/company_v2_production_cutover_monitoring_checklist.md` 中 rollback 配置已就绪。
第三步：如 smoke gate 通过，可进入 Phase 6S：Production Staged Cutover；legacy 继续保留。
