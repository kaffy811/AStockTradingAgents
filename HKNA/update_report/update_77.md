---
目前完成的工作汇总：

已完成

1. P1.6.2/P1.6.3 临时修复拆分
- 在旧临时 clean clone 中建立 `repair/p16-runtime-transfer` 专用分支。
- 将 Auth principal cache、Chat Streaming 事务隔离、SSE terminal、Shadow terminal diagnostics、official report fast path 与 runner completion 修复拆入 runtime 提交。
- 将数据库 pool 策略纯函数、主 engine/RAG engine 接入和 dialect matrix 测试拆入 DB policy 提交。

2. 验证结果
- Pool matrix 在 SQLite 测试环境连续两次 `13 passed`。
- Targeted backend 回归 `71 passed`。
- Backend full `3359 passed, 15 skipped`。
- Frontend `npm test` 为 `679 passed`，`npm run build` 通过。

3. Gate/Smoke 记录
- 固定 3 条 official_report_pdf Live Shadow Smoke 已记录为 `planned=3, executed=3, accepted=3`。
- 记录 Auth cache、pool policy、resource leak、secret scan、runtime gate 与 agent gate artifacts。
- 正式 Pi path 仍保持关闭：`pi_executor_enabled=false`、`authorized_agents=[]`、`decision=do_not_enable_pi_compatible`。

---
下一步：你需要操作

第一步：将 `repair/p16-runtime-transfer` 上拆分出的 commits 逐个 cherry-pick 到主工作区 `release/demo-staging`。
第二步：在主工作区重新运行 pool matrix、targeted backend、backend full、frontend test/build，并确认默认配置仍为 legacy/Shadow disabled。
第三步：push 主工作区到 `origin/release/demo-staging` 后，从最终远程 SHA 创建新的 clean clone，再执行 Phase 6V-P1.6.4；本阶段不得运行 Full30。
