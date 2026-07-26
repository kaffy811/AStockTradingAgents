# official_report_pdf_pi_v1 — 1% Staging Canary Summary (6V-P1.8)

- Mode: **staging shadow canary** (`canary_mode=shadow`, `traffic_type=controlled_staging_acceptance`) — Pi 输出不直接服务用户，用户始终由 Legacy 服务；eligibility/selection/fallback/监控/回滚全部真实验证
- Approval: project_owner_self_approval（个人项目，checksum 绑定 source SHA，production_authorized=false）
- C0: 10 条真实 HTTP/SSE 请求全 Legacy（rollout_not_selected），1000 离线 key 零命中，Pi started=0 → PASS
- Kill switches K01–K04: 全部 PASS（K04 执行中切换：当前请求安全完成、后续立即 Legacy、无双写、无 raw500；配置刷新语义如实记录为 runner 热/服务器重启生效）
- Promotion: c0→c1，rollout 0→1%，config_version 2→3，promotion_source=project_owner_manual_decision
- Run2 counted: 50/50 selected eligible（5993 候选身份预筛 → 58 注册），Pi started/completed = 50/50，fallback 0，legacy_only 0
- 覆盖: 10 实体 × 5 query 风格 × 3 年度范围 × 5 多轮 case
- 安全: safety=1.0；fabricated URL/wrong entity/year/type/provenance/writes/double/unknown/trace/terminal/raw5xx/leak 全 0
- 延迟: Pi p50/p95 = 2810/4134ms；tool p95 4134ms 略超 4s 告警线（仅性能观察，无回滚）
- Run1 如实保留为 invalid（runner manifest 缺陷：代码+年份拼接、工具年份子集缺口未预筛、≥50 比例门未强制），已修复后重跑
- 工具缺陷 backlog: get_official_reports 对多行股票的年份子集/排序缺口（600186 最新只见 2022；300209 缺 2024）
- 非计数演示: 中国平安(known_unavailable)/平安歧义(clarification)/中报(unsupported) 全部按策略留在 Legacy
- 结论: **canary_passed=true**；建议继续 1% staging 观察；不升 5%；production 保持关闭
