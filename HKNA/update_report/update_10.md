---
目前完成的工作汇总：

已完成

1. Phase 6T-S shadow soak 作用域隔离修复
- 在 `backend/app/services/company_v2_financial_fusion_worker_service.py` 中收窄 claim 语义，支持 `requester_scope`、`requester_run_id` 和 `allowed_job_ids` 过滤，并在 claim 后做二次校验，避免未知 queued job 被改写。
- `evaluate_shadow_job` 和 `run_shadow_cycle` 继续沿用同一组作用域约束，保持默认 worker 行为兼容。

2. Phase 6T-S soak runner 绑定本轮 run_id
- 在 `backend/scripts/company_v2_financial_fusion_phase6ts_shadow_soak.py` 中将 worker 调用链绑定到本轮 `run_id` 与本轮 `job_id` 白名单。
- 增加 scope/run_id 校验 helper，发现越界 job 时 fail-fast，记录 `SOAK_CLAIM_SCOPE_ISOLATION_FAILED`。

3. 新增 scope 隔离回归测试
- 更新 `backend/tests/fundamental/test_phase6ts_shadow_soak.py`，覆盖 worker 过滤参数传递、scope 校验 helper 和 hermetic soak 路径。
- 更新 `backend/tests/fundamental/test_phase6ts_shadow_soak_live.py`，用真实 PostgreSQL 断言仅当前 run_id 的 soak job 会被 claim，旧 queued job 保持未改写。
- 更新 `backend/tests/fundamental/test_phase6tr_worker_foundation.py`，兼容新增可选参数，不破坏旧 worker foundation 测试。

4. 安全恢复工具
- 新增 `backend/scripts/company_v2_financial_fusion_phase6ts_shadow_soak_recovery.py`，默认只读审计 `phase6ts-worker-*` 的 claim 状态，只有显式 `--release-known-claims` 才允许释放已知 claim。

5. Phase 6T-S gate 回收
- 更新 `backend/docs/artifacts/company_v2_phase6ts_gate.json` 和 `.md`，将当前状态回收为失败态，标记 `SOAK_CLAIM_SCOPE_ISOLATION_FAILED`，避免继续把有 scope 泄漏风险的结果标成通过。

6. 验证结果
- hermetic 后端回归通过：`3078 passed, 15 deselected`。
- 已完成本次修复相关的定向测试通过。

---
下一步：你需要操作

第一步：在具备 live Supabase DNS/连通性的 same-region runner 上重新跑 `tests/fundamental/test_phase6ts_shadow_soak_live.py`，确认 claim 只命中本轮 run_id。
第二步：如需人工恢复误 claim 的历史 job，使用 `backend/scripts/company_v2_financial_fusion_phase6ts_shadow_soak_recovery.py --run-id <run_id> --known-job-ids <job_ids> --release-known-claims`，先做只读审计，再显式释放。
第三步：如果 live 验证通过，再更新 phase6ts gate 到通过态；如果仍发现越界 claim，保持 gate false 并继续追踪日志。
