---
目前完成的工作汇总：

已完成

1. 字段定义 registry 拆分
- 修改 `backend/app/services/company_v2_financial_field_definition_registry.py`。
- 明确拆分 `revenue`、`total_operating_revenue`、`main_business_revenue`。
- 明确拆分 `net_profit`、`net_profit_parent`、`net_profit_parent_excl_nonrecurring`。
- 明确拆分 `roe`、`roe_weighted`、`roe_diluted`。
- `field_definition_match` 现在输出 `exact`、`alias`、`incompatible`、`unknown` 语义，不把不同口径字段自动视为相同。

2. Source metadata 补全
- 修改 `backend/app/services/company_v2_normalizers.py`。
- BaoStock normalized row 现在为相关字段补充：
  - `provider_definition`
  - `matched_label`
  - `field_definition_match`
  - `value_basis`
- 已停止把 BaoStock `netProfit` 自动填充为 `net_profit_parent`。
- `roeAvg` 暂按 `unknown_roe` 处理，不强校验为 `roe_weighted`。

3. AI verifier metadata 透传
- 修改 `backend/app/services/company_v2_official_verification_service.py`。
- 修改 `backend/app/services/company_v2_ai_official_verification_agent.py`。
- 修改 `backend/app/services/company_v2_ai_verification_guardrail.py`。
- AI verification 字段结果现在包含 `provider_definition`、`matched_label`、`report_period`、`value_basis` 和 `field_definition_match`。
- guardrail 会基于这些 metadata 决定是否允许数值比较；口径不兼容时保留 `definition_mismatch`，不计入 `true_conflict_count`。

4. 前端口径文案
- 修改 `frontend/src/components/company-v2/CompanyV2ReportTimeline.vue`。
- 仅新增轻量字段口径文案：
  - `revenue`: 营业收入字段口径不同
  - `net_profit_parent`: 净利润与归母净利润口径不同
  - `roe_weighted`: ROE 与加权平均 ROE 口径不同
- 未改整体布局、未改图表。

5. Phase 6T-C4 artifact 脚本
- 新增 `backend/scripts/company_v2_run_601686_ai_verify_phase6tc4.py`。
- 脚本只处理 601686 2024 annual、report_id=1、已有 parsed sidecar。
- 不做 RAG、不新增数据源、不改 CNINFO/PDF 主链路。
- 使用 Phase 6T-C2 真实 AI extraction replay，并注入 C4 provider metadata 后重新运行 AI verifier/guardrail。

6. 601686 Phase 6T-C4 artifacts
- 已生成：
  - `backend/docs/artifacts/company_v2_601686_ai_official_verification_phase6tc4.json`
  - `backend/docs/artifacts/company_v2_601686_ai_human_review_queue_phase6tc4.json`
  - `backend/docs/artifacts/company_v2_601686_ai_verification_summary_phase6tc4.md`
- Before C4：
  - `revenue=definition_mismatch`
  - `net_profit_parent=definition_mismatch`
  - `roe_weighted=definition_mismatch`
  - `human_review_queue_count=3`
- After C4：
  - `revenue=definition_mismatch`
  - `net_profit_parent=definition_mismatch`
  - `roe_weighted=definition_mismatch`
  - `human_review_queue_count=3`
  - `true_conflict_count=0`
  - `provider_definition_known_count=6`
  - `provider_definition_unknown_count=0`
- C4 没有为了减少人工队列而强行标记 verified。

7. 测试
- 新增 `backend/tests/fundamental/test_phase6tc4_financial_field_definition_alignment.py`。
- 更新 `frontend/src/tests/companyV2AIVerificationSemantics.test.js`。
- 验收结果：
  - `backend/.venv/bin/python -m pytest backend/tests/fundamental/test_phase6tc4_financial_field_definition_alignment.py -q`：9 passed。
  - `backend/.venv/bin/python -m pytest -q`：2787 passed, 1 skipped。
  - `npm run test`：44 test files passed, 572 tests passed。
  - `npm run build`：通过。

8. 是否可以结束校对阶段
- C4 已完成字段定义对齐和 artifact 复核。
- 当前仍有 3 个真实 definition mismatch，但它们已被明确归因，不再误报为 provider value conflict。
- 可以结束 AI verification 语义校对阶段；后续如要继续，应进入结构化字段来源修正或 provider metadata 深化，而不是进入 RAG。

---
下一步：你需要操作

第一步：打开 `backend/docs/artifacts/company_v2_601686_ai_verification_summary_phase6tc4.md`，确认 C4 Before/After 结果和 provider definition 摘要。

第二步：确认是否接受 `revenue=main_business_revenue`、`net_profit_parent=net_profit`、`roe_weighted=unknown_roe` 这三个字段继续保留为真实 definition mismatch。

第三步：如接受 C4 结果，可以结束 AI verification 校对阶段；后续不要直接进入 RAG，应先决定是否做结构化字段来源修正。
