---
目前完成的工作汇总：

已完成

1. Phase 6P-1 recapture 脚本
- 新增 `backend/scripts/recapture_company_v2_phase6p.py`。
- 支持 in-process service 或 `--base-url` HTTP API 两种采集方式。
- 为 600519、000725、601686 保存 `*_phase6p_recapture.json`，并生成 JSON/Markdown 汇总。
- 内置 Real Provider Data Gate、formatter scan、price semantics scan、computed field scan、coverage/trace scan、provider_summary scan、敏感字段扫描和失败分类。

2. Provider data success 指标补充
- 更新 `backend/app/services/company_v2_debug_service.py`。
- 顶层 summary 增加 `provider_data_failure_count`，避免继续把 wrapper success 当作业务数据成功。

3. Diagnosis 标签补充
- 更新 `backend/app/services/company_v2_debug_diagnosis_service.py`。
- 缺可计算字段时补充 `MISSING_COMPUTED_FIELD`，便于 recapture gate 精确归因。

4. Phase 6P-1 测试
- 新增 `backend/tests/fundamental/test_phase6p1_real_provider_gate.py`。
- 覆盖 formatter、price semantics、field_trace、coverage、provider_summary、computed market cap、report/RAG empty、schema_version、agent_summary、gate failure reasons、敏感字段扫描。

5. Real Provider Data Gate 采集结果
- 使用 provider 网络权限运行 `python backend/scripts/recapture_company_v2_phase6p.py --symbols 600519,000725,601686 --market CN --include-raw true --force-refresh true --out-dir backend/docs/artifacts`。
- 三只股票均通过 gate：`providers_data_success=8`、`modules_renderable=9`、`providers_timeout=0`。
- 生成 `backend/docs/artifacts/company_v2_phase6p_recapture_summary.json` 与 `.md`。
- 未生成 failure analysis，说明本次无 `providers_data_success=0` 的失败分类。

---
下一步：你需要操作

第一步：在 dev/staging 环境保留本次 recapture artifact，作为 Phase 6P Real Provider Data Gate 基线。
第二步：进入 Phase 6Q 前，确认前端页面读取同一批 `display_value`、coverage、field_trace、provider_summary，与 JSON summary 一致。
第三步：可以开始 Phase 6Q：CompanyV2 Data Validation Engine，但 legacy Company Tab 继续保留。
