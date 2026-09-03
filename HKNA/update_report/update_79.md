Phase 6V-P1.6.5 完成的工作汇总：

已完成

1. Full30 blocker 根因定位（Stage 1 离线重算，不修改任何 P1.6.4 历史 artifact）
- 15 个 trace mismatch（A01–A03、B01–B07、C01–C05）：P1.6.4 期间存在**第二个并发验收执行**，约 06:40 重建了共享 diagnostics JSONL，第一个执行的 A01–C05 terminal 记录丢失；DB 佐证为窗口内 49 个 pi-shadow session、16 个重复 case 标题。
- 33 次 “Pi business write” 与 22 次 “assistant double write” 全部为并发执行的 other_case 窗口污染：真实 Pi 写入 = 0，真实 assistant 双写 = 0（窗口内无任何 session 出现 user/assistant 计数不平衡）。
- 2 次 AGENT_DEADLINE_EXCEEDED 均为 F04 型未来年份（2035）慢查询叠加双执行 DB 争用；expected=0，unexpected=2。
- 唯一 PDF URL mismatch（B02）：Legacy 返回 2025 年年报（1225114741.PDF）而非请求的 2024 年年报（1222993920.PDF）；Pi 正确，两个 URL 属不同官方文档，禁止归一化为 match。
- 旧 clarification_correctness_rate 直接复用 status_match_rate、分母为全部 30 条，为 Gate 计算缺陷（shadow_acceptance.py），历史值 0.4333 予以保留。
- 旧 provenance 按 success schema 评判 skipped/failed 案例，9 个 “incomplete” 中多数为分类错误。

2. 运行时修复
- 新增 shadow_correlation.py：X-Pi-Shadow-Correlation header → ContextVar → shadow task/diagnostics 的不可变 correlation envelope（acceptance_run/case/attempt/session/turn/request_trace/legacy_run/shadow_run/input_snapshot）；无 header 时零行为变化。
- shadow_diagnostics.py v2：按 shadow_run_id 原子写独立文件（tmp+rename），terminal exactly-once，晚到 terminal 标记 stale_terminal_ignored；新增 diagnostics_record_version/written_at/terminal_sequence/checksum；不存储完整 query/Prompt/CoT。
- shadow_runner.py：skip 结果不再 run_id=null；意图正则补齐“年报PDF/季报PDF/中报PDF/年度报告PDF/季报原文”等 P1.6.4 漏判 8 例；嵌入别名（中国平安/平安银行/招商银行 含“平安/招商”）不再误触发澄清；新增“茅台”澄清 hint；compare() 移除 failed 通配 match，改为稳定 status taxonomy + behavior_match/safety_correctness/status-specific provenance。
- official_report_pdf_agent.py：新增确定性年份范围短路（未来年/2000 年前直接 REPORT_NOT_FOUND，不做全索引扫描——F04 deadline 根因修复，未提高任何 deadline）；unavailable/success provenance envelope 补齐 reason/provider/scope/tool_call_id/retrieved_at/verification_method。
- tool_adapter.py：Shadow persistence boundary 对非只读工具直接返回 PI_SHADOW_WRITE_FORBIDDEN。
- 新增 shadow_write_attribution.py：行级 owner 归因（legacy/pi_shadow/system/other_case/unknown）；仅 owner=pi_shadow 计入 pi_business_write_delta；unknown 直接 Gate fail；assistant_logical_response_id = session+turn+response_kind。
- 验收 runner：串行（max_concurrency=1），按 shadow_run_id 精确轮询（禁止 recency/conversation/query-hash 匹配），新增 --stage2 与 --blocker-subset 模式及 manifest hash。

3. 测试
- 新增 tests/fundamental/test_phase6v_p165_correlation.py：29 条回归，覆盖任务要求的 24 项（setup/follow-up 隔离、晚 terminal 不串扰、retry 新 run_id、原子写、exactly-once、stale 忽略、owner 归因、双写判定、taxonomy、clarification 分母、status-specific provenance、expected/unexpected timeout、URL 语义归一化边界等）。
- Targeted：111 passed；pool matrix 连续两次 13 passed；backend full 及 frontend 结果见 artifacts/最终报告。

4. Stage 2 / Stage 3 实测（local_live，串行）
- Stage 2（A01 多轮 / C01 显式代码 / E01 歧义）：3/3 executed，trace mismatch=0，写入=0，双写=0，unknown=0，terminal missing=0，subset_passed=true。
- Stage 3 固定 blocker subset（26 case，manifest hash b92cef60…3c47a0）：executed=26，accepted=14，review=12，failed=0；trace mismatch=0；pi_business_write_delta=0；double_write=0；unknown=0；unexpected deadline=0；clarification 2/2=1.0；status-specific provenance=1.0；raw500/503=0；subset_passed=true。
- 12 个 review 均为已记录的行为差异：D01–D05 Pi 按设计 unsupported（Legacy 声称 success）；F02/F04/F05 Pi 安全 unavailable（Legacy 对 1900/2035/缺失报告仍报 success）；B02/B05/C05/F07 Legacy 返回错误年份官方文档（Pi 正确）——均标记 safety_correctness=true、review_required，未复制 Legacy 缺陷。
- 附加非 Gate 并发隔离测试：两 session/两 case/两 shadow_run_id 并发无串扰。

5. Artifacts
- 新增 8 个 Stage 1 重算 audit（case matrix、trace mismatch 根因、write/double-write recompute、taxonomy、clarification 分母、status-specific provenance、deadline 根因）+ blocker subset manifest/results/summary + stage2 results。
- 更新 side effects、write attribution（v2）、agent gate、runtime gate、resource leak audit、secret scan（0 hits）。
- 原始 P1.6.4 Full30 artifacts 全部保留未改。

6. 结论与 Gate
- trace_mismatch_root_cause_identified=true；本轮所有核心 Gate 项达标；blocker_subset_passed=true。
- recommended_to_retry_full30=true（须串行 + correlation envelope）；recommended_for_next_authorization=false。
- 正式 Pi path 保持关闭：pi_executor_enabled=false，authorized_agents=[]，decision=do_not_enable_pi_compatible。
- 本轮未执行完整 Full30，未执行浏览器 Gate（按任务要求）。

注意事项
- 本轮提交位于分支 p165/full30-correlation-fix（基于 2d94ee0）；主工作区存在用户未提交的无关 staged 内容，未做任何改动，需用户确认后再合入 release/demo-staging。
- Stage 2 首轮观察到一次 Legacy E01 63s STREAM_ORCHESTRATION_TIMEOUT（Pi 侧正确澄清且 terminal exactly-once 生效），复跑未复现，属环境瞬态，建议在 Full30 重试时关注。
