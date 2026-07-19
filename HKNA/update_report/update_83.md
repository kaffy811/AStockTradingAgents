Phase 6V-P1.7 完成的工作汇总：

已完成

1. Staging Canary 授权模型与运行时策略（app/agent_runtime/canary_policy.py）
- 授权对象：environment=staging 绑定、agent 精确匹配（wildcard fail-closed）、status proposed/approved/rejected/revoked/disabled、可撤销、可过期（过期字符串不可读也 fail-closed）、config_version 版本化、审批引用脱敏。
- 九级决策优先链：global kill switch → environment hard disable（production 无条件拒绝，需独立授权）→ authorization status/expiry → exact allowlist → rollout bucket → request eligibility → runtime health gate → Pi execution → Legacy fallback；任一上游不满足直接 Legacy + compact audit reason，无用户可见错误。
- 配置解析 fail-closed：非法 rollout（负数/超 max/超 100/非数字）、未知 status、wildcard、读取异常一律关闭。

2. 配置默认值（app/core/config.py，全部关闭）
- pi_executor_global_kill_switch=false、pi_canary_environment=staging、authorization_status=proposed、allowed_agents=""、rollout_percent=0、max_rollout_percent=5、fallback=legacy、auto_rollback=true、min_sample=50；auto_run=false、production_enabled=false。

3. 稳定分桶
- sha256(env|agent|anon_user_key|config_version) % 10000 < rollout*100；不用内置 hash/时间/随机；匿名 key=sha256(user_id)[:16]（不存完整 id）；config_version 变化重新分桶；rollout=0 绝对无人命中；20000 样本 1% 实测 0.955%。

4. Eligibility / Fallback / Kill switch / Auto rollback
- 仅 staging+approved+annual+实体明确可进；歧义/unsupported/unavailable/故障注入全部留在 Legacy（保持 P1.6.8 澄清体验）。
- 三级 kill switch（global>environment>agent>rollout），状态入每条审计；刷新机制为 per-decision 读取 settings（配置变更需进程重启/env reload，已在 artifact 明确该局限）。
- 零容忍指标（fabricated URL、Pi business write、double write、unknown write、trace mismatch、terminal missing、provenance、clarification error、raw500/503、task/DB leak、safety<1.0）样本无关立即回退 rollout=0；比例指标（unexpected timeout>1%、fallback>10%）需 ≥50 样本；回退后 auto_reraise_allowed=false，必须人工重审。

5. 监控与审计
- 六类指标 spec（eligibility/execution/safety/reliability/performance/product）；标签禁止完整 user id/query/token/URL/高基数 id，只允许 16 位 hash 与有限枚举。
- compact audit event schema（build_audit_event）：含 config_version/kill_switch_state/decision/reason/相关性 hash，脱敏测试覆盖；audit 属 system 写入，不计 Pi business write；audit 失败触发安全 fallback。

6. 测试与模拟
- 新增 32 项 canary policy 测试（默认关闭、rollout=0 永不命中、wildcard/过期/非法配置 fail-closed、三级 kill switch 优先级、eligibility 排除、确定性分桶/重分桶、max 上限、rollback 全套、样本规则、审计脱敏、production 拒绝）全部 PASS。
- S01–S08 模拟全部 PASS：S01 1% 分布 0.955% 且稳定；S02 fabricated URL→回退 0；S03 选中用户 health gate 失败→单次 Legacy、双写 0、Pi 写入 0、无 raw500；S04 trace mismatch→立即回退；S05 global kill switch→50 请求全 Legacy；S06 中报→unsupported 不进 Pi；S07 歧义“平安”→Legacy clarification；S08 production 即使 approved 也拒绝。模拟仅用内存配置，不计真实流量。
- Targeted + backend full + 前端基线见最终报告。

7. 阶段计划与审批
- C0（当前 rollout=0 直到人工批准）→ C1（1%，≥50 请求，≥24h，人工启动，auto rollback）→ C2（5%，≥200 请求，≥48h，需 C1 人审）→ 更高需全新审批；本提案 max_rollout_percent=5，不预授权 100%。
- 双人审批（Agent/Runtime owner + Release/Reliability owner，可选 Product/Compliance），checklist 十项确认后才可 approved；本轮 artifact 为 proposal，未填写任何批准人。

8. 本轮结束状态
- authorization_status=proposed、allowed_agents=[]、rollout_percent=0、max=5、auto_run=false、production_enabled=false。
- 正式 Pi：pi_executor_enabled=false、authorized_agents=[]、AGENT_EXECUTOR_MODE=legacy、PI_AGENT_SHADOW_ENABLED=false、decision=do_not_enable_pi_compatible。
- recommended_for_staging_canary_authorization=true（仅表示可提交审批）；recommended_for_production_authorization=false。

Artifacts：新增 10（proposal/authorization policy/rollout plan/kill switch audit/auto rollback policy/monitoring spec/audit schema/simulation results/approval checklist/canary gate）+ 更新 4（agent gate/runtime gate/secret scan(p17 命中 0)/leak audit）；P1.6.6/P1.6.7/P1.6.8 历史 artifacts 未覆盖。

下一步：提交双人审批；批准后进入 C1（人工将 authorization_status→approved、allowed_agents 填入精确 agent、rollout→1%），全程 kill switch 与 auto rollback 就位。
