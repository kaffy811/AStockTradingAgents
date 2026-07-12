---
目前完成的工作汇总：

已完成

1. Production cutover 配置文档
- 更新 `.env.example`，补充 CompanyV2 dev/staging、production legacy、production gray cutover 和 URL override 说明。
- 更新 `backend/docs/artifacts/company_v2_staged_rollout.md`，明确配置优先级和一行 rollback 配置。
- 保持 `frontend/.env.example` 为 dev/staging v2，`frontend/.env.production.example` 为 production legacy。

2. CompanyV2 生产监控计划
- 新增 `backend/docs/artifacts/company_v2_monitoring_plan.md`。
- 定义前端 render success、fallback-to-legacy、console error、scroll sentinel、RawJsonDrawer、forbidden legacy 文案等指标。
- 定义后端 debug/full latency、providers_timeout、modules_renderable、baostock_aggregate_calls、cache、report/RAG、mapping/render error 等指标。
- `backend/app/services/company_v2_debug_service.py` summary 新增监控计数字段。

3. 生产回退与 cutover checklist
- 新增 `backend/docs/artifacts/company_v2_production_rollback_checklist.md`。
- 新增 `backend/docs/artifacts/company_v2_production_cutover_checklist.md`。
- 明确回退条件、回退步骤、incident report 字段、pre-cutover/cutover/post-cutover 检查项。

4. 真实浏览器验收记录
- 新增/更新 `backend/docs/artifacts/company_v2_production_cutover_manual_acceptance.md`。
- Browser runtime 返回无可用浏览器，记录为 browser acceptance blocked。
- 使用本地 debug/full API 做 smoke：600519/000725/601686 均 200，但当前本地环境未达到 production cutover gate，文档中明确标记 not passed。

5. Phase 6O-7 测试
- 新增 `backend/tests/fundamental/test_phase6o7_production_cutover_preparation.py`。
- 新增 `frontend/src/tests/companyV2ProductionCutover.test.js`。
- 覆盖生产默认 legacy、dev/staging 默认 v2、URL override、fallback legacy、监控字段、rollback/cutover/manual acceptance 文档、敏感信息与旧 DATA_MODE 文案扫描。

---
下一步：你需要操作

第一步：在真实 dev/staging 浏览器环境完成 `backend/docs/artifacts/company_v2_production_cutover_manual_acceptance.md` 中仍 blocked 的浏览器项。
第二步：确认三个代表股票在正常 provider/network 环境下 `modules_renderable >= 10` 且 `providers_timeout=0` 或有 stale fallback。
第三步：满足 `backend/docs/artifacts/company_v2_production_cutover_checklist.md` 后，才进入 Phase 6O-8：Production Staged Cutover。
第四步：切换前继续保留 legacy，生产回退仍使用 `VITE_COMPANY_TAB_VERSION=legacy` 或 `company_v2=0`。
