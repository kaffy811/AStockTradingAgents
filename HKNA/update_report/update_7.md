---
目前完成的工作汇总：

已完成

1. `backend/app/services/company_v2_data_validation_engine.py`
- 新增 CompanyV2 Data Validation Engine。
- 支持市值公式、流通市值约束、杜邦公式、利润率一致性、估值 sanity、偿债/营运/现金流 sanity、多 provider 冲突检查。
- 输出 `validation_summary`、`validation_checks` 和 `data_quality_score`。

2. `backend/app/services/company_v2_debug_service.py` / `backend/app/schemas/company_v2_debug.py`
- DebugEnvelope 增加 `validation_summary` 和 `validation_checks`。
- `schema_features` 增加 `data_validation_engine`。
- module/full 响应注入 validation 结果，并同步写入 `agent_summary`。

3. `backend/scripts/validate_company_v2_artifacts.py`
- 新增 artifact 离线校验 CLI。
- 已生成 `backend/docs/artifacts/company_v2_validation_summary.json` 和 `backend/docs/artifacts/company_v2_validation_summary.md`。

4. `frontend/src/components/company-v2/CompanyV2DebugPanel.vue` / `CompanyV2Section.vue`
- 增加 Data Quality 区块。
- 展示质量分、状态、检查数量、warning/fail 数量和可展开 validation checks。
- 兼容缺少 validation 字段的旧 schema。

5. 测试
- 新增 `backend/tests/fundamental/test_phase6q_data_validation_engine.py`。
- 新增 `frontend/src/tests/companyV2DataValidation.test.js`。
- `pytest -q`：2605 passed, 1 skipped。
- `npm run test`：477 passed。
- `npm run build`：passed。

---
下一步：你需要操作

第一步：复核 `backend/docs/artifacts/company_v2_validation_summary.md` 中三股票质量检查结果。
第二步：若接受当前 fail 作为口径差异提示，进入 Phase 6R 监控；若不接受，先进入字段口径归一修复。
第三步：生产切换前继续保留 legacy Company Tab 与 `company_v2=0` 回退路径。
