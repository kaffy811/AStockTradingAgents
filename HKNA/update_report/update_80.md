Phase 6V-P1.6.6 完成的工作汇总：

已完成

1. 正式基线与环境
- 基线：origin/release/demo-staging @ 086083186d49f89368b3dabcc91c3713a92a951d（P1.6.5A 合入后首个正式 Full30 重试基线）。
- 全新 clean clone：/private/tmp/tradingagents-p166-clean，独立 uv venv，独立全新 diagnostics 目录（未复用任何旧 diagnostics 文件）。
- 后端以 shadow-only 环境启动（CHAT_RUNTIME_MODE=legacy、AGENT_EXECUTOR_MODE=pi_compatible_shadow、PI_AGENT_SHADOW_ENABLED=true、allowlist 仅 official_report_pdf_pi_v1）；仓库默认配置保持全关。

2. Preflight 与固定 Smoke
- Preflight：environment_ready=true，blockers=[]。
- 固定 3 条 Smoke（A01 多轮 / A02 显式代码 / A03 歧义）：3/3 pass，side effects=0，double writes=0，smoke_passed=true。

3. 串行 Full30（max_concurrency=1，correlation envelope + per-run diagnostics）
- planned=30，executed=30，accepted=15，review=15，failed=0。
- Manifest hash：68c3c9d1221ddd7939ce42805ace239222175cd569f91c382d75243c10761518（原 30 case，expected outcome 未改）。
- P1.6.4 污染项全部归零：trace mismatch=0，terminal missing=0，stale terminal=0，Pi business writes=0，assistant double writes=0，unknown writes=0，other-case writes=0，context mutations=0。
- deadline expected/unexpected=0/0（F04 未来年份短路修复生效，1444ms p95）。
- entity/year/type/source URL match=1.0；pdf_url_match=0.8667；status_match=0.6333。
- status-specific provenance completeness=1.0；clarification applicable 2/2=1.0；safety correctness=30/30=1.0。
- deterministic LLM calls=0；raw500/raw503=0/0；resolver warm full scans/rebuilds=0/0；Pi latency p50/p95=933/1444ms。
- diagnostics 记录 37 条（3 smoke+1 setup、30 case、3 setup），全部按预生成 shadow_run_id 精确匹配一次。

4. 15 个 review case（全部为已记录的安全行为差异，safety_correctness=true）
- D01–D05：Pi 按设计对非年报类型返回 unsupported；Legacy 声称 success（多数无 URL）。
- F01–F06：Pi 对不存在公司/1900/2035/无官方链接返回安全 unavailable；Legacy 答案派生 status 误报 success。
- B02/B05/C05/F07：Legacy 返回错误年份的官方文档 URL，Pi 返回正确年份；真实不同文档，不做归一化。

5. 最终 Shadow Gate（honest 结论）
- shadow_passed=false。剩余 blockers：
  a) status_match_rate 0.6333 < 0.99 阈值——全部 15 项差异均为 Pi 更安全或 Legacy 错误文档，无一项为 Pi 不安全行为；
  b) 浏览器验收 not_run——需要有人工登录态的浏览器会话。
- recommended_for_next_authorization=false；pi_executor_enabled=false；authorized_agents=[]；decision=do_not_enable_pi_compatible。

6. Artifacts
- 重写正式 Full30 final 五件套（results/summary/terminal/provenance/safety，schema v2，注明 supersedes P1.6.4；P1.6.4 失败版本保留在 git 历史 2d94ee0）。
- 更新 case summary、agent gate、runtime gate、fixed smoke results/summary、side effects、write attribution、resource leak audit、secret scan（token/JWT/UUID/DB URL 命中=0，无完整 query/Prompt/CoT）。

7. 测试
- Backend full（p166 clone 独立环境）：见最终报告（提交前完成）。
- 基线树与 P1.6.5A integration 完全一致（该树已录得 backend 3408 passed / frontend 679 passed / build passed）。

下一步建议
1. 人工浏览器验收（三段对话）：贵州茅台最新财报→这份报告的官方 PDF；五粮液2025年年度报告PDF；平安的年报PDF（应澄清）。
2. 若维持 0.99 status_match 阈值，需要产品决策：要么扩展 Pi Agent 支持季报/中报与 Legacy 对齐，要么将“Pi 更安全的差异”正式纳入 Gate 豁免清单（safety_correctness=1.0 已具备证据）。
3. 在上述决策前，正式 Pi path 保持关闭。
