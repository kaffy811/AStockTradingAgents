---
Phase 6T-Q dispatch safety gate fix

本次修复点

1. 修复 `app/routers/company_v2_financial_fusion.py` 的后台任务触发条件。
2. 现在只有在 `auto_run=True` 且 `rollout_percent>0` 且非 duplicate 时，才会把 `run_job()` 加入 `BackgroundTasks`。
3. `auto_run=False` 时，POST 仍然创建 `queued` job，但不会自动 dispatch。
4. `rollout_percent=0` 时，不会 dispatch。
5. duplicate active job 不会重复 dispatch。

验证结果

1. targeted tests: 7 passed
2. hermetic: 3051 passed, 9 deselected
3. live_supabase: 9 passed

说明

这次修复只影响 HTTP dispatch safety gate，没有修改 Fusion 业务结果、RAG 语义、job admission 的入库/去重/提交路径。
