---
目前完成的工作汇总：

已完成

1. R3.3I.2 report-local structured operand supplement
- 在隔离 candidate tree 增加仅限 selected report、selected annual period 与净利率请求的 operand 补充能力。
- 从同一 CNINFO chunk 的明确年度、单位和币种证据中补充 revenue / parent_net_profit，并绑定 request-local E-label。

2. Derived fact 与安全链路贯通
- 补充字段在 `build_report_derived_facts()` 前进入 structured snapshot。
- 无完整 evidence ID / provenance 时拒绝 structured operand；模型可见内容不含 raw chunk ID。

3. 测试与隔离验收
- 定向测试 34 collected / 34 passed / 0 failed / 0 skipped，0.58s。
- Q1 S5 成功 emitted `net_margin=50.46%`，但 Q1 在 S6 因既有 LLM timeout 结束为 partial_success；按任务边界未修 timeout。
- 已生成 `backend/docs/artifacts/company_agents_data_r3_3i2_structured_operand_coverage.md` 与 `.json`。

---
下一步：你需要操作

第一步：审阅上述 MD/JSON 报告及隔离 candidate tree 中的实现，不要直接提交当前历史脏工作区。
第二步：在独立后续 phase 处理或稳定复现 S6 LLM timeout 后，重新执行原 Q1，并要求 S0–S8、`numeric_validation.valid=true`、final status `completed`。
第三步：只有 Q1 全链路通过后，再评估从 candidate tree 提取最小提交；流量继续保持 `HOLD_1_PERCENT`。
