---
目前完成的工作汇总：

已完成

1. Legacy Company Tab 下线计划文档
- 新增 `backend/docs/artifacts/company_v2_legacy_inventory.md`。
- 盘点 legacy Company Tab 入口、旧 panels、DataSourceBanner、adapter、API client、legacy routes/tools/tests/docs/flags。
- 每类文件标注 `keep`、`freeze`、`deprecate_later`、`remove_after_prod_cutover` 等状态。

2. Legacy freeze policy 与 production rollout gate
- 新增 `backend/docs/artifacts/company_v2_legacy_deprecation_plan.md`。
- 明确 legacy 冻结策略：只修安全、崩溃、严重回退问题；新功能只进入 CompanyV2。
- 新增 `backend/docs/artifacts/company_v2_production_rollout_gate.md`。
- 明确 production 切换条件、rollback 步骤和 incident checklist。

3. Rollback 与测试命令清理
- 更新 `backend/docs/artifacts/company_v2_staged_rollout.md`，补充 production gate、known limitations 和合规声明。
- 新增 `backend/docs/artifacts/company_v2_test_commands.md`，标准化 backend/frontend/build/e2e 命令。
- 新增根目录 `pytest.ini`，默认只收集 `backend/tests`，避免旧 `test_stock_detail.py` 被 root pytest 误收集。
- 新增 `backend/tests/conftest.py`，隔离测试 CORS 默认值，避免 root cwd 读取部署 `.env` 后造成 CORS 测试误报。

4. 旧 DATA_MODE 文案处理
- `backend/app/tools/fundamental/base.py` 中旧泛化 DATA_MODE 文案保留在 legacy 路径，但标注 deprecated。
- CompanyV2 UI/service/test 覆盖确认不包含旧泛化 DATA_MODE 文案。

5. CompanyV2 fallback legacy 安全阀
- `frontend/src/views/CompanyV2View.vue`：加载失败时 emit `load-error`。
- `frontend/src/views/StockDetailView.vue`：嵌入式 CompanyV2 加载失败时回退 legacy CompanyFundamentalsPanel。
- 显式 `company_v2=1` full-page debug 仍保留，不吞掉错误，方便诊断。

6. Phase 6O-6 测试
- 新增 `backend/tests/fundamental/test_phase6o6_legacy_deprecation_plan.py`。
- 新增 `frontend/src/tests/companyV2RolloutGate.test.js`。
- 验证 root `pytest -q` 不再因旧 Playwright/import path 误报失败。

---
下一步：你需要操作

第一步：若准备生产切换，先按 `backend/docs/artifacts/company_v2_production_rollout_gate.md` 完成 staging/browser gate。
第二步：生产切换仅设置 `VITE_COMPANY_TAB_VERSION=v2` 并重建前端；保留 `company_v2=0` 作为运行时回退。
第三步：如出现生产问题，设置 `VITE_COMPANY_TAB_VERSION=legacy` 回滚，不删除 CompanyV2 cache，保留 debug snapshots。
第四步：生产稳定一个完整回归周期后，再进入 Phase 6O-7：Production Config Cutover Preparation。
