---
目前完成的工作汇总：

已完成

1. Canonical citation validation boundary
- 保持 Prompt 使用 compacted E-label evidence，同时为后端 citation/provenance 校验建立同标签 canonical evidence map。
- fabricated 数字、错期间和缺 operand provenance 继续 fail closed。

2. 受约束的净利率公式常数
- 未修改全局 numeric validator。
- 仅在 verified ratio_percentage、canonical operands、明确公式 span 和已验证派生结果同时存在时接受 100/100%。

3. 严格串行隔离 harness
- 新增四门 gate：HTTP terminal、S8 persisted、backend completed、health ok。
- Q1 完成后 15.027 秒才启动 Q3，消除了上一轮 overlap。

4. 测试与运行时验收
- 最终定向测试 40/40 passed，0.55s。
- Q3 citation/numeric 均 valid，C1 resolved，最终 completed。
- Q1 遇到未修改的 LLM timeout 并安全 partial_success，因此未创建条件性提交。

---
下一步：你需要操作

第一步：审阅 `backend/docs/artifacts/company_agents_data_r3_3i2_3_citation_claim_boundary.*` 与隔离 candidate tree 的白名单改动。
第二步：不要提交当前历史脏工作区；若后续允许重新验收，继续使用严格串行 harness，并保持 timeout 修复在独立 phase。
第三步：只有 Q1 与 Q3 同时完整通过 S0–S8 后，才创建最小白名单提交；流量继续 `HOLD_1_PERCENT`。
