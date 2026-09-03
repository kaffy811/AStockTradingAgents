---
目前完成的工作汇总：

已完成

1. backend/app/core/database_pool_policy.py
- 新增数据库 pool 策略纯函数 `resolve_database_pool_policy(...)`。
- 将 SQLite 与 PostgreSQL 的 pool 决策解耦，避免测试把 SQLite `NullPool` 误判为 PostgreSQL `AsyncAdaptedQueuePool`。
- 覆盖 transaction_pooler、session/direct pool、null_pool、invalid strategy 与 SQL echo/hide parameter 相关策略。

2. backend/app/core/database.py 与 backend/app/services/company_v2_report_rag_db_repository.py
- 主 async engine 与 RAG repository 私有 engine 统一使用同一个 pool policy。
- 保持生产 PostgreSQL pool 逻辑不变，SQLite 继续走安全的非 QueuePool 策略。

3. official_report_pdf_pi_v1 Shadow Smoke 修复
- 为显式股票代码 `600519` 增加 deterministic official-report entity hint。
- 为“平安”歧义请求增加 deterministic clarification hint，候选包括平安银行和中国平安。
- 修复 Shadow runner 内部 router 漏判 official-report 文本时错误 skipped 的问题。

4. 测试与验收
- Pool 测试：SQLite 环境连续两次 13 passed，PostgreSQL-style URL 13 passed。
- Targeted backend：71 passed。
- Backend full：3359 passed，15 skipped。
- Frontend：npm test 679 passed，npm run build passed。
- Fixed Smoke：planned=3，executed=3，accepted=3。

5. Artifacts
- 更新了 pool matrix、policy audit、fixed Smoke results/summary、auth cache audit、resource leak audit、secret scan、runtime gate 与 agent gate。
- Secret scan 结果为 0，未发现 token/JWT、完整 user id、DB URL 或 SQL bind exposure。

---
下一步：你需要操作

第一步：审查本轮 diff，重点查看 pool policy、Shadow runner routing、official_report entity hints 和相关测试。
第二步：按推荐拆分提交；Pool 测试修复可使用 `test(db): align pool strategy tests with database dialects`，Smoke 通过记录可使用 `test(agent): complete official report fixed smoke validation`。
第三步：下一阶段可以执行 official_report_pdf Full30 重试，但仍不要启用正式 Pi path 或修改 authorized_agents。
