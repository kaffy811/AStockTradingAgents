---
目前完成的工作汇总：

已完成

1. Phase 6V-P1.5 official_report_pdf Pi Shadow Smoke 阻塞修复
- 修复 A01 side-effect attribution：将 Legacy 正常 `chat_messages` 写入和 session context commit 归属为 `legacy`，Pi Shadow 业务写入仍严格要求为 0。
- 增加目标 session 级 context version 快照，避免全局 context version sum 将 Legacy 正常写入误判为 Pi 副作用。
- Shadow side-effect artifact 已脱敏，不再输出完整 target session id。

2. A02 Tool timeout 收口
- `get_official_reports` 增加 active report id 快路径，优先读取已持久化 `ReportDocument` 元数据。
- Tool latency 拆分为 resolver、DB query、report selection、domain validation、external network、adapter overhead。
- Smoke 中 A01/A02 均未发起 external network，`llm_call_count=0`，`tool_call_count=1`。

3. A03 skipped / ambiguity 修复
- official PDF intent 覆盖 “报告原文 / 年报链接 / 官方报告地址 / 这个年报”等表达。
- 增加 shadow snapshot 路由，优先复用 Legacy input snapshot。
- 对“平安”的 official_report_pdf 歧义请求返回 clarification，不自动选择公司；候选包含平安银行、中国平安。

4. Resolver warm scan 修复
- 对“这份报告/这个年报”等当前报告引用，复用 context entity snapshot，避免重复构建全市场 SecurityEntity index。
- 收窄 context shortcut：比较语义不走该短路，避免影响“那它和五粮液比呢”的旧比较能力。
- 固定 smoke 中 resolver full scan delta=0，rebuild delta=0。

5. SQL 日志安全
- 新增配置 `DATABASE_SQL_ECHO=false`、`DATABASE_SQL_HIDE_PARAMETERS=true`。
- SQLAlchemy engine 默认关闭 echo 并隐藏 bind parameters。
- Smoke artifact SQL audit：parameter exposure=0。

6. 真实 local_live Smoke
- 环境：local_live，branch=`release/demo-staging`，commit=`bbc3379790b9a5308ed0089b98ad276b44d71adf`。
- 专用验收身份：通过正常 register/login 创建，token 仅保存在 `/private/tmp` 临时文件，artifact 只记录 present/hash。
- 固定 3 条真实 HTTP/SSE smoke：planned=3，executed=3，accepted=3。
- Formal Pi path 仍禁用：`pi_executor_enabled=false`，`authorized_agents=[]`，`decision=do_not_enable_pi_compatible`。

7. 测试
- Targeted：`test_phase6v_pi_runtime.py`、`test_phase6v_pi_official_report_shadow.py`、`test_phase6v_p1_1_shadow_acceptance.py` 全部通过。
- Backend full：3349 passed，16 skipped。
- Frontend：679 passed。
- Frontend build：passed。
- 无 migration；未修改 P1-P4 Prompt、Stage 3、auto_run、rollout。

---
下一步：你需要操作

第一步：基于当前 smoke_passed=true 的结果，进入独立 Phase 6V-P1.6 执行完整 30 条 official_report_pdf live shadow case。

第二步：完成浏览器验收后再计算授权前完整 Gate；在 30/30 和 browser acceptance 均通过前，继续保持 Pi 正式路径禁用。
