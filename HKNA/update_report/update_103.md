---
目前完成的工作汇总：

已完成

1. 公式常数集成断点归因
- 冻结 Q3 的首个失败点归类为 `F3_ANSWER_SPAN_NOT_RECOGNIZED_AS_FORMULA`。
- 旧逻辑要求公式句逐字包含派生结果，未识别由 operand 名称绑定的 `×100%`，也未识别实际文本“每实现100元”。

2. Request-local formula policy
- 仅为 citation 已解析、canonical operands 完整的 `ratio_percentage` C1 创建 policy。
- 最终 numeric gate 只在明确公式 span 与同一 C1 operands 或 result 绑定时接受 `100`/`100%`。
- 未修改全局 validator/allowed set；裸常数、非公式 claim、1000/10000/101/99% 和 fabricated 数字继续拒绝。

3. 测试与纯 candidate 复验
- 最终定向测试：48 passed、0 failed、0 skipped、0.67s。
- 隔离 candidate 只执行一次 Q3；request `9cf98947` 完整 S0–S8，citation valid、C1 resolved、numeric valid、metadata leak false、S8 completed。
- 无 retry；没有发起其他运行时请求。

4. 安全与发布边界
- 已生成 `backend/docs/artifacts/company_agents_data_r3_3i2_5_formula_constant_boundary.md/.json`。
- 未修改 timeout、RAG、cache、report selection、embedding、chunking、frontend 或 production 环境。
- 未 push、部署、migration 或扩流；流量保持 `HOLD_1_PERCENT`。

---
下一步：你需要操作

第一步：审阅 follow-up commit、artifact 中的 F3 归因及 request-local policy 边界。
第二步：保持不部署、不扩流；如需 push、合并或发布，必须另行授权。
第三步：后续观察必须继续保留裸 `100`、非公式 `100%` 和 fabricated number 的 fail-closed 回归。
