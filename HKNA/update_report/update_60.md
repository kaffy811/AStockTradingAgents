---
目前完成的工作汇总：

已完成

1. `backend/app/core/runtime_reliability.py`
- 扩大 Auth DB unavailable 捕获范围，覆盖 built-in `TimeoutError`、`asyncio.TimeoutError`、SQLAlchemy timeout/DBAPI/OperationalError 以及相关 `OSError`。
- `CancelledError` 继续向上传播，invalid token 仍为 401，disabled user 仍为 403。
- 503 payload 统一为 `AUTH_DATABASE_UNAVAILABLE`，包含 `retryable=true` 与 `Retry-After: 3`。
- 增加 auth cache/singleflight 指标，10 个并发同用户请求最多一次 DB lookup。

2. `backend/app/services/company_chat_data_service.py`
- 新增 Chat 复用 Company 页面数据的共享 adapter。
- 分别返回 `quote_snapshot`、`company_profile`、`financial_snapshot`、`financial_history`、`market_history` availability。
- 避免把“行情历史趋势不足”误判为整家公司无数据。

3. `backend/app/agents/chat_skills/report_comparison_skill.py`
- 报告选择、RAG、结构化抽取任一 DB/RAG 异常时，落到 Company V2 cached snapshot/history。
- 在 RAG 不可用但 Company 页面已有结构化财务数据时返回 `partial_success`。
- 明确提示“报告原文核验暂不可用”，不说五粮液无数据，不填 0，不让模型补造缺失数字。

4. `backend/scripts/db_connection_mode_probe.py`
- A/B probe 增加 `checkout_connect_ms` 与 `query_ms` 分阶段耗时。
- 说明 DNS/TCP/SSL/Supavisor 在 asyncpg/SQLAlchemy 中属于 connection phase，避免只看 total latency。

5. 前端 503 降级
- 现有 `frontend/src/api/http.js` / `frontend/src/api/chat.js` 继续保持：503 不清登录态、不跳登录页，向 UI 暴露可重试错误。

6. 测试与验证
- E0/E0.1 targeted backend：`25 passed, 1 warning`。
- Frontend Vitest：`679 passed`。
- Frontend build：passed。
- Python compileall：passed。
- Full backend：`3255 passed, 15 failed, 299 warnings`；剩余失败均为 live Supabase/RAG/worker 连接依赖，首个失败仍在 pooler DNS/连接建立阶段。

---
下一步：你需要操作

第一步：用真实登录态重试 Chat 追问“那它和五粮液相比呢”，确认 DB 连接异常时前端显示账户验证服务可重试提示而非裸 500。
第二步：打开 `/stocks/CN/000858` 后再发起比较问题，确认 RAG DB 不可用时至少返回 Company 页面缓存的 partial comparison。
第三步：执行 `python backend/scripts/db_connection_mode_probe.py --output backend/docs/artifacts/db_connection_mode_probe.json`，用 `checkout_connect_ms` 与 `query_ms` 判断慢点是否仍在连接建立阶段。
