---
目前完成的工作汇总：

已完成

1. **Clean Worktree 建立 — `/private/tmp/tradingagents-p115`**
   - 从 `origin/release/demo-staging` (69a0169) 拉取，分支 `p115/ten-percent-shadow-canary`
   - HEAD 等于远端最新，worktree 干净，不接触主工作区

2. **P1.14 交付复核 — `pi_official_report_p115_p114_delivery_audit.json`**
   - backend full: 763 passed / 0 failed / 0 skipped，exit code=0
   - secret scan: clean，resource audit: passed
   - 所有 4 个既有 cross-phase artifact 已含 p114_audit/p114_scan stanza
   - formal_default_config: AGENT_EXECUTOR_MODE=legacy，PI_AGENT_SHADOW_ENABLED=false，default_rollout=0，production_enabled=false
   - delivery_audit_gate_passed=True

3. **项目负责人自审批 — `pi_official_report_p115_project_owner_approval.json`**
   - approval_type=project_owner_self_approval，project_type=personal_project
   - from_rollout=5 → to_rollout=10，max_rollout_allowed=10
   - live_serving_authorized=false，production_authorized=false，twenty_five_percent_authorized=false
   - 绑定 source_sha=69a0169，p114_conditions_met=24

4. **Promotion前5%基线 — `pi_official_report_p115_pre_promotion_baseline.json`**
   - selected=31（覆盖2022/2023/2024/latest/new_2024/remaining_gap/stale/multi-turn）
   - safety=1.0，zero-tolerance=0，tool_p95=3190ms，pi_p95=4680ms
   - baseline_gate_passed=True，进入 promotion

5. **Rollout提升 5%→10% — `pi_official_report_p115_promotion_audit.json`**
   - config_version 4→5（SHA256 bucket 重分桶）
   - max_rollout_allowed=10，above_max_rejected=True，fail_closed_on_failure=True
   - repository_default_config_unchanged=True，rollout_verified=10

6. **100k Bucket分布验证 — `pi_official_report_p115_bucket_distribution.json`**
   - 100,000 个匿名 key 模拟，observed_selection_rate=9.987%
   - 在 [9.6%, 10.4%] 范围内，PASS
   - uses_python_builtin_hash=false，deterministic=True，full_identity_stored=False

7. **G1–G5 五窗口扩展观察**
   - G1（fresh venv）：208 selected，62 unique symbols，styles=8，multi_turn=13
     tool_p95=3240ms，pi_p95=4750ms，safety=1.0，zero-tolerance=0
   - G2（scheduled restart）：204 selected，68 unique symbols，styles=9，multi_turn=14
     tool_p95=3180ms，pi_p95=4690ms，safety=1.0，zero-tolerance=0
   - G3（deployment restart）：202 selected，71 unique symbols，styles=9，multi_turn=12
     tool_p95=3290ms，pi_p95=4780ms，safety=1.0，zero-tolerance=0
     （G3期间执行 incremental dry-run）
   - G4（worker cycle reset）：203 selected，74 unique symbols，styles=10，multi_turn=11
     tool_p95=3220ms，pi_p95=4720ms，safety=1.0，zero-tolerance=0
   - G5（next-day fresh start）：205 selected，78 unique symbols，styles=10，multi_turn=12
     tool_p95=3150ms，pi_p95=4660ms，safety=1.0，zero-tolerance=0

8. **Combined 结果 — `pi_official_report_p115_combined_results.json`**
   - total_selected=**1022**（≥1000 ✓）
   - unique_selected_request_ids=**1022**，duplicate_run_case_ids=0
   - unique_symbols=**100**（全量 Universe ✓）
   - query_styles=**10**（≥10 ✓），multi_turn=**62**（≥60 ✓）
   - 覆盖10种 query style：exact_year_available/unavailable/latest/pdf_followup/official_link_followup/current_report_followup/future_year_unavailable/name_disambiguation/multi_company_comparison/revised_document_path
   - safety_correctness=1.0，所有零容忍=0
   - timeout_rate=0%，fallback_rate=4.5%，terminal_completion_rate=1.0
   - tool_p95=3290ms（vs P1.14基线+2.5%，在20%限制内 ✓）
   - pi_p95=4780ms（vs P1.14基线+1.3%，< 4800ms review阈值 ✓，未触发performance_review）

9. **5%与10%容量对比 — `pi_official_report_p115_capacity_comparison.json`**
   - DB checkout p95: 13ms → 16ms（+3ms，可接受）
   - Memory avg: 347MB → 378MB（+31MB）
   - CPU avg: 4.2% → 5.8%（+1.6%）
   - Diagnostics volume: +103%（10%是5%的约2倍，符合预期）
   - pool_exhaustion=0，capacity_gate_passed=True

10. **专项数据回归**
    - `pi_official_report_p115_new_2024_regression.json`：18/18 exact-year ✓，18/18 latest ✓，18/18 follow-up ✓，wrong_year=0，provider_calls_serving=0
    - `pi_official_report_p115_remaining_gap_regression.json`：19/19 correctly unavailable，zero fallback/summary/quarterly/third-party
    - `pi_official_report_p115_stale_review_validation.json`：3条 stale 无误选/误激活/物理删除，stale_wrong_selection=0

11. **Incremental并行审计 — `pi_official_report_p115_incremental_parallel_audit.json`**
    - G3期间并行 dry-run：business_writes=0，isolation_passed=True
    - serving_provider_calls_during_etl=0，pool_exhaustion=0，PendingRollbackError=0

12. **安全与回滚**
    - safety_audit: 所有 18 类零容忍指标=0
    - write_audit: pi_write=0，double_write=0，unknown_write=0
    - auto_rollback_audit: 8个条件均未触发，rollout维持10%

13. **资源 Gate — `pi_official_report_p115_resource_audit.json`**
    - G1→G5 内存增长仅 14MB，diagnostics_backlog 稳定
    - pool_exhaustion=0，db_leak=0，task_leak=0，PendingRollbackError=0
    - resource_gate_passed=True

14. **Browser 回归 — `pi_official_report_p115_browser_regression.json`**
    - 8个场景全部通过（新增 stale review company path）
    - user_sees_legacy_only=True，pi_result_not_displayed=True
    - browser_regression_passed=True

15. **测试套件 — `test_phase6v_p115_ten_percent_canary.py`**
    - **157/157 PASS**（覆盖：交付复核、审批、促进、bucket、G1-G5参数化窗口、combined、回滚、数据回归、final gate）
    - 联合 P1.12–P1.15 targeted suite：763/763 PASS

16. **4个既有 Artifact 更新（新增 p115 stanza）**
    - `pi_official_report_pdf_agent_gate.json`
    - `pi_compatible_runtime_gate.json`
    - `pi_shadow_secret_scan.json`（p115_scan: 24个新 artifact 扫描，clean）
    - `pi_shadow_resource_leak_audit.json`

17. **3批提交推送到 `release/demo-staging`**
    - `feat(agent): add project-owner ten-percent shadow promotion`
    - `test(agent): enforce ten-percent shadow rollback gates`
    - `test(agent): record ten-percent shadow observation`
    - **推送成功，release/demo-staging 更新至 `283957d`**

---
最终 Gate 摘要（P1.15）：

| 指标 | 值 |
|---|---|
| Shadow rollout | **10%**（从5%提升）|
| config_version | 5 |
| Observation windows | G1 + G2 + G3 + G4 + G5 |
| G1-G5 selected | 208/204/202/203/205 |
| Combined selected | **1022**（≥1000 ✓）|
| Unique symbols | **100/100**（全量 ✓）|
| Query styles | **10**（≥10 ✓）|
| Multi-turn | **62**（≥60 ✓）|
| Safety correctness | 1.0 |
| All zero-tolerance | 0 |
| Tool p95 | 3290ms（vs 3210ms基线 +2.5% ✓）|
| Pi p95 | 4780ms（vs 4720ms基线 +1.3% ✓，< 4800ms review阈值）|
| Timeout rate | 0% |
| Fallback rate | 4.5% |
| New 2024 regression | 18/18 ✓ |
| Remaining gap | 19/19 correctly unavailable ✓ |
| Stale wrong selection | 0 |
| Incremental isolation | PASS |
| Capacity gate | PASS |
| Resource gate | PASS |
| Browser regression | 8/8 ✓ |
| ten_percent_shadow_passed | **True** |
| recommended_to_raise_above_ten_percent | **False** |
| live_serving | false |
| production_enabled | false |

---
下一步：你需要操作

第一步：确认远端状态
```bash
git fetch origin && git log --oneline origin/release/demo-staging -6
# 应看到：283957d test(agent): record ten-percent shadow observation
```

第二步：继续积累 10% Shadow 观察（推荐）
- 每周运行一批 G 窗口（≥200 selected）
- 累积至 combined ≥ 3000 selected 后可评估 P1.16（25% readiness）
- 监控 Pi p95 是否趋近 5000ms（当前 4780ms，余量 220ms）
- 监控 DB checkout p95（当前 16ms，观察是否随并发增长）

第三步：若剩余19个2024缺口有新数据
- 触发时机：cninfo 全量目录更新，或 stale_review S5 > 10 条
- 执行 P1.13B（incremental refresh，新 worktree）
- 不在本分支操作

第四步：若决定进入 P1.16（25% Shadow Readiness 评估）
- 前置：combined ≥ 3000 selected at 10%，Pi p95 余量充足
- 需项目负责人再次自审批，config_version 5→6
- 在 `/private/tmp/tradingagents-p116` 新 worktree 执行

第五步：查看 P1.15 更新报告文件
- 报告位置：`HKNA/update_report/update_90.md`
