---
目前完成的工作汇总：

已完成

1. `backend/app/core/database.py` / `backend/app/core/config.py`
- 增加 `DB_CONNECTION_MODE` 与 `DATABASE_TRANSACTION_POOL_STRATEGY`，显式区分 `direct`、`session_pooler`、`transaction_pooler`。
- Supabase Transaction Pooler 默认改为小型连接池策略，避免本地 `5+10` 突发连接叠加远端 pooler。
- 启动日志只输出连接模式、host class、端口、pool class、pool size 和 timeout，不打印 URL 或密码。

2. `backend/app/core/runtime_reliability.py`
- 新增 `AuthPrincipal`、`RequestDeadline`、运行时 metrics、auth user TTL cache、singleflight 和 auth DB circuit breaker。
- `load_auth_principal()` 使用短事务查询用户状态，DB checkout/connect timeout 返回结构化 503。
- `CancelledError` 继续向上传播，不把请求取消伪装成普通 500。

3. `backend/app/dependencies.py`
- `get_current_user` 改为本地校验 JWT 后构造 `AuthPrincipal`，cache miss 才短事务查询用户状态。
- 区分 invalid/expired token 的 401、disabled/not found 的 401/403、DB unavailable 的 503。
- Chat 请求不再每条消息无条件加载完整 User ORM。

4. `backend/routers/health.py`
- 新增 `/health/runtime`，输出 runtime metrics、auth circuit state 和 pool snapshot。
- 指标不包含用户邮箱、JWT、数据库 URL 或 secret。

5. `backend/scripts/db_connection_mode_probe.py`
- 新增连接模式 A/B probe 脚本，覆盖 current QueuePool、NullPool、小型 QueuePool。
- 输出 `backend/docs/artifacts/db_connection_mode_probe.json`，记录 serial/concurrent/short transaction/cancellation 结果。
- 当前 Supabase pooler 网络条件下三组均在 60 秒组预算内未完成，说明故障点仍在连接建立/SSL create_connection 层，而非 Agent 层。

6. `frontend/src/api/http.js` / `frontend/src/api/chat.js`
- 503 `AUTH_DATABASE_UNAVAILABLE` 不再触发登出或跳转登录。
- 前端保留用户输入，向上抛出可重试错误消息与 `errorCode` / `retryAfter`。

7. 测试与验证
- Targeted backend：`21 passed, 1 warning`。
- Auth optional compatibility：`1 passed, 1 warning`。
- Full backend：`3252 passed, 15 failed, 299 warnings`；剩余失败集中在 live Supabase/RAG/worker 连接依赖，首个失败为 `aws-1-ap-northeast-2.pooler.supabase.com:6543` DNS/连接建立失败。
- Frontend Vitest：`679 passed`。
- Frontend build：passed。
- Python compileall：passed。

---
下一步：你需要操作

第一步：在本地 `.env` 明确设置 `DB_CONNECTION_MODE=transaction_pooler`，并按 probe 结果在 `DATABASE_TRANSACTION_POOL_STRATEGY=small_queue_pool|null_pool` 之间做线上 A/B。
第二步：用真实 Supabase 环境执行 `python backend/scripts/db_connection_mode_probe.py --output backend/docs/artifacts/db_connection_mode_probe.json`，比较 p50/p95/p99 与 timeout count。
第三步：在联调时观察 `/health/runtime`，确认 `db_connect_timeouts`、`auth_cache_hit`、`pool_checked_out` 和 `circuit_state` 是否符合预期。
