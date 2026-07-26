# official_report_pdf_pi_v1 — Staging Canary Proposal (6V-P1.7)

- Shadow Gate source: `808b3671d76042774399c478ac1ad2d6b018aa52` (P1.6.8 shadow_passed=true; Full30 30/30, hard failures 0, safety 1.0, Browser B01–B05 passed)
- Scope: **staging only**, single agent `official_report_pdf_pi_v1`, annual-report requests only
- Initial state: `authorization_status=proposed`, `allowed_agents=[]`, `rollout_percent=0`, `max_rollout_percent=5`

## Authorization model
Versioned per-environment authorization object (see `pi_official_report_p17_authorization_policy.json`):
exact agent id (wildcards fail closed), revocable, expiring, dual-approval, production strictly独立授权。

## Decision priority
global kill switch → environment hard disable → authorization status/expiry → exact allowlist →
rollout bucket → request eligibility → runtime health gate → Pi execution → legacy fallback。
任一上游不满足即静默走 Legacy，产生 compact audit reason，无用户可见错误。

## Eligibility
仅 staging + approved + annual + 实体已明确；歧义 clarification、unsupported semi/q1/q3、
已知 unavailable、故障注入请求一律 Legacy（保持 P1.6.8 澄清体验）。

## Stable bucketing
`sha256(env|agent|anon_user_key|config_version) % 10000 < rollout*100`；
rollout=0 绝对无人命中；1% 实测 0.955%（20k 样本）；config_version 变化可重新分桶；
不存完整 user id（sha256[:16] 匿名 key）。

## Fallback
Agent/Tool timeout、unavailable、异常、provenance/URL 校验失败、diagnostics 失败、
side-effect guard、kill switch、health gate → 单次 Legacy 回答；无双写（P1.6.5 行级归因保障）、
无 Pi 内部错误外显、无 raw500/503、半成品 Pi 输出永不下发。

## Kill switch / Auto rollback
三级开关（global > environment > agent > rollout），状态入审计；
零容忍指标（fabricated URL/各类写入/trace/terminal/provenance/5xx/泄漏/safety<1.0）样本无关立即回退到 0，
比例指标（unexpected timeout>1%、fallback>10%）需 ≥50 样本；回退后禁止自动升流量。

## Rollout stages
C0（当前，rollout=0，直到人工批准）→ C1（1%，≥50 请求，≥24h，人工启动）→
C2（5%，≥200 请求，≥48h，需 C1 人审）→ 更高比例需全新审批；本提案上限 5%。

## Approval
至少双人（Agent/Runtime owner + Release/Reliability owner，可选 Product/Compliance），
逐项确认 checklist（见 `pi_official_report_p17_approval_checklist.md`）后方可将
authorization_status 置为 approved。本 artifact 仅为 proposal，未填写任何批准人。

## Current state after this phase
`{"environment":"staging","authorization_status":"proposed","allowed_agents":[],"rollout_percent":0,"max_rollout_percent":5,"auto_run":false,"production_enabled":false}`
正式 Pi 保持关闭：pi_executor_enabled=false、authorized_agents=[]、decision=do_not_enable_pi_compatible。
