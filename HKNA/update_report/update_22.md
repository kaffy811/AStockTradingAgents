---
目前完成的工作汇总：

已完成

1. Phase 6T-F 显式跨报告比较
- 在 Phase 6T-D / 6T-E3 的单报告 QA 与多报告索引隔离基础上，新增同一 symbol、显式选择 2–4 份报告的比较入口。
- 普通单报告 QA 继续保持 report_id 强过滤，不会自动进入比较模式。
- 比较模式只接受 `report_ids` 显式列表，不允许跨股票、不允许隐式补齐其他报告。

2. 修改文件清单
- Backend:
  - `backend/app/routers/company_v2_report_rag.py`
  - `backend/app/services/company_v2_report_comparison_answer_service.py`
  - `backend/app/services/company_v2_report_comparison_calculator.py`
  - `backend/app/services/company_v2_report_comparison_evidence_builder.py`
  - `backend/app/services/company_v2_report_comparison_prompt_builder.py`
  - `backend/app/services/company_v2_report_comparison_retriever.py`
  - `backend/scripts/company_v2_cross_report_comparison_eval.py`
  - `backend/tests/fundamental/test_phase6tf_comparison_answer.py`
  - `backend/tests/fundamental/test_phase6tf_comparison_api.py`
  - `backend/tests/fundamental/test_phase6tf_comparison_calculator.py`
  - `backend/tests/fundamental/test_phase6tf_comparison_retriever.py`
  - `backend/tests/fundamental/test_phase6tf_comparison_safety.py`
  - `backend/tests/fundamental/test_phase6tf_evidence_matrix.py`
- Frontend:
  - `frontend/src/api/companyV2.js`
  - `frontend/src/components/company-v2/CompanyV2ReportDocuments.vue`
  - `frontend/src/components/company-v2/reports/CompanyV2ReportComparisonPanel.vue`
  - `frontend/src/tests/companyV2ReportComparisonPanel.test.js`
- Artifacts / report:
  - `backend/docs/artifacts/company_v2_601686_cross_report_comparison_phase6tf.json`
  - `backend/docs/artifacts/company_v2_601686_cross_report_comparison_eval_phase6tf.json`
  - `backend/docs/artifacts/company_v2_601686_cross_report_comparison_eval_phase6tf.md`
  - `backend/docs/artifacts/company_v2_phase6tf_final_gate.json`
  - `backend/docs/artifacts/company_v2_phase6tf_final_gate.md`
  - `HKNA/update_report/update_22.md`

3. 比较模式后端实现
- 新增 comparison retriever / evidence matrix / change calculator / prompt builder / answer service。
- 每份报告独立检索，始终强制限定在所选 `report_ids` 内。
- 每个结论都保留 report year / report type / page citation。
- 明确拒绝投资建议与未来预测。
- 支持 annual vs annual、annual vs q3 的显式比较，并为 q3/annual 口径提供 period-basis warning。

4. 前端显式入口
- 在报告文档区域新增 “比较报告” 按钮。
- 新增 `CompanyV2ReportComparisonPanel.vue`：
  - 手动勾选 2–4 份报告
  - 比较模式选择
  - 比较问题输入
  - 结果、指标变化、页码 citation、CNINFO source URL 展示
- 切换 symbol 会清空比较状态，不会影响普通 QA。

5. 真实 601686 比较验证
- 2023 annual vs 2024 annual：
  - 营业收入：answered
  - 归母净利润：answered
  - 经营活动现金流：answered
- 2024 q3 vs 2024 annual：
  - 营业收入：period_basis_warning
  - 全年净利润相对前三季度：period_basis_warning
- 风险 / 主营业务类比较保持证据隔离，未进行无证据推断。

6. Comparison Eval
- selected_report_isolation_rate = 1.00
- dual_citation_rate = 1.00
- citation_page_accuracy = 1.00
- comparable_metric_accuracy = 1.00
- period_basis_warning_accuracy = 1.00
- unsupported_comparison_rate = 0.00
- wrong_report_usage_rate = 0.00
- investment_advice_refusal = 1.00
- prediction_refusal = 1.00
- phase6tf_passed = true

7. Tests / Build
- Backend full pytest：
  - 2918 passed, 1 skipped
- Frontend full tests：
  - 51 files / 628 tests passed
- Frontend build：
  - 成功
- 环境 warning：
  - `pyenv: cannot rehash`
  - Vite CJS deprecation warning
  - 均不影响结果

8. Limitations
- 当前比较模式仅支持同一 symbol 的 2–4 份显式选择报告。
- 仍不支持跨股票比较、自动选择报告、全历史几十份报告或投资建议输出。
- 当前比较评估仍是 deterministic/extractive，没有引入新的外部模型依赖。

9. Rollback
- 可回滚新增 comparison services、comparison route、比较面板和 comparison eval 脚本。
- 不影响 Phase 6T-D / E3 已有单报告 QA、多报告索引隔离、CNINFO stability 和 Fast/Deep acceptance artifacts。

10. 结论
- Phase 6T-F 已通过。
- 建议进入下一阶段：结构化财务与官方报告证据融合。

