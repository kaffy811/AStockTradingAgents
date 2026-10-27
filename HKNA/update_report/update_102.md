---
目前完成的工作汇总：

已完成

1. 最小可信度修复 commit
- 在已验证 candidate 基线创建独立 commit `28870a13d98f6e7bab5a2b16c6f3144411859198`。
- commit 只含 14 个 Agent、provenance service、诊断 harness、定向测试和 R3.3I.2.3 审计文件；排除了 Docker、dependency、migration、embedding provider 和主工作区历史脏改。

2. 纯 commit candidate image
- 从 detached clean worktree 构建 `tradingagents-backend:rc-r33i2-4-28870a1`。
- OCI revision 精确等于 commit SHA；关键源码的镜像 SHA-256 与 clean worktree 一致，Git blob 对照一致。
- candidate 无 bind mount，只连接隔离 PostgreSQL/Redis；production identity 未被替换。

3. 定向测试与一次性 Q3
- 完整配置后的定向测试为 44 passed、0 failed、0 skipped、0.67s。
- Q3 只执行一次，无 retry；S5 生成 revenue、net_profit 和 `net_margin=50.46%`，citation valid、C1 resolved、无 metadata 泄漏。
- pure candidate 的 numeric gate 仍拒绝公式 `100%` 和 `100`，S8 正确安全降级为 `partial_success`，因此判定 `CANDIDATE_REGRESSION_DETECTED`。

4. 安全与发布边界
- 没有修改 timeout、LLM、RAG、cache、report selection 或全局 numeric validator。
- 没有 push、部署、migration、production 变更或扩流；流量保持 `HOLD_1_PERCENT`。
- 已生成 `backend/docs/artifacts/company_agents_data_r3_3i2_4_commit_candidate.md/.json`。

---
下一步：你需要操作

第一步：审阅纯 candidate Q3 trace `ab337d23` 的 S7 `100%` / `100` 首次拒绝证据和本阶段 artifacts。
第二步：不要部署或扩流；若授权下一阶段，应单独定位为何相同 commit 的公式常数路径未在纯镜像中生效，不要扩大 numeric 豁免。
第三步：commit `28870a13...` 已创建但未 push；是否保留、后续修复或合并需单独发布决策。
