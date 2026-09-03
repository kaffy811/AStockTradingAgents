---
目前完成的工作汇总：

已完成

1. Phase 6T-S duplicate claim 诊断修复
- 修改 `backend/scripts/company_v2_financial_fusion_phase6ts_shadow_soak.py`。
- 将 `duplicate_claim_count` 从“同一 job 被再次 claim”改为“有效 lease 时间区间重叠的 claim”。
- 新增 `reclaim_after_restart_count`，用于记录 lease 已过期后的合法 restart/reconnect reclaim。
- 新增 `duplicate_claim_events` 和 `claim_reclaim_events`，记录 job_id、两个 worker_id、claim 时间、lease 过期时间、overlap、reclaim_reason、requester_run_id。

2. Artifact 安全诊断
- 扩展 artifact sanitizer，避免失败 artifact 写入 `traceback_sanitized` 等可能包含本地路径的信息。
- secondary artifacts 同步输出新的 duplicate/reclaim 诊断字段。

3. Phase 6T-S 测试增强
- 修改 `backend/tests/fundamental/test_phase6ts_shadow_soak.py`。
- 新增合法 sequential reclaim 不计 duplicate 的单测。
- 新增真实 overlapping lease 会计入 duplicate 的单测。
- 修改 `backend/tests/fundamental/test_phase6ts_shadow_soak_live.py`。
- live 断言现在带字段名和完整 metrics 上下文，便于下一次失败定位。

4. 验证结果
- Phase 6T-S hermetic：17 passed。
- Phase 6T-S hermetic + key live：18 passed。
- live restart/reconnect 单测连续 10 次：10/10 passed。
- full hermetic：3154 passed, 15 deselected。
- full suite：3169 passed。

---
下一步：你需要操作

第一步：如需复核关键 live 稳定性，执行：
`cd backend && for i in 1 2 3 4 5 6 7 8 9 10; do .venv/bin/python -m pytest -q tests/fundamental/test_phase6ts_shadow_soak_live.py::test_live_shadow_soak_short_run_with_restart_and_reconnect || exit $?; done`

第二步：如需查看最新 shadow soak artifact，打开：
`backend/docs/artifacts/company_v2_phase6ts_gate.json`

第三步：提交时建议使用：
`fix(company-v2): make shadow soak restart claim metrics deterministic`
