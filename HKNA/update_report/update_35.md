---
Phase 6T-Q manual admission vs automatic dispatch separation

本次修复点

1. 修复 `company_v2_financial_fusion_job_service.create_job()` 在 HTTP manual create 场景下仍被全局 rollout disable 拦截的问题。
2. 新增更窄的 `manual_admission` 语义，只允许 allowlist 手动入队，不复用 `force_enabled` 的过宽绕过能力。
3. 保持 `auto_run=False` 时不添加 `BackgroundTasks`。
4. 保持 `rollout_percent=0` 时不添加 `BackgroundTasks`。
5. 保持 duplicate active job 不重复 dispatch。
6. 保持非 allowlist symbol 不可用 manual admission 绕过基础安全约束。

验证结果

1. targeted tests: 12 passed
2. hermetic: 3053 passed, 9 deselected
3. live_supabase: 9 passed

说明

这是 manual admission 与 automatic dispatch 权限分离修复，不改变 Fusion 业务结果、RAG 语义或 job 入库/去重/提交路径。
