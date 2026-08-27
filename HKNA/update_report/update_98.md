---
目前完成的工作汇总：

已完成

1. Report Chat S0–S8 持久化审计
- 新增专用 trace header/stage 数据模型、Alembic migration 与失败安全 repository。
- 每个阶段先写 started，再写 completed/failed/rejected/skipped；超时或进程异常可保留最后阶段。
- 普通用户响应不暴露 trace，审计数据仅供管理员和工程数据库路径使用。

2. Numeric 与 citation provenance
- S7 保存 unsupported token、完整答案句子、first-observed stage、证据 token 摘要、报告 ID/year、retrieved chunk IDs、citation validation 与 metadata leak 结果。
- S6 保存受长度限制且脱敏的 raw structured LLM result 和 structured facts。
- S8 保存受控 final response，不把 trace ID 或数据库内部信息加入用户 API。

3. 数据最小化与安全边界
- Session ID 使用 SHA-256；问题、证据、LLM 与最终答案字段均设长度上限。
- Authorization、Cookie、API key、secret、token、password 和 connection string 均脱敏。
- Trace 写入失败不会改变 numeric validator 或主业务安全状态，只写 correlation 日志。

4. 测试与运行时验收
- 127 项 Report Chat、D3、numeric、cache 与 hardening 回归全部通过。
- 五条真实串行请求全部形成完整 S0–S8 或明确失败终点；LLM timeout 留在 S6 failed，numeric invalid 留在 S7 并保存 token 句子。
- 无 secret 泄漏、无 raw chunk ID 最终答案回归、无 trace persistence failure。

5. 发布边界
- 既有 Dockerfile、main.py warmup、embedding provider、pyproject.toml 与 uv.lock dirty changes 未修改、未纳入本阶段。
- 未 push、未部署、未重建生产镜像、未扩大流量；保持 HOLD_1_PERCENT。

---
下一步：你需要操作

第一步：Owner 审阅独立 commit 与 `backend/docs/artifacts/company_agents_data_r3_3b_trace_durability.md`。

第二步：在 R3.3C 构建只含已提交代码、带 Git SHA/image digest 标签的 release image，并验证运行镜像可追溯性。

第三步：积累新的完整 S0–S8 numeric-invalid trace 后，单独授权 R3.3D 根因修复；不要提前放宽 validator。

第四步：保持 1% 流量，不执行 push、deploy 或扩流，直到后续 owner-approved gate。
