---
目前完成的工作汇总：

已完成

1. Git 与环境前置检查
- 当前分支：`release/demo-staging`。
- 当前 commit：`a4db27cb91154baed640eb0b3bc93bf67a9dad45`。
- Pi Runtime 与 Shadow Gate 基线代码已在 HEAD 中。
- 当前工作区仍有 unrelated dirty files，未回滚、未纳入本轮验收结论。

2. `backend/scripts/pi_official_report_pdf_live_shadow_acceptance.py`
- 新增 `--preflight-only`。
- 新增 `--environment-type=staging|local_live|local_fixture`。
- Preflight 记录 branch、commit SHA、environment type、auth mode、database mode、provider mode。
- 禁止 production mode。
- 禁止 local fixture 计入 live acceptance。
- 增加 HTTP auth/chat readiness 检查。
- 增加 input snapshot hash 从 diagnostics 回填到 comparison。

3. `backend/app/agent_runtime/shadow_diagnostics.py`
- 增加 `input_snapshot_hash`。
- 继续只写 compact diagnostics，不保存完整 query、user id、token、JWT、Prompt 或 CoT。

4. `backend/app/agent_runtime/shadow_acceptance.py`
- Runtime Gate 升级为 Phase 6V-P1.3。
- 增加 `source_url_match_rate`、`clarification_correctness_rate`。
- 只有 30/30 样本执行完成才计算完整 rate。

5. P1.3 Preflight 结果
- `python backend/scripts/pi_official_report_pdf_live_shadow_acceptance.py --preflight-only`：失败，未执行 case。
- `python backend/scripts/pi_official_report_pdf_live_shadow_acceptance.py --execute`：在 preflight 阶段停止，executed=0。
- 当前 blockers：
  - 缺少显式 Shadow env。
  - 缺少 `PI_AGENT_SHADOW_DIAGNOSTICS_PATH`。
  - 缺少 `PI_SHADOW_ACCEPTANCE_BASE_URL`。
  - 缺少 service account token/user id。
  - DB readiness failed。
  - 当前推断为 local_fixture，不能计入 live acceptance。

6. 测试与回归
- `pytest backend/tests/fundamental/test_phase6v_pi_runtime.py -q`：21 passed。
- `pytest backend/tests/fundamental/test_phase6v_pi_official_report_shadow.py -q`：19 passed。
- `pytest backend/tests/fundamental/test_phase6v_p1_1_shadow_acceptance.py -q`：8 passed。
- `pytest backend/tests -q`：3338 passed, 16 skipped。
- `npm test`：679 passed。
- `npm run build`：passed。

---
下一步：你需要操作

第一步：在 staging 或 local_live 环境准备专用验收账号，不使用开发者主账号或真实普通用户。

第二步：仅在当前 shell 或安全 secrets manager 中设置：
- `CHAT_RUNTIME_MODE=legacy`
- `AGENT_EXECUTOR_MODE=pi_compatible_shadow`
- `PI_AGENT_SHADOW_ENABLED=true`
- `PI_AGENT_ALLOWED_AGENTS=official_report_pdf_pi_v1`
- `PI_AGENT_SHADOW_DIAGNOSTICS_PATH=/tmp/pi_shadow_diagnostics.jsonl`
- `PI_SHADOW_ACCEPTANCE_ENVIRONMENT_TYPE=staging`
- `PI_SHADOW_ACCEPTANCE_BASE_URL=<backend base url>`
- `PI_SHADOW_ACCEPTANCE_USER_ID=<test user id>`
- `PI_SHADOW_ACCEPTANCE_ACCESS_TOKEN=<token>`

第三步：先跑 preflight：
- `python backend/scripts/pi_official_report_pdf_live_shadow_acceptance.py --preflight-only`

第四步：preflight 全部通过后再执行 30 条：
- `python backend/scripts/pi_official_report_pdf_live_shadow_acceptance.py --execute --stream`

第五步：使用已登录测试账户完成浏览器三组对话验收，并更新 `backend/docs/artifacts/pi_shadow_browser_acceptance.md`。
