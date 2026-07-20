Phase 6V-P1.8 完成的工作汇总：

已完成

1. 项目负责人自审批（个人项目模式）
- project_owner_self_approval 记录：staging-only、agent 仅 official_report_pdf_pi_v1、approved_rollout=1%、max=5%、production_authorized=false、checksum 绑定 source SHA 85e61c0（SHA 变更需重生成）；无虚构姓名/邮箱/签名。

2. Canary 激活状态机（app/agent_runtime/canary_activation.py）
- disabled→approved_c0→active_c1→completed_c1/rolled_back；禁止跳过 C0、禁止自动 promotion（必须 project_owner_manual_decision）、rolled_back 禁止自动恢复（需全新 owner 决定）、production 永远拒绝；promotion 时 config_version 递增；13 条新测试 + P1.7 32 条 = 45 PASS。

3. C0（rollout=0）live 验证 — PASS
- 独立 p18 uv venv、8024 端口（shadow OFF 纯 Legacy）；10 条真实 HTTP/Auth/SSE 请求全部 decision=legacy/rollout_not_selected，每条 HTTP200+terminal=1+单 user/assistant 行；1000 离线匿名 key 零命中；production/other-agent 无条件拒绝；Pi started=0。

4. Kill switch 演练 K01–K04 — 全 PASS
- K01 global→全 Legacy；K02 environment→staging 停、production 本就拒绝；K03 agent→仅本 Agent 停；K04 执行中切换→当前请求安全完成（terminal=1、单 assistant 行、无双写、无 raw500）、后续立即 Legacy。刷新语义如实记录：runner 域配置热生效、服务器 env 开关重启生效。

5. C1 手动 promotion 与 1% 真实验证
- promotion：c0→c1、rollout 0→1、config_version 2→3、promotion_source=project_owner_manual_decision（审计入 artifact）。
- 20k 离线匿名 key 分布 0.885% ∈ [0.8%,1.2%]（不计入 50）。
- 方案B：5993 候选身份按稳定分桶预筛 → 58 命中者注册真实账号；每条请求真实 login/HTTP/SSE + correlation envelope + per-run diagnostics；max_concurrency=1。
- **canary_mode=shadow**（诚实标记）：当前 runtime 无 Pi 用户可见输出路径，用户始终由 Legacy 服务；traffic_type=controlled_staging_acceptance。

6. Run1 失效与修复（如实保留，不隐藏）
- run1 保存为 canary_results_run1_invalid.json：7 条 runner manifest 缺陷（代码+年份无空格拼接致实体不可解析，本不满足 eligibility）、2 条命中工具年份子集缺口、≥50 比例/safety 门未强制执行。
- 修复：manifest 空格与工具核验 combos（600186 整体剔除——工具最新只见 2022≠DB 2025；300209 剔除 2024）；比例/safety 门在 ≥50 后强制执行；3 条不计数预热请求。
- 新增工具缺陷 backlog：get_official_reports 多行股票年份子集/排序缺口。

7. C1 run2 — **canary_passed=true**
- 50/50 selected eligible；pi_started=50、pi_completed=50、fallback=0、legacy_only=0（pi_completed+safe_fallback=pi_started ✓）。
- 覆盖：10 实体 × 5 query 风格 × 3 年度范围（latest/2025/2024）× 5 多轮 case。
- 安全全 0：fabricated URL、wrong entity/year/type、provenance failure、Pi business writes、double writes、unknown writes、trace mismatch、terminal missing、raw500/503、task/DB leak、PendingRollbackError；safety_correctness=1.0；unexpected_timeout_rate=0；fallback_rate=0。
- 延迟：Pi p50/p95=2810/4134ms（<5s）；tool p95 4134ms 略超 4s 告警线 → 仅性能观察项，无回滚；legacy p50/p95=16983/21810ms（当前 staging 环境整体较慢）。
- 三条非计数演示：中国平安(known_unavailable)/平安歧义(clarification)/中报(unsupported) 全部按策略留在 Legacy。
- 终态：completed_c1，rollout 仍 1%，无自动回滚。

8. 结束状态
- 不升 5%（需 owner 另行决定）；production 保持关闭；仓库默认配置未动（AGENT_EXECUTOR_MODE=legacy、PI_AGENT_SHADOW_ENABLED=false、authorized_agents=[]、canary status=proposed/rollout=0）。

9. Artifacts
- 新增 15（approval/c0/kill drill/promotion/manifest/results+run1_invalid/summary/latency/safety/fallback/write/auto rollback/monitoring/final gate）+ 更新 4（agent gate、runtime gate、secret scan（p18 命中 0）、leak audit）；历史 artifacts 未覆盖。

下一步建议
1. 维持 1% staging shadow canary 观察（周期性重跑 runner 采样）。
2. 修复 get_official_reports 年份子集/排序缺陷后，将 600186/300209-2024 纳回 manifest。
3. 若观察期干净且 owner 决定，另开阶段升 5%；live serving canary 需先设计 Pi 用户可见输出路径的独立提案。
