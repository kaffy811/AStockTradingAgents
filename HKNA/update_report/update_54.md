---
目前完成的工作汇总：

已完成

1. `backend/app/agents/chat_skills/report_comparison_skill.py`
- 修复多轮财报比较实体合并：当前 query 显式实体、上下文 primary entity、代词解析和 comparison parser 输出统一合并为 `comparison_input.entities`。
- 对“那它和五粮液比呢”这类请求，输出顺序为 pronoun/context entity first、current-query explicit entity second，并按 `market + symbol` 去重。
- 增加 resolver diagnostics：`raw_query`、`normalized_query`、`current_query_entities`、`resolved_pronouns`、`context_before`、`candidate_context`、`comparison_skill_input`、`comparison_agent_input`、`context_after`、`context_commit_reason`。
- 普通回答中移除 `report_id`、chunk id 等内部标识，证据列改为用户可理解的正式年报来源描述。

2. `backend/app/agents/chat_orchestrator.py`
- 将 `raw_query` 和 `effective_query` 注入 `SkillContext.metadata`，避免 de-pronoun 后丢失“它”等代词来源。
- 会话财务上下文改为事务式提交：只有 `completed` / `partial_success` 才写入 report/comparison context，`failed` / `timeout` / clarification 不再清空旧 primary entity。
- 成功比较后才提交 comparison entities；失败比较只保留 pending/failed intent，不覆盖上一轮有效上下文。

3. `backend/app/services/security_entity_resolver.py`
- 修复中文文本中 6 位代码边界识别，使用数字负向边界代替英文 `\b`，避免中文相邻字符导致代码解析漏判。
- 生产路径未加入样例股票硬编码，仍通过 security master / resolver 数据驱动解析。

4. `backend/app/datasource/baostock_session_manager.py`
- 新增 BaoStock canonical session manager。
- 使用模块级 `threading.RLock` 串行化 `login -> batch queries -> logout`，记录 `batch_id`、`thread_id`、`login_count`、`query_count`、`logout_count`、`skipped_query_count`。
- 检测 EBADF、socket closed、ConnectionResetError、BaoStock receive error 后立即 abort 当前 batch，剩余 query 不再执行，同 batch 只聚合一条结构化错误。
- 抑制 BaoStock stdout/stderr 进度输出，防止 Web 请求路径出现 tqdm/progress 噪声。

5. `backend/app/datasource/baostock_client.py`
- 年度历史 bulk refresh 改为 direct serialized / subprocess provider runner 两种模式，默认测试环境 direct serialized。
- 去掉历史抓取中的多进程并发 BaoStock session，避免同进程/多进程同时 login/logout 导致 EBADF。
- 兼容的 `login/logout`、单表季度查询、近期行情 fallback、全指标聚合均纳入统一 BaoStock lock。
- 保留现有 singleflight refresh identity，force refresh 不再意味着允许重复并发 provider batch。

6. `backend/app/provider_workers/financial_provider_worker.py`
- 新增独立 provider worker 入口，支持 JSON stdin/stdout。
- 支持 `provider=baostock`、`operation=annual_history`，stdout 只输出 JSON。
- 子进程 timeout、native abort / exit!=0、invalid JSON 都返回 `provider_unavailable` / structured error。
- 子进程环境剔除数据库、Redis、LLM API key 等敏感变量。

7. `backend/app/services/company_v2_stock_basic_service.py`、`backend/app/services/coverage_audit_service.py`
- 现有 BaoStock direct fallback 入口统一进入 BaoStock session manager lock。

8. 测试
- 新增 `backend/tests/fundamental/test_phase6u_d6_2_baostock_isolation.py`，覆盖 login/logout once、EBADF abort、无 tqdm 输出、subprocess success、subprocess nonzero、subprocess timeout。
- 更新 `backend/tests/fundamental/test_phase6u_d6_states_reports_comparison.py`，覆盖 pronoun + explicit entity merge、comparison failed 不提交污染 context。
- Targeted：`28 passed`。
- 相关回归：`137 passed, 1 warning`。
- Full backend：`3231 passed, 1 skipped, 274 warnings`。
- Frontend Vitest：`674 passed`。
- `npm run build`：passed。

---
下一步：你需要操作

第一步：在真实服务环境设置 `FINANCIAL_PROVIDER_EXECUTION_MODE=subprocess`，并用实际 BaoStock 网络环境压测 `history?period=annual&force_refresh=true`。

第二步：在浏览器真实会话中验证三轮 Chat：
`贵州茅台最新财报表现如何？` → `那它和五粮液比呢` → `贵州茅台最新财报表现如何？`。

第三步：观察生产日志中的 BaoStock batch stats，确认每个 batch `login_count=1`、`logout_count=1`，且 EBADF 后没有连续 “接收数据异常” 风暴。
