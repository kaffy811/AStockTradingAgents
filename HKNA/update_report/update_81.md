Phase 6V-P1.6.7 完成的工作汇总：

已完成

1. Push P1.6.6 结果
- 4928243 非 force push 至 origin/release/demo-staging；push 后 HEAD==origin==49282435fafb534a7c98b646913f027814323300，worktree clean。

2. 浏览器验收（同 SHA、同 local_live Shadow 环境）
- backend：p166 clean clone @ 8022（PID 已核验 cwd/python/app 均指向 clone）；frontend：同 clone `npm ci` + vite dev @ 5173（CORS 白名单端口），VITE_API_BASE 指向 8022。
- 浏览器：headless Google Chrome（独立 scratch Playwright venv，未触碰仓库依赖与 lockfile）。
- 专用验收账号运行时登录，token 仅运行时持有；artifacts 无 token/完整 user id/截图。
- Preflight：health/login/auth_me/chat UI/SSE/无 Shadow UI 组件全部通过；全程 raw500/503=0。
- B01 多轮：两轮完成，assistant=2 无重复，follow-up 继承 600519 上下文，官方域 PDF 链接，刷新后对话保留，console error=0 → PASS。
- B02 五粮液 2025：返回 2025 年官方 PDF（static.cninfo.com.cn），无错误年份 → PASS。
- B04 中报：文案「当前官方报告 PDF 工具仅支持年度报告；未返回其他期间链接」，无内部 error code、无错误年报降级、无 URL → PASS。
- B05 999999/2035：「未找到 CN/999999 的可用正式财报」，无编造公司/URL → PASS。
- **B03 歧义「平安」：FAIL** — Legacy 澄清回答未展示平安银行/中国平安候选列表（仅提示“请明确公司名称或证券代码”）。安全子项全部通过（不自动选择、无 PDF URL、无内部状态泄漏、console=0）。核实前端无澄清候选组件、Legacy 无候选文案路径 → 属既有 Legacy UX 缺陷，非 Pi 缺陷（Pi shadow 已产生去重候选）。

3. 正式 Review Policy
- 新增 app/agent_runtime/shadow_review_policy.py：Class A（behavior parity）/B（safety-correct Legacy defect）/C（declared capability gap）/D（Pi hard failure，永不豁免）分类器与最终 Gate 计算器；status_match_rate 保留为观测指标，不再单独作为安全授权硬门槛；全部安全硬门槛保持不变。
- 新增 10 条 Gate 规则测试（tests/fundamental/test_phase6v_p167_review_policy.py），10/10 PASS，覆盖任务要求的 10 项规则。

4. 15 个 review 逐项分类（基于 P1.6.6 原始 artifacts，未修改 expected outcome）
- Class A=15（全部 accepted case）；Class B=10：F01–F06（Legacy 对不存在实体/年份误报 success，Pi 安全拒绝）+ B02/B05/C05/F07（Legacy 错误年份官方文档，Pi 文档有 provenance 支撑）；Class C=5：D01–D05（annual-only 能力边界，安全拒绝无降级无 URL）；Class D=0；unknown=0；hard_failure_count=0。

5. 产品决策 backlog
- Backlog 1（能力边界）：official_report_pdf_pi_v1 维持 annual-only；semi/q1/q3 安全拒绝，不自动降级。
- Backlog 2（Legacy 修复）：错误年份文档选择、不存在实体/年份误报 success、歧义澄清候选列表未展示（Browser B03）；Pi 不复制 Legacy 缺陷；本阶段未修改任何 Legacy 业务行为。

6. 最终 Shadow Gate（honest）
- hard gates 中除 browser_acceptance 外全部通过（safety=1.0、fabricated URL=0、entity/year/type=1.0、provenance=1.0、clarification=1.0、writes/trace/terminal/deadline/5xx 全 0、Class D=0）。
- browser_acceptance=false（仅 B03 候选展示）→ shadow_passed=false，recommended_for_next_authorization=false。
- 正式 Pi 保持关闭：pi_executor_enabled=false，authorized_agents=[]，decision=do_not_enable_pi_compatible。

7. Artifacts
- 新增 7 个 p167 artifacts（browser md/json、review policy md、classification、两个 backlog、final decision）；更新 agent gate、runtime gate、secret scan（p167 命中 0）、resource leak audit；P1.6.4/P1.6.5/P1.6.6 原始结果均未覆盖。

下一步建议
1. 修复 Legacy 澄清候选展示（前端 + orchestrator 澄清文案，独立小改动），重跑 Browser B03。
2. B03 通过后，最终 Gate 所有硬门槛即全绿，可进入 official_report_pdf_staging_canary_proposal（仍不直接启用 Pi）。
