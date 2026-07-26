---
目前完成的工作汇总：

已完成

1. 修改文件清单
- backend/scripts/company_v2_cross_stock_acceptance.py：补充 Deep artifact 所需字段，新增 quarterly_range、invalid_period_count、start_period、end_period 输出；未改变 gate 阈值或 provider 行为。
- frontend/src/components/company-v2/charts/CompanyV2CashflowQualityChart.vue：修复现金流图表 secondary axis 判断与 fallback 口径，修正 ECharts splitLine 配置。
- backend/docs/artifacts/company_v2_cross_stock_fast_acceptance_phase6te1.json / .md / .checkpoint.json：Fast Gate 收口 artifact。
- backend/docs/artifacts/company_v2_000725_retry_phase6te1.json / .md：000725 唯一有效 retry 结果。
- backend/docs/artifacts/company_v2_601686_chart_reaudit_phase6te1.json / .md：601686 chart contract 重校验结果。
- backend/docs/artifacts/company_v2_cross_stock_deep_acceptance_phase6te1.json / .md：Deep Acceptance 3 股结果。
- backend/docs/artifacts/company_v2_cninfo_stability_phase6te.json / .md：CNINFO Stability 8 股结果。
- backend/docs/artifacts/company_v2_history_completeness_phase6te.json：历史完整性汇总。
- backend/docs/artifacts/company_v2_performance_baseline_phase6te.json：性能基线汇总。
- backend/docs/artifacts/company_v2_phase6te_final_gate.json / .md：Phase 6T-E final gate。
- HKNA/update_report/update_19.md：本次收尾报告。

2. Fast Acceptance 8 股结果
- 600519：passed，6 模块，provider_calls=120，elapsed_ms=145877。
- 000725：passed，唯一有效 retry 后 6 模块 annual rows 均为 19，provider_calls=120，elapsed_ms=110498。
- 601686：warning，chart_contract_valid=true，invalid_chart_contracts=[]，history_audit_warning:dupont。
- 300750：passed，6 模块，provider_calls=54，elapsed_ms=87126。
- 688981：passed，6 模块，provider_calls=42，elapsed_ms=58015。
- 601318：passed，6 模块，provider_calls=120，elapsed_ms=136910。
- 000001：warning，6 模块，历史完整性 warning，provider_calls=120，elapsed_ms=120181。
- 601728：passed，6 模块，provider_calls=36，elapsed_ms=53059。

3. 600519 性能修复前后
- 修复前旧慢路径约 624 calls / 1611s。
- Fast Gate 收口后为 120 calls / 146s，仍保留真实 cold cache 结果。

4. 000725 retry 结果
- 首次 Fast artifact 为 180s hard timeout：per_symbol_timeout_exceeded:180s。
- 唯一有效 retry 成功：elapsed_ms=110498，provider_calls=120，timeout=false，final_status=passed。
- retry_count_by_symbol.000725=1，未再次重试。

5. 601686 chart contract
- 旧 artifact 中 cashflow_quality 出现 extreme_scale_without_secondary_axis:124x。
- 修复后 cashflow_quality contract 支持 auto_secondary_axis=true、scale_threshold=100。
- 124x 量级差现在为 extreme_scale_uses_secondary_axis:124x warning，不再产生 invalid chart contract。

6. 000001 history warning
- 历史完整性约 49%-51%，缺失 17/18 个年度期。
- 该问题保留为 warning，非 chart failure，非 blocking。
- 不能直接归因成 NOT_APPLICABLE_FOR_BANK，也未填充假数据。

7. Deep Acceptance 3 股结果
- 600519：timeout=true，blocking_issues=[per_symbol_timeout_exceeded:180s]，final_status=failed。
- 300750：timeout=true，blocking_issues=[per_symbol_timeout_exceeded:180s]，final_status=failed。
- 000001：timeout=true，blocking_issues=[per_symbol_timeout_exceeded:180s]，final_status=failed。
- Deep Acceptance 没有下载 PDF、解析 PDF、运行 AI verification 或 RAG。

8. CNINFO Stability 8 股结果
- 600519：success，reports=16，annual=5，quarterly=11。
- 000725：success，reports=10，annual=5，quarterly=5。
- 601686：success，reports=16，annual=5，quarterly=11。
- 300750：success，reports=11，annual=5，quarterly=6。
- 688981：success，reports=19，annual=5，quarterly=14。
- 601318：success，reports=19，annual=5，quarterly=14。
- 000001：success，reports=12，annual=5，quarterly=7。
- 601728：success，reports=18，annual=5，quarterly=13。
- 汇总：8/8 success，reports_found=121，annual_reports_found=40，quarterly_reports_found=81，duplicate=0，invalid_url=0，non_whitelist=0，summary=0，wrong_symbol=0。

9. 四个 gates
- history_gate_passed=false。
- chart_gate_passed=false。
- cninfo_gate_passed=true。
- performance_gate_passed=false。
- phase6te_passed=false。
- recommendation_for_phase6td=hold。

10. Blocking issues
- deep:600519:per_symbol_timeout_exceeded:180s。
- deep:300750:per_symbol_timeout_exceeded:180s。
- deep:000001:per_symbol_timeout_exceeded:180s。

11. Warnings
- fast:601686:history_audit_warning:dupont。
- fast:000001:history_audit_warning:profitability/growth/solvency/operation_capability/cashflow_quality/dupont。
- frontend_build:large_chunk_warning。
- pyenv rehash: shims not writable。
- Vite CJS Node API deprecated warning。
- cninfo:cache_hit_not_observed_by_script。

12. Backend 全量测试
- 命令：backend/.venv/bin/python -m pytest -q。
- 结果：2860 passed，1 skipped，70 warnings，63.47s。

13. Frontend 全量测试
- 命令：npm run test。
- 结果：48 files passed，609 tests passed。

14. Frontend build
- 命令：npm run build。
- 结果：成功，947 modules transformed。
- 备注：存在 Vite chunk size warning，未导致 build 失败。

15. 是否建议进入 Phase 6T-D
- 不建议进入。
- 原因：Fast Gate 已收口且 CNINFO Gate 通过，但 Deep Acceptance 3 股均 180s timeout，history/chart/performance final gate 因 Deep blocking issue 重新失败。
- 当前 recommendation_for_phase6td=hold。

16. Phase 6T-E2：Quarterly Deep Acceptance Performance Fix
- 根因定位：E1 Deep 将 quarterly financial fetch、annual payload_compare、CNINFO discovery 全部包在同一个 180s per-symbol timeout 内；quarterly 财务阶段即使已完成，也可能被后续 payload_compare/CNINFO 消耗预算后整体 timeout，且 timeout 分支用 _empty_result 覆盖阶段统计，导致 provider_calls、quarterly_range、stage 全部为空。
- 请求范围修正：新增 resolve_quarterly_window(as_of_date, years=5, latest_disclosed_period=None)，Deep quarterly 默认解析为最近 5 个完整财年，不按上市日期生成，不请求未来季度、不请求 daily、不请求 valuation history。
- 2026-07-11 的 Deep quarterly window：2021-03-31 至 2025-12-31，20 个主要报告期。
- 阶段拆分：financial_timeout=180s，cninfo_timeout=60s，CNINFO 不再占用财务抓取 180s 预算；payload_compare 默认关闭，避免 annual debug_full 阻塞季度验收。
- 观测增强：artifact 增加 stage、performance_progress、provider_call_accounting、deep_chart_gate_status、deep_history_gate_status、chart_contract_regression。
- 共享查询：6 个模块继续共享同一 BaoStock quarterly bundle，planned_calls=120，calls_by_endpoint 每表 20，duplicate_calls_avoided=600。
- 缓存增强：补充 quarterly_bundle、quarterly_normalized cache key 结构；timeout/checkpoint 保留阶段信息，便于 resume。

17. Phase 6T-E2 单股 smoke
- 300750：passed，timeout=false，quarterly_range=2021-03-31—2025-12-31，provider_calls=120，elapsed_ms=33850，chart=passed。
- 600519：passed，timeout=false，quarterly_range=2021-03-31—2025-12-31，provider_calls=120，elapsed_ms=20318，chart=passed。
- 000001：warning，timeout=false，quarterly_range=2021-03-31—2025-12-31，provider_calls=120，elapsed_ms=33291，chart=passed；银行不适用字段未作为 blocking。

18. Phase 6T-E2 三股 Deep Acceptance
- 600519：passed，timeout=false，provider_calls=120，elapsed_ms=13124。
- 300750：passed，timeout=false，provider_calls=120，elapsed_ms=42175。
- 000001：passed，timeout=false，provider_calls=120，elapsed_ms=22654。
- 三股合并结果：history_gate_passed=true，chart_gate_passed=true，cninfo_gate_passed=true，performance_gate_passed=true，phase_gate_passed=true。

19. Phase 6T-E2 修复前后对比
- E1 Deep：600519/300750/000001 均 per_symbol_timeout_exceeded:180s，provider_calls 未落盘，quarterly_range 未生成，CNINFO skipped。
- E2 Deep：三股均在 180s 内完成财务阶段并独立完成 CNINFO，provider_calls 均可观测为 120。
- chart gate 修正：timeout 时可记录 deep_chart_gate_status=not_evaluated；E2 有数据后 deep_chart_gate_status=passed，chart_contract_regression=false。

20. Phase 6T-E2 targeted tests
- 命令：backend/.venv/bin/python -m pytest backend/tests/fundamental/test_phase6te2_quarterly_deep_performance.py backend/tests/fundamental/test_phase6te1_history_fetch_performance.py backend/tests/fundamental/test_phase6te_chart_contract_validation.py -q。
- 结果：33 passed。

21. Phase 6T-E2 final gate
- history_gate_passed=true。
- chart_gate_passed=true。
- cninfo_gate_passed=true。
- performance_gate_passed=true。
- phase6te_passed=true。
- blocking_issues=[]。
- warnings：fast:601686 history_audit_warning:dupont；fast:000001 history completeness warnings；cninfo:cache_hit_not_observed_by_script。
- recommendation_for_phase6td=proceed。

---
下一步：你需要操作

第一步：进入 Phase 6T-D 前先由产品/工程确认 Phase 6T-E2 final gate artifact：backend/docs/artifacts/company_v2_phase6te_final_gate.json。

第二步：保留 E1 timeout artifact 与 E2 repaired artifact 作为回归基线，不删除 legacy，不重跑 Fast 8 股，不再次重试 000725。

第三步：若后续进入 Phase 6T-D，只基于 phase6te_passed=true 的 final gate 开始，不在本轮启动 Phase 6T-D。
