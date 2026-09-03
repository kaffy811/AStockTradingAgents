---
目前完成的工作汇总：

已完成

1. AI verification 字段语义校准
- 修改 `backend/app/services/company_v2_ai_verification_guardrail.py`。
- 字段状态统一为 C3 新枚举：`verified`、`likely_match`、`conflict`、`structured_field_missing`、`official_field_not_found`、`insufficient_evidence`、`definition_mismatch`、`period_basis_mismatch`、`unit_scale_suspected`、`needs_human_review`、`skipped`。
- 只有同期间、同口径、同单位、证据可靠且数值超过 tolerance 的差异才计入 `true_conflict_count`。
- 新增 `non_blocking_findings`，缺字段、证据未找到、明确期间差异等不再默认进入人工抽检队列。

2. 字段定义 registry
- 新增 `backend/app/services/company_v2_financial_field_definition_registry.py`。
- 定义 revenue、net_profit、net_profit_parent、operating_cashflow、total_assets、equity_parent、eps_basic、roe_weighted、total_share、float_share 的 canonical name、alias 与 incompatible alias。
- 明确不把 `net_profit` 与 `net_profit_parent` 自动视为同字段；不把 generic `roe` 与 `roe_weighted` 无条件视为同字段；股本字段要求期间/时点基础。

3. AI verifier 输出与 API payload
- 修改 `backend/app/services/company_v2_ai_official_verification_agent.py`。
- LLM 输出增加 bounded timeout，避免 provider 长时间阻塞。
- fallback 与 omitted field 不再输出旧 `not_found/mismatch` 状态。
- 字段结果补充 `structured_period`、`structured_field_name`、`field_definition_match`。
- 修改 `backend/app/services/company_v2_ai_verification_response.py` 与 `backend/app/routers/company_v2_debug.py`，API 响应包含 `non_blocking_findings` 与 `summary_counts`。

4. 前端轻量语义展示
- 修改 `frontend/src/components/company-v2/CompanyV2ReportTimeline.vue`。
- 新增 C3 状态文案：冲突、口径不同、期间/时点不同、单位疑似、结构化缺字段、报告证据不足等分开展示。
- `conflict` 使用红色，definition/period/unit 使用黄色，missing/evidence 使用灰色。
- 新增 `non_blocking_findings` 轻量列表。
- 修改 `frontend/src/components/company-v2/CompanyV2ReportDocuments.vue`，AI 校对完成提示按 C3 aggregate status 调整。

5. Phase 6T-C3 artifact 脚本
- 新增 `backend/scripts/company_v2_run_601686_ai_verify_phase6tc3.py`。
- 脚本只处理 601686 2024 annual、report_id=1、已有 parsed page sidecar。
- 不做 RAG、不批量下载、不改 CNINFO/PDF 主链路。
- 由于 live provider 构建会触发 baostock 并长时间等待，C3 脚本使用 Phase 6T-C2 已保存的真实 AI extraction 作为 semantic calibration replay 输入，再通过 `verify_with_ai` 和 C3 guardrail 重新分类。

6. 601686 Phase 6T-C3 artifacts
- 已生成：
  - `backend/docs/artifacts/company_v2_601686_ai_official_verification_phase6tc3.json`
  - `backend/docs/artifacts/company_v2_601686_ai_human_review_queue_phase6tc3.json`
  - `backend/docs/artifacts/company_v2_601686_ai_verification_summary_phase6tc3.md`
- Before：`final_status=conflict`，`human_review_queue_count=10`。
- After：`final_status=needs_human_review`，`true_conflict_count=0`，`human_review_queue_count=3`，`non_blocking_findings_count=6`。
- 字段状态：`net_profit=verified`；`revenue/net_profit_parent/roe_weighted=definition_mismatch`；`operating_cashflow/total_assets/equity_parent/eps_basic=structured_field_missing`；`total_share=period_basis_mismatch`；`float_share=official_field_not_found`。
- artifact 未泄露 local path，未返回完整 PDF 文本。

7. 测试
- 新增 `backend/tests/fundamental/test_phase6tc3_ai_verification_semantics.py`。
- 更新 `backend/tests/fundamental/test_phase6tc1_ai_official_verification_agent.py` 以适配 C3 新状态枚举。
- 新增 `frontend/src/tests/companyV2AIVerificationSemantics.test.js`。
- 验收结果：
  - `backend/.venv/bin/python -m pytest backend/tests/fundamental/test_phase6tc3_ai_verification_semantics.py -q`：11 passed。
  - `backend/.venv/bin/python -m pytest -q`：2778 passed, 1 skipped。
  - `npm run test`：44 test files passed, 571 tests passed。
  - `npm run build`：通过。

8. 是否建议进入后续阶段
- 不建议直接进入大范围 Phase 6T-D。
- 建议先确认 C3 artifact 的 semantic calibration 口径，尤其是 `revenue`、`net_profit_parent`、`roe_weighted` 三个 definition mismatch 是否需要自动映射或结构化字段修正。

---
下一步：你需要操作

第一步：打开 `backend/docs/artifacts/company_v2_601686_ai_verification_summary_phase6tc3.md`，确认 Before/After 状态变化和字段状态分类是否符合 Phase 6T-C3 验收。

第二步：检查 `backend/docs/artifacts/company_v2_601686_ai_human_review_queue_phase6tc3.json` 中 3 个 definition mismatch，决定是否需要 C3 follow-up 做结构化字段口径修正。

第三步：在 C3 artifact 验收前，不进入 RAG、不删除 legacy、不改图表、不改 CNINFO/PDF 主链路。
