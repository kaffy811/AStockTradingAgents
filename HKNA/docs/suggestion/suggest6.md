# HKNA 产品验收报告 6：Trace Durability 已关闭，进入纯提交镜像门禁

## 1. 本次验收范围

验收 Phase R3.3B 的 Agent trace durability、敏感信息保护、运行时阶段留证和隔离提交。

## 2. 已完成内容

- `b055da8 feat(agent-audit): persist durable report analysis traces` 已独立提交。
- S0–S8 支持原子状态记录，失败/超时/质量拒绝不会丢失已完成阶段。
- S7 记录 unsupported token、完整答案句子、首次观察阶段、证据摘要、citation 与 metadata leak 结果。
- 真实五类查询均有完整 trace 或明确失败终点，未发现 D3 回归或敏感信息泄漏。

## 3. 当前风险

- 当前生产 uvicorn 仍运行旧的 dirty image，未包含 trace durability commit。
- 此 commit 对应 migration 已应用，但应用运行时尚未切换到该可追溯镜像。
- 仍未形成可对应 Git SHA 的 release image，不能重新开始 numeric root-cause 修复或扩大流量。

## 4. 下一步任务

P0：建立从 `b055da8` 独立 worktree 构建、带 SHA/digest 证据的候选镜像；只做 build/import/hash/安全验证，不替换当前容器、不接收新流量。

P1：候选镜像验证后，才以 durable trace 收集新的 numeric-invalid 样本，并按 token 根因实施独立最小修复。

## 5. 发布建议

维持 `HOLD_1_PERCENT`。本阶段不应提交既有 Docker、embedding、dependency 或 warmup 改动，也不得让当前 dirty image 代表 b055da8 的发布状态。
