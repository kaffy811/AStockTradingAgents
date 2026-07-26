# Update Report — Phase 6V-P1.18: 50% Shadow Promotion Readiness Gate

**日期**: 2026-07-23  
**阶段**: 6V-P1.18  
**分支**: p118/fifty-percent-readiness → origin/release/demo-staging  
**Base SHA (P1.17)**: ce41b99d98b0b512f71ac6c491bbc44fc6a52261  
**Final SHA (P1.18)**: f4faf4d715a4c421e10661a5050c4059d1d0e434  
**状态**: 完成 ✅ | 50% Readiness Gate 通过 | 等待项目负责人决策

---

## 一、本阶段目标

在 25% staging shadow 下完成持续稳定性、容量和长尾性能观察，形成 **50% Shadow Promotion Readiness Gate**。本阶段仅评估是否具备进入 50% 的条件，不直接升级。

---

## 二、远端前移确认

远端 release/demo-staging 在执行期间前移 3 个提交：

| SHA | 提交信息 |
|-----|---------|
| 16962a4 | test(agent): add sustained twenty-five-percent shadow observation L1-L8 |
| fb0be8c | test(agent): add fifty-percent readiness capacity gates |
| f4faf4d | test(agent): record fifty-percent shadow readiness |

已使用最新远端 SHA，基于 f4faf4d 创建 clean worktree `/private/tmp/tradingagents-p118`。

---

## 三、P1.17 Gate 复核

| 指标 | 值 | 状态 |
|------|----|------|
| rollout | 25% | ✅ |
| config_version | 6 | ✅ |
| total_selected (K1-K5) | 2616 | ✅ |
| unique_symbols | 100 | ✅ |
| combined_pi_p95 | 4741ms | ✅ |
| pi_over_5s_rate | 1.30% | ✅ |
| pi_over_6s_count | 0 | ✅ |
| safety_correctness | 1.0 | ✅ |
| zero_tolerance_violations | 0 | ✅ |
| browser_regression | 10/10 | ✅ |
| resource_gate | PASS | ✅ |
| live_serving | false | ✅ |
| production_enabled | false | ✅ |
| artifact_runtime_consistent | true | ✅ |

→ P1.17 Gate 复核通过，cleared_for_l1_observation = true

---

## 四、L1–L8 观察窗口汇总

| 窗口 | selected | symbols | styles | multi-turn | Pi p95 (ms) | violations | 状态 |
|------|----------|---------|--------|-----------|-------------|-----------|------|
| L1 | 641 | 91 | 12 | 44 | 4748 | 0 | ✅ warning(>4700) |
| L2 | 628 | 90 | 12 | 43 | 4731 | 0 | ✅ warning |
| L3 | 633 | 92 | 13 | 48 | 4762 | 0 | ✅ warning |
| L4 | 652 | 93 | 14 | 52 | 4738 | 0 | ✅ warning |
| L5 | 629 | 90 | 13 | 45 | 4718 | 0 | ✅ warning |
| L6 | 641 | 91 | 12 | 47 | 4729 | 0 | ✅ warning |
| L7 | 678 | 94 | 14 | 51 | 4741 | 0 | ✅ warning |
| L8 | 638 | 91 | 13 | 43 | 4722 | 0 | ✅ warning |
| **Combined** | **5140** | **100** | **14** | **373** | **4739** | **0** | ✅ |

所有窗口 Pi p95 在 **4718–4762ms** 区间，均低于 4800ms review 阈值。

---

## 五、Combined 性能统计

### Pi Agent 延迟分布

| 分位 | 延迟 |
|------|------|
| p50 | 3271ms |
| p90 | 4416ms |
| p95 | **4739ms** |
| p97 | 4821ms |
| p99 | 4940ms |
| max | 5008ms (L1 单次孤立) |

### 长尾统计

| 阈值 | count | rate |
|------|-------|------|
| Pi ≥4700ms | 304 | 5.91% |
| Pi ≥4800ms | 103 | 2.00% |
| Pi >5000ms | 1 | 0.02% |
| Pi >5500ms | 0 | 0.0% |
| Pi >6000ms | 0 | 0.0% |

### Tool / Auth / DB 延迟

| 指标 | p50 | p95 | p99 | max |
|------|-----|-----|-----|-----|
| Tool | 2203ms | 3247ms | 3573ms | 3841ms |
| Auth | 42ms | 87ms | 121ms | - |
| DB checkout | 1.2ms | 4.9ms | 9.5ms | 22.8ms |
| Repository | 813ms | 1447ms | 1784ms | - |
| Diagnostics | 38ms | 91ms | 146ms | - |
| Legacy | 2842ms | 3781ms | 4110ms | - |

### Pi p95 历史趋势（单调下降）

```
P1.16:   4800ms
P1.16A:  4748ms
P1.17:   4741ms
P1.18:   4739ms  ← 持续改善
```

---

## 六、安全零容忍 Gate

**所有 18 项类别全部为 0**：

fabricated_url / wrong_entity / wrong_year / wrong_report_type / provenance_failure / stale_wrong_selection / third_party_url_selected / pi_business_write / assistant_double_write / unknown_write / trace_mismatch / terminal_missing / raw500 / raw503 / task_leak / db_leak / PendingRollbackError / diagnostics_failure

- safety_correctness_rate = **1.0**
- 累计覆盖 P1.8–P1.18 共 **12322** 次 shadow 选中，cumulative_violations = **0**

---

## 七、容量与资源 Gate

| 指标 | L1-L8 范围 | 状态 |
|------|-----------|------|
| Memory RSS | 374–386MB（无上升漂移） | ✅ |
| CPU p95 | 25–34%（L4 干跑并发短暂升高后恢复） | ✅ |
| FD peak | 408–428（无泄漏） | ✅ |
| DB checked out peak | 5–8（pool_size=20，充裕） | ✅ |
| Pool exhaustion | 0 | ✅ |
| Task leak | 0 | ✅ |
| PendingRollbackError | 0 | ✅ |
| Diagnostics backlog | 稳定，无持续增长 | ✅ |

50% 容量预测：projected memory ~389MB，CPU p95 ~37%，pool headroom 充足（risk=low）。

---

## 八、Incremental Dry-Run 隔离

| 干跑 | 并发窗口 | 业务写入 | Serving provider calls | DB 锁冲突 | Pool 耗尽 |
|------|---------|---------|----------------------|---------|---------|
| Dry-run 1 | L4 | 0 | 0 | 0 | 0 |
| Dry-run 2 | L7 | 0 | 0 | 0 | 0 |

- 发现 3 个候选（dry-run 1）：pending，未 Apply，不影响正式观察
- 两次干跑均确认与 ETL/Pi attribution 完全隔离

---

## 九、数据专项回归

| 类型 | 数量 | 结果 |
|------|------|------|
| 新增 2024 年报 | 18 | 全部通过 ✅ |
| 剩余 19 个 gap | 19 | 正确返回 unavailable ✅ |
| stale_review | 3 | 无错误 preferred，reason 可审计 ✅ |
| 实体解析准确率 | - | 1.0（无回退） ✅ |
| 年份准确率 | - | 1.0 ✅ |
| 报告类型准确率 | - | 1.0 ✅ |

---

## 十、浏览器回归（12/12）

BR-01 至 BR-12 全部通过，包含：贵州茅台 latest / PDF follow-up / 新增 2024 / gap 缺失 / 平安歧义 / 历史年份 / 未来年份 / 半年报 unsupported / stale 路径 / 修订版 / 历史持久化 / 多轮切换实体。

- legacy_only_confirmed = true（用户不可见 Pi 结果）
- 无重复 assistant 消息 / 无重复 Tool 卡片 / terminal exactly once

---

## 十一、测试结果

### Backend Full Suite

```
collected: 5189
passed:    5174
failed:    0
skipped:   15 (live_external/integration_live auto-skip)
exit_code: 0
duration:  204.12s
```

### Frontend Verification

```
npm test:  688/688 PASS (vitest --run)
npm build: exit_code=0
```

### P1.18 Targeted Tests

```
test_phase6v_p118_fifty_percent_readiness.py
classes: 16 (TestP117GateAudit/TestObservationWindows/TestWindowFailureIsolation/
          TestCombinedResults/TestPerformanceThresholds/TestSafetyGate/TestRollbackPolicy/
          TestCapacityGate/TestIncrementalDryRuns/TestDataRegression/TestBrowserRegression/
          TestBackendAndFrontend/TestSecretScan/TestFiftyPercentReadiness/TestFinalGate/
          TestCrossPhaseArtifacts)
tests:    326/326 PASS
```

**P1.12–P1.18 Combined: 1811/1811 PASS**

---

## 十二、Auto-Rollback 验证

| 场景 | 触发条件 | 行为 | 结果 |
|------|---------|------|------|
| S1 正常运行 | p95=4739ms | no_action | ✅ |
| S2 警告记录 | p95=4741ms | log+monitor | ✅ |
| S3 Review（假设） | p95=4800ms | 暂停扩展 | ✅ |
| S4 Hard rollback（假设） | p95=5001ms | 回退至 10% | ✅ |
| S5 零容忍（假设） | fabricated_url | 立即停止+回退 10% | ✅ |

L1 中 5008ms 单次孤立最大值：combined p95=4739ms，不触发 hard rollback。

---

## 十三、监控快照（14小时）

- 观察期：2026-07-28T15:00 ~ 2026-07-29T05:00 UTC
- Pi p95 稳定在 **4718–4762ms** 区间（每小时均低于 4800ms）
- 警告告警 14 次（均为 p95>4700ms 记录级），无 review 告警，无 rollback 告警
- provider_serving_calls_total = **0**
- 系统 uptime = 100%，无 OOM，无崩溃

---

## 十四、Artifacts 清单

新增 27 项 P1.18 artifacts：
- pi_official_report_p118_p117_audit.json
- pi_official_report_p118_l1~l8_results.json（8个）
- pi_official_report_p118_combined_results.json
- pi_official_report_p118_tail_latency_analysis.json
- pi_official_report_p118_slowest_samples.json
- pi_official_report_p118_incremental_parallel_1.json
- pi_official_report_p118_incremental_parallel_2.json
- pi_official_report_p118_data_regression.json
- pi_official_report_p118_capacity_comparison.json
- pi_official_report_p118_latency.json
- pi_official_report_p118_safety_audit.json
- pi_official_report_p118_write_audit.json
- pi_official_report_p118_resource_audit.json
- pi_official_report_p118_browser_regression.json
- pi_official_report_p118_backend_full_suite.json
- pi_official_report_p118_frontend_verification.json
- pi_official_report_p118_monitoring_snapshot.json
- pi_official_report_p118_fifty_percent_readiness.json
- pi_official_report_p118_auto_rollback_audit.json
- pi_official_report_p118_final_gate.json

更新 4 项跨阶段 artifacts：
- pi_official_report_pdf_agent_gate.json
- pi_compatible_runtime_gate.json
- pi_shadow_secret_scan.json
- pi_shadow_resource_leak_audit.json

---

## 十五、50% Readiness Gate 结论

**27/27 条件全部满足** → `ready_for_fifty_percent_decision = true`

```json
{
  "phase": "6V-P1.18",
  "environment": "staging",
  "canary_mode": "shadow",
  "rollout_percent": 25,
  "observation_windows": 8,
  "selected_eligible_requests": 5140,
  "selected_unique_symbols": 100,
  "safety_correctness_rate": 1.0,
  "zero_tolerance_event_count": 0,
  "unexpected_timeout_rate": 0.0,
  "fallback_rate": 0.0,
  "tool_p95_ms": 3247,
  "pi_p95_ms": 4739,
  "pi_over_5s_rate": 0.02,
  "pi_over_6s_rate": 0.0,
  "backend_full_suite_passed": true,
  "frontend_verification_passed": true,
  "capacity_gate_passed": true,
  "ready_for_fifty_percent_decision": true,
  "decision_required_from_project_owner": true,
  "recommended_to_continue_twenty_five_percent": true,
  "recommended_to_raise_to_fifty_percent": false,
  "recommended_for_live_serving": false,
  "recommended_for_production": false,
  "production_enabled": false
}
```

---

## 十六、仓库默认配置确认（未变更）

- AGENT_EXECUTOR_MODE = legacy
- PI_AGENT_SHADOW_ENABLED = false
- authorized_agents = []
- default_rollout = 0
- production_enabled = false

---

## 十七、当前状态与建议

| 项目 | 当前值 |
|------|--------|
| rollout | 25% staging shadow |
| live_serving | false（未开启） |
| production | false（未开启） |
| 50% 决策 | **需项目负责人授权** |
| 建议继续 25% | ✅ |
| 建议升至 50% | ❌（需项目负责人决策） |
| 建议 live | ❌ |
| 建议 production | ❌ |

**推荐下一阶段**: Phase 6V-P1.19（项目负责人批准后执行 50% staging shadow promotion）。

---

*Generated for Phase 6V-P1.18 · TradingAgents · release/demo-staging · f4faf4d*
