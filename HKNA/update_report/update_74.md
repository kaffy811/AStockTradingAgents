---
目前完成的工作汇总：

已完成

1. Phase 6V-P1.4 local_live 环境启动
- 在独立干净 clone `/private/tmp/tradingagents-pi-shadow-live` 上运行，分支为 `release/demo-staging`。
- 验收 commit 为 `bbc3379790b9a5308ed0089b98ad276b44d71adf`。
- Backend 以 `CHAT_RUNTIME_MODE=legacy`、`AGENT_EXECUTOR_MODE=pi_compatible_shadow`、`PI_AGENT_SHADOW_ENABLED=true`、`PI_AGENT_ALLOWED_AGENTS=official_report_pdf_pi_v1` 启动。
- 默认配置未改，正式 Pi path 未启用。

2. 专用验收身份与 preflight
- 通过正常 `/api/v1/auth/register` 和 `/api/v1/auth/login` 创建 dedicated local_live test user。
- token 仅在运行进程环境中使用，未写入 artifact 或 Git。
- Runner preflight 通过：backend health、Auth、DB、Chat、SSE、diagnostics、official report tool、resolver、Shadow env、branch/SHA 均 ready。
- DB readiness 用项目 asyncpg/SQLAlchemy `SELECT 1` 与官方报告元数据查询验证通过。

3. 真实 HTTP/SSE smoke
- 执行 3 条真实 HTTP/SSE smoke case，均来自既有 case manifest。
- 结果：planned=30，executed=3，accepted=0。
- 因 smoke 未通过，按 P1.4 要求停止完整 30 条执行。

4. Gate 与 artifacts
- Gate 保持失败：`recommended_for_next_authorization=false`。
- Runtime Gate 保持 `pi_executor_enabled=false`、`authorized_agents=[]`、`decision=do_not_enable_pi_compatible`。
- 已更新 P1.4 artifacts：
  - `backend/docs/artifacts/pi_shadow_acceptance_environment.json`
  - `backend/docs/artifacts/pi_shadow_acceptance_side_effects.json`
  - `backend/docs/artifacts/pi_shadow_browser_acceptance.md`
  - `backend/docs/artifacts/pi_official_report_pdf_live_shadow_results.json`
  - `backend/docs/artifacts/pi_official_report_pdf_live_shadow_summary.md`
  - `backend/docs/artifacts/pi_official_report_pdf_agent_gate.json`
  - `backend/docs/artifacts/pi_compatible_runtime_gate.json`
  - `backend/docs/artifacts/pi_shadow_live_environment_bootstrap.md`

发现的问题

1. Smoke 未通过
- A01：Pi deterministic path 成功，`llm_call_count=0`，但 side-effect checker 记录了 context mutation/side effect。
- A02：Pi `get_official_reports` 超时，返回 `AGENT_TOOL_TIMEOUT`。
- A03：Pi Shadow diagnostics 记录为 `skipped`，未进入 official_report_pdf agent。

2. 性能与 resolver 风险
- local_live 日志显示 resolver 仍会按市场加载 `stock_industry_map` / `stock_master` 大批量记录。
- smoke latency 已超过 warm target，不能推荐授权。

3. 浏览器验收
- 因 smoke 失败且未跑满 30 条，浏览器验收未标记通过。

4. 日志安全
- local_live backend 当前 SQL echo 会输出 SQL bind 参数。
- 本次 artifacts 未保存 token/JWT/完整 user id，但控制台日志出现了测试用户名、邮箱、hashed password 和完整 chat content。
- 在下一次可计入 Gate 的验收前，需要关闭或脱敏 SQL 参数日志。

---
下一步：你需要操作

第一步：修复 smoke blocker
- 区分 Legacy 正常 context commit 与 Pi Shadow 副作用，避免把 legacy 写入误算为 Pi business write。
- 定位 `get_official_reports` 在 local_live 下超时原因，优先优化工具查询和 session 生命周期，而不是简单放宽 timeout。
- 定位 A03 skipped 的 L0/L1 intent/entity/context 条件，确保“这份报告原文在哪里？”能够稳定触发 official_report_pdf Shadow。

第二步：优化 resolver warm path
- 避免 warm resolver 在验收请求中重复触发全市场 30000 行加载。
- 记录 query count 和 full scan count，满足 Gate 的 resolver scan 目标后再重跑。

第三步：修复验收日志安全
- 关闭 live acceptance 环境中的 SQL echo 或启用 SQL 参数脱敏。
- 确认日志不打印 token、JWT、hashed password、完整用户标识、完整 query 或 provider payload。

第四步：重新执行 P1.4
- 先跑 preflight。
- 再跑指定 smoke。
- smoke 全通过后再跑完整 30 条 live HTTP/SSE case。
- 只有 executed=30 后才计算完整 match rate 和授权前 Gate。

注意事项

- 当前不能启用 Pi 正式路径。
- 当前不能推荐 `official_report_pdf_pi_v1` 进入下一阶段授权。
- 本轮没有 migration/schema 变更。
- 本轮没有修改 P1-P4 Prompt、Stage 3、auto_run、rollout 或默认 runtime 配置。
