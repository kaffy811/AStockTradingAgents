---
目前完成的工作汇总：

已完成

1. `backend/docs/artifacts/company_v2_production_staged_cutover.md`
- 新增 Phase 6S production staged cutover 文档。
- 明确 legacy/v2/env/query 配置优先级。
- 定义 Level 0 到 Level 4 rollout 分级，本阶段目标为 Level 3。

2. Phase 6S gate / rollback / observation 文档
- 新增 `company_v2_phase6s_pre_cutover_gate.md`。
- 新增 `company_v2_phase6s_post_cutover_smoke.md`。
- 新增 `company_v2_phase6s_rollback_verification.md`。
- 新增 `company_v2_phase6s_observation_window.md`。

3. `backend/scripts/company_v2_cutover_readiness_check.py`
- 新增 production cutover readiness check CLI。
- 读取 smoke/daily artifacts。
- 输出 `company_v2_cutover_readiness_report.json/md`。
- 当前报告：`cutover_ready=true`，推荐 Level 3 production default v2。

4. `frontend/src/components/company-v2/CompanyV2DebugPanel.vue`
- Production Health Summary 中增加 Company Tab Version、Rollback、Schema Version。
- 显示 `company_v2=0` 回退提示和 semantic warning count。
- 不影响 legacy。

5. 测试与验收
- 新增 `backend/tests/fundamental/test_phase6s_production_staged_cutover.py`。
- 新增 `frontend/src/tests/companyV2StagedCutover.test.js`。
- `pytest -q`：2628 passed, 1 skipped。
- `npm run test`：487 passed。
- `npm run build`：passed。

---
下一步：你需要操作

第一步：如果准备切 production，设置 `VITE_COMPANY_TAB_VERSION=v2`。
第二步：build/deploy 前端。
第三步：部署后立即运行 post-cutover smoke，并验证 `/stocks/CN/600519?company_v2=0` 可回 legacy。
第四步：进入 Phase 6T：Post-Cutover Observation，观察 24-48 小时。
