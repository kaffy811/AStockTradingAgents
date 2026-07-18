---
目前完成的工作汇总：

已完成

1. `backend/app/agent_runtime/shadow_diagnostics.py`
- 新增 Pi Shadow compact diagnostics JSONL sink。
- 使用 `query_hash`、`user_hash` 关联 HTTP 请求与后台 Shadow 结果。
- 不保存 token、JWT、密码、完整 user id、Prompt、CoT 或完整 Tool payload。

2. `backend/scripts/pi_official_report_pdf_live_shadow_acceptance.py`
- 将验收 runner 升级为 HTTP Chat request 路径。
- 支持 service account token/user id 环境变量。
- 支持显式 `--allow-local-fixture-user` 在 local/test/staging 创建或复用 fixture 用户。
- 增加环境前检、HTTP health、诊断轮询、SSE completion 校验、side-effect snapshot。
- 当前环境缺少 Shadow env、diagnostics path、base URL、identity 和 DB readiness，因此 executed samples 保持 0。

3. `backend/app/agent_runtime/shadow_acceptance.py`
- Gate 升级为 Phase 6V-P1.2。
- 只有 executed samples 达到 planned samples 30 时才计算完整 match metrics。
- 新增 context mutation、double write、raw 500 指标。
- 新增 artifact：`pi_shadow_acceptance_environment.json`、`pi_shadow_acceptance_side_effects.json`、`pi_shadow_browser_acceptance.md`。

4. `backend/app/agents/chat_orchestrator.py`
- Shadow 后台任务完成后写 compact diagnostics。
- diagnostics 写入失败只记录 debug，不影响 Legacy HTTP 状态和用户回答。

5. 测试与回归
- `pytest backend/tests/fundamental/test_phase6v_pi_runtime.py -q`：21 passed。
- `pytest backend/tests/fundamental/test_phase6v_pi_official_report_shadow.py -q`：9 passed。
- `pytest backend/tests/fundamental/test_phase6v_p1_1_shadow_acceptance.py -q`：8 passed。
- `pytest backend/tests -q`：3328 passed, 16 skipped。
- `npm test`：679 passed。
- `npm run build`：passed。

---
下一步：你需要操作

第一步：在 local/staging 启动后端并显式设置：
- `AGENT_EXECUTOR_MODE=pi_compatible_shadow`
- `PI_AGENT_SHADOW_ENABLED=true`
- `PI_AGENT_ALLOWED_AGENTS=official_report_pdf_pi_v1`
- `CHAT_RUNTIME_MODE=legacy`
- `PI_AGENT_SHADOW_DIAGNOSTICS_PATH=/tmp/pi_shadow_diagnostics.jsonl`

第二步：准备验收身份，二选一：
- 使用 service account：设置 `PI_SHADOW_ACCEPTANCE_USER_ID`、`PI_SHADOW_ACCEPTANCE_ACCESS_TOKEN`、`PI_SHADOW_ACCEPTANCE_BASE_URL`。
- 本地 fixture：使用 `--allow-local-fixture-user`，仅限 local/test/staging。

第三步：执行真实 30 条 HTTP Shadow 验收：
- `python backend/scripts/pi_official_report_pdf_live_shadow_acceptance.py --execute --base-url http://127.0.0.1:8000 --allow-local-fixture-user`

第四步：完成已登录浏览器验收，并更新 `backend/docs/artifacts/pi_shadow_browser_acceptance.md`。
