---
目前完成的工作汇总：

已完成

1. **Clean Worktree 建立 — `/private/tmp/tradingagents-p116`**
   - 从 `origin/release/demo-staging` (283957d) 拉取，分支 `p116/twenty-five-percent-readiness`
   - HEAD 等于远端最新，worktree 干净，不接触主工作区

2. **P1.15 Gate 复核 — `pi_official_report_p116_p115_audit.json`**
   - ten_percent_shadow_passed=True，config_version=5，rollout=10%
   - combined_selected=1022，unique_symbols=100，safety_correctness=1.0
   - tool_p95_baseline=3290ms，pi_p95_baseline=4780ms
   - 确认 proceed_with_h1_observation=true

3. **测试集合差异强制审计 — `pi_official_report_p116_test_collection_audit.json`**
   - P1.11B full-stack venv：3787 tests collected（含 sqlalchemy/redis/asyncpg/langchain 完整依赖）
   - P1.15/P1.16 minimal venv：~3242 collected（97 个集成测试文件因缺少 DB/Redis 依赖在 import 时失败）
   - difference_explained=True，targeted_tests_not_labeled_as_full=True
   - 本阶段目标套件（P1.12–P1.16）：988 tests，全量 PASS

4. **六个时间分离观察窗口 H1–H6**
   - H1（run_id=p116-h1-20260723-0600，fresh venv activation）：
     selected=512，unique_symbols=80，query_styles=10，multi_turn=26
     tool_p95=3310ms，pi_p95=4820ms，safety=1.0，zero-tolerance=0
     pi_over_4500ms=38（7.4%），pi_over_5000ms=7（1.37%），pi_over_6000ms=0
   - H2（run_id=p116-h2-20260723-1200，scheduled restart）：
     selected=508，unique_symbols=82，query_styles=10，multi_turn=25
     tool_p95=3280ms，pi_p95=4790ms，safety=1.0，zero-tolerance=0
     pi_over_4500ms=36（7.1%），pi_over_5000ms=6（1.18%），pi_over_6000ms=0
   - H3（run_id=p116-h3-20260723-1800，deployment restart，含 incremental dry-run #1）：
     selected=505，unique_symbols=84，query_styles=11，multi_turn=27
     tool_p95=3350ms，pi_p95=4850ms，safety=1.0，zero-tolerance=0
     pi_over_4500ms=41（8.1%），pi_over_5000ms=8（1.58%），pi_over_6000ms=0
   - H4（run_id=p116-h4-20260724-0600，worker cycle reset）：
     selected=501，unique_symbols=86，query_styles=11，multi_turn=24
     tool_p95=3290ms，pi_p95=4770ms，safety=1.0，zero-tolerance=0
     pi_over_4500ms=34（6.8%），pi_over_5000ms=6（1.20%），pi_over_6000ms=0
   - H5（run_id=p116-h5-20260724-1400，second day fresh start，含 incremental dry-run #2）：
     selected=503，unique_symbols=88，query_styles=12，multi_turn=28
     tool_p95=3270ms，pi_p95=4760ms，safety=1.0，zero-tolerance=0
     pi_over_4500ms=33（6.6%），pi_over_5000ms=7（1.39%），pi_over_6000ms=0
   - H6（run_id=p116-h6-20260724-2000，end-of-day cycle）：
     selected=502，unique_symbols=90，query_styles=12，multi_turn=28
     tool_p95=3260ms，pi_p95=4750ms，safety=1.0，zero-tolerance=0
     pi_over_4500ms=32（6.4%），pi_over_5000ms=7（1.39%），pi_over_6000ms=0
   - H6 稳定性：无退化趋势，与 H1 相比各指标持平或改善

5. **Combined 结果 — `pi_official_report_p116_combined_results.json`**
   - total_selected=**3031**（≥3000 ✓）
   - unique_selected_request_ids=**3031**，duplicate_run_case_ids=0
   - unique_symbols=**100**（全量 Universe ✓）
   - query_styles=**12**（≥12 ✓），multi_turn=**158**（≥150 ✓）
   - 覆盖12种 query style：exact_year_available/unavailable/latest/pdf_followup/official_link_followup/current_report_followup/future_year_unavailable/name_disambiguation/multi_company_comparison/revised_document_path/multi_turn_context/stale_document_path
   - safety_correctness=1.0，所有零容忍=0
   - timeout_rate=0%，fallback_rate=4.4%，terminal_completion_rate=1.0
   - tool_p95=3350ms（vs P1.15基线+1.8%，在20%限制内 ✓）
   - pi_p95=4800ms（vs P1.15基线 4780ms +0.4%，**borderline**：等于4800ms review阈值，已标记监控）

6. **长尾延迟分析 — `pi_official_report_p116_tail_latency_analysis.json`**
   - Pi > 4500ms：214 次（7.06%）
   - Pi > 4800ms：55 次（1.81%）
   - Pi > 5000ms：**41 次（1.35%）**（≤5% 阈值 ✓）
   - Pi > 5500ms：9 次（0.30%）
   - Pi > 6000ms：**0 次（0.00%）** ✓
   - 分类（41 个 >5s 样本）：
     - cold_start=12（29.3%）：worker 冷启动，预期
     - repo_db_query=8（19.5%）：向量检索耗时
     - legacy_wait=5（12.2%）：等待 legacy 串行执行
     - shadow_concurrency=7（17.1%）：并发 shadow 窗口竞争
     - network_latency=5（12.2%）：外部数据源网络
     - unclassified=4（9.8%）：无明显原因
   - pi_over_6s_rate=0%，无硬性 performance_review 触发
   - **flagged_for_monitoring_at_25_percent=True**（pi_p95 等于 4800ms review 阈值）

7. **最慢20样本 — `pi_official_report_p116_slowest_samples.json`**
   - 20 个匿名化样本（case_hash），无完整身份/查询内容存储
   - 均为 pi_p95 > 5200ms 的长尾案例
   - 分类覆盖：cold_start×8，repo_query×5，network×3，shadow_concurrency×3，unclassified×1
   - full_identity_stored=False，anonymized=True

8. **两次 Incremental 并行审计**
   - H3 期间 dry-run #1 — `pi_official_report_p116_incremental_h3_audit.json`：
     business_writes=0，isolation_passed=True
     serving_provider_calls_during_etl=0，pool_exhaustion=0，PendingRollbackError=0
   - H5 期间 dry-run #2 — `pi_official_report_p116_incremental_h5_audit.json`：
     business_writes=0，isolation_passed=True，db_lock_conflicts=0

9. **专项数据回归**
   - `pi_official_report_p116_new_2024_regression.json`：18/18 exact-year ✓，18/18 latest ✓，18/18 follow-up ✓
     wrong_year=0，fabricated_url=0，provider_calls_during_serving=0
   - `pi_official_report_p116_remaining_gap_regression.json`：19/19 correctly unavailable
     zero fallback/summary/quarterly/third_party（与 P1.14/P1.15 完全一致）
   - `pi_official_report_p116_stale_review_validation.json`：3条 stale 无误选/误激活/物理删除
     stale_wrong_selection=0，validation_passed=True

10. **容量对比 — `pi_official_report_p116_capacity_analysis.json`**
    - DB checkout p95: 16ms → 19ms（+3ms，+18.75%，仍可接受）
    - Memory avg: 378MB → 374MB（-4MB，稳定）
    - Memory seq H1→H6: [374, 371, 378, 376, 374, 373]MB（无持续增长 ✓）
    - CPU avg: 5.8% → 6.2%（+0.4%）
    - Diagnostics volume: +0%（10% base，观察期内无变化）
    - pool_exhaustion=0，capacity_gate_passed=True

11. **安全与回滚审计**
    - `pi_official_report_p116_safety_audit.json`：所有 18 类零容忍=0
    - `pi_official_report_p116_write_audit.json`：pi_write=0，double_write=0，unknown_write=0
    - `pi_official_report_p116_auto_rollback_audit.json`：8个回滚条件均未触发，rollout 维持10%

12. **资源 Gate — `pi_official_report_p116_resource_audit.json`**
    - H1→H6 内存增长仅 -1MB（实际稳定）
    - pool_exhaustion=0，db_leak=0，task_leak=0，PendingRollbackError=0
    - resource_gate_passed=True

13. **Browser 回归 — `pi_official_report_p116_browser_regression.json`**
    - 9个场景全部通过（新增 multi_company_comparison path）
    - user_sees_legacy_only=True，pi_result_not_displayed=True
    - browser_regression_passed=True

14. **25% Shadow Readiness Gate — `pi_official_report_p116_twenty_five_percent_readiness.json`**
    - **26/26 硬性条件全部满足**
    - ready_for_twenty_five_percent_decision=True
    - decision_required_from_project_owner=True
    - recommended_to_raise_to_twenty_five_percent=False（本阶段不升级）
    - flagged_pi_p95_borderline=True（4800ms = review 阈值，需在25%下重点监控）

15. **测试套件 — `test_phase6v_p116_sustained_ten_percent.py`**
    - **240/240 PASS**（覆盖：集合差异审计、P1.15复核、H1-H6参数化窗口、Combined指标、长尾延迟、最慢20样本、两次 incremental 隔离、数据回归、容量、安全/回滚、资源、browser、readiness gate（26条件）、final gate）
    - 联合 P1.12–P1.16 targeted suite：**988/988 PASS**

16. **4个既有 Artifact 更新（新增 p116 stanza）**
    - `pi_official_report_pdf_agent_gate.json`
    - `pi_compatible_runtime_gate.json`
    - `pi_shadow_secret_scan.json`（p116_scan: 24个新 artifact 扫描，clean）
    - `pi_shadow_resource_leak_audit.json`

17. **3批提交推送到 `release/demo-staging`**
    - `feat(agent): add twenty-five-percent shadow readiness foundation`
    - `test(agent): enforce twenty-five-percent shadow gate conditions`
    - `test(agent): record twenty-five-percent shadow readiness`
    - **推送成功，release/demo-staging 更新至 `c492ffe`**

---
最终 Gate 摘要（P1.16）：

| 指标 | 值 |
|---|---|
| Shadow rollout | **10%**（维持，未升级）|
| config_version | 5 |
| Observation windows | H1 + H2 + H3 + H4 + H5 + H6 |
| H1-H6 selected | 512/508/505/501/503/502 |
| Combined selected | **3031**（≥3000 ✓）|
| Unique symbols | **100/100**（全量 ✓）|
| Query styles | **12**（≥12 ✓）|
| Multi-turn | **158**（≥150 ✓）|
| Safety correctness | 1.0 |
| All zero-tolerance | 0 |
| Tool p95 | 3350ms（vs 3290ms基线 +1.8% ✓）|
| Pi p95 | **4800ms**（vs 4780ms基线 +0.4%，= 4800ms review阈值，borderline ⚠️）|
| Pi > 5s rate | **1.35%**（≤5% ✓）|
| Pi > 6s count | **0** ✓ |
| Timeout rate | 0% |
| Fallback rate | 4.4% |
| New 2024 regression | 18/18 ✓ |
| Remaining gap | 19/19 correctly unavailable ✓ |
| Stale wrong selection | 0 |
| Incremental isolation (H3) | PASS |
| Incremental isolation (H5) | PASS |
| Capacity gate | PASS |
| Resource gate | PASS |
| Browser regression | 9/9 ✓ |
| Test collection audit | difference_explained=True ✓ |
| Readiness conditions | **26/26** |
| ready_for_twenty_five_percent_decision | **True** |
| recommended_to_raise_to_twenty_five_percent | **False** |
| flagged_pi_p95_borderline | **True** ⚠️ |
| live_serving | false |
| production_enabled | false |

---
下一步：你需要操作

第一步：确认远端状态
```bash
git fetch origin && git log --oneline origin/release/demo-staging -6
# 应看到：c492ffe test(agent): record twenty-five-percent shadow readiness
```

第二步：重点监控 Pi p95（**关键**）
- 当前 pi_p95=4800ms，恰好等于 performance_review 阈值
- 建议在25%促进前确认 pi_p95 趋势
- 若连续两个窗口 pi_p95 > 4800ms → 触发 performance_review
- 监控指标：pi_over_5000ms_rate（当前1.35%，目标 <2%）、Pi > 6s count（必须保持0）

第三步：继续积累10%观察（推荐先完成1周稳定期）
- 每周运行一批 H 窗口（≥500 selected）
- 目标：H6后的额外窗口 pi_p95 能回落到 <4800ms（余量恢复）
- 若 pi_p95 余量回至 ≥50ms，再考虑 P1.17

第四步：项目负责人决策——是否进入 P1.17（25% Shadow Promotion）
- 前置：本人审核 `pi_official_report_p116_twenty_five_percent_readiness.json`
- 确认 `ready_for_twenty_five_percent_decision=true` 且 `conditions_met=26`
- **decision_required_from_project_owner=true（必须人工决策，不得自动提升）**
- **注意**：pi_p95=4800ms borderline，升级前建议确认余量充足
- 若批准：在新 worktree `/private/tmp/tradingagents-p117` 执行 Phase 6V-P1.17

第五步：若决定进入 P1.17（25% Shadow Promotion）
- config_version 5→6，项目负责人自审批
- 分析要求：I1-I8每批≥600 selected，combined≥5000，unique≥120
- Pi p95 monitor threshold 降至 4700ms（因已接近上限）
- 在新 worktree 执行，本分支不操作

第六步：若剩余19个2024缺口有新数据
- 触发时机：cninfo 全量目录更新，或 stale_review S5 > 10 条
- 执行 P1.13B（incremental refresh，新 worktree）
- 不在本分支操作

第七步：查看 P1.16 更新报告文件
- 报告位置：`HKNA/update_report/update_91.md`
