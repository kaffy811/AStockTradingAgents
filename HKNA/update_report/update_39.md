---
目前完成的工作汇总：

已完成

1. Phase 6T-S shadow claim 重试预算修复
- 修改 `backend/app/services/company_v2_financial_fusion_worker_service.py`，shadow mode claim 不再递增真实 `attempt_count`。
- shadow claim 不再受 `attempt_count < max_attempts` 限制；真实 `attempt_count` 继续只服务 canary/rollout 的真实执行语义。
- shadow 次数改由 worker observation 记录和 soak metrics 的 `shadow_observation_count` 表达。

2. Phase 6T-S soak runner 生命周期修复
- 修改 `backend/scripts/company_v2_financial_fusion_phase6ts_shadow_soak.py`，主生命周期由 `duration_seconds` 和 monotonic clock 控制。
- 没有 eligible job 时 worker 继续 sleep/poll，不再让 soak 提前结束。
- worker task 结束或异常后由 main 记录错误并重启 worker，DB reconnect 后继续运行到截止时间。

3. artifact 与 cleanup 修复
- 启动时立即写入 `status=running`、`run_id`、`started_at`、`requested_duration_seconds`，覆盖旧 artifact，避免旧结果被误判为本轮结果。
- finally 路径写入 passed/failed artifact，包含 `run_id`、`started_at`、`finished_at`、`actual_duration_seconds`、`process_pid` 和 `git_commit`。
- cleanup 只释放本 run 创建的 leases，只取消本 run 创建的测试 jobs；cleanup 失败也写入 artifact errors。

4. live Supabase schema 兼容修复
- 修改 `backend/app/services/company_v2_financial_fusion_job_service.py`，将 `worker_observations.job_id` 索引保证为非唯一索引，允许同一 job 多次 shadow observation。
- 新增 Alembic migration `backend/alembic/versions/2026_07_14_0001-l0m1n2o3p4q5_phase6ts_shadow_observation_index.py`，固化 observation job_id 非唯一索引。

5. 回归测试补充
- 更新 `backend/tests/fundamental/test_phase6tr_worker_foundation.py`，覆盖 shadow claim 不递增 `attempt_count`，真实执行才递增，以及 max_attempts 不阻断 shadow。
- 更新 `backend/tests/fundamental/test_phase6ts_shadow_soak.py`，覆盖 3 秒 duration、无 eligible job 继续轮询、worker 异常失败 artifact、SIGTERM cleanup、running artifact 覆盖旧 run_id。
- 更新 `backend/tests/fundamental/test_phase6ts_shadow_soak_live.py`，覆盖 live run_id claim 隔离和 live shadow soak 完整结束。

6. Gate 状态回收
- 更新 `backend/docs/artifacts/company_v2_phase6ts_gate.json` 和 `.md`，保持 `phase6ts_passed=false`、`shadow_soak_completed=false`、`stage3_status=not_authorized`。
- blocking issue 固定为 `SHADOW_SOAK_EXITED_BEFORE_REQUESTED_DURATION`，不授权 Stage 3，不进入 Canary，不执行真实 Fusion。

7. 验证结果
- 定向回归通过：`21 passed, 2 warnings`。
- live foundation + shadow soak 回归通过：`6 passed, 5 warnings`。
- full backend tests 通过：`3101 passed, 261 warnings`。
- 180 秒 live smoke 通过：`status=passed`，`run_id=0654cd6c5f834f78a90eccd44f22d471`，`actual_duration_seconds=195.005`，`jobs_created=5`，`jobs_cancelled=5`，`active_leases_end=0`，`stale_leases_end=0`，`real_execution_count=0`。

---
下一步：你需要操作

第一步：复核 `backend/docs/artifacts/company_v2_phase6ts_gate.json`，确认 7200 秒 Gate 仍为失败态且 Stage 3 未授权。
第二步：复核 `backend/docs/artifacts/company_v2_phase6ts_shadow_soak.json`，确认最终 smoke artifact 属于 run_id `0654cd6c5f834f78a90eccd44f22d471`。
第三步：提交时使用 commit message：`fix(company-v2): keep Phase 6T-S shadow soak alive for requested duration`。
