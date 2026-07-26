Phase 6V-P1.6.8 完成的工作汇总：

已完成

1. 澄清链路调查（P1.6.7 Browser B03 blocker 根因）
- 首个丢失点在 **resolver 本身**：裸简称“平安”在 security_entity_resolver 索引无匹配（entities=[]、ambiguity=false），Legacy 从未拿到候选；skill 落入 ENTITY_NOT_RESOLVED 泛化文案；SSE/持久化/前端各层随之皆无候选。

2. 后端修复（通用、非硬编码）
- SecurityEntityResolver 新增 `resolve_short_alias_candidates`：仅在正常解析失败后，用索引对查询中的中文短别名做包含匹配（停用词过滤 + 命中 2..8 家才算歧义 + 确定性排序：前缀→名长→CN>HK>US→代码 + 跨市场同名去重）。实测“平安”返回平安银行/平安电工/中国平安——第三家来自真实索引，证明非写死。
- 新增 app/services/entity_clarification.py：`entity_selection` 结构化合同 + 确定性文本 fallback（列出“1. 平安银行（000001）…可直接回复公司名称或股票代码”），无 LLM、无 URL、无内部字段。
- report_explanation_skill：resolver 歧义分支与 ENTITY_NOT_RESOLVED fallback 均产出合同，status=clarification_required。
- Orchestrator 提升 metadata.response_kind/clarification；sync 响应新增可选 metadata 字段；SSE 在唯一 agent_completed terminal 附带合同（terminal 仍恰好一次，旧前端忽略未知字段）；chat_messages 现有 JSONB metadata 白名单持久化（零 migration）；session detail 暴露脱敏 metadata 子集供刷新恢复。

3. 前端
- 新增 ChatClarificationCard.vue + utils/clarification.js（去重/排序/选择文本纯函数）；ChatMessageList 在 assistant 消息下渲染候选按钮（无候选不渲染）；点击候选把“中国平安（601318）”作为普通用户轮发送（不绕过后端、不拼 URL）；刷新后从持久化 metadata 恢复候选。零新增依赖，package-lock 未变。

4. 测试
- 后端新增 17 条澄清测试（候选生成/去重/排序/显式代码不触发/停用词/无 URL/无内部字段/persist 往返/旧消息兼容/选择后正确解析等）；targeted 128 passed；**backend full 3435 passed, 15 skipped**。
- 前端新增 9 条测试（chatP168Clarification）；**688 passed (62 files)**；build passed。

5. Browser B03 重验 + 快速回归（headless Chrome，p168 worktree 同 SHA 前后端，专用账号）
- B03：候选卡片渲染（平安银行/平安电工/中国平安，去重、排序稳定、不自动选、无 PDF URL、无内部状态泄漏、console=0）；点击“中国平安”后 follow-up 不再歧义、无错误公司；刷新后候选恢复 → **PASS**。
- B01/B02/B04/B05 轻量回归全过；非歧义场景无候选组件误现；raw500/503=0/0。

6. 最终 Shadow Gate（引用 P1.6.6 Full30 原始结果，未重算未覆盖）
- shadow_passed=**true**；browser_acceptance=true；hard_failure_count=0；Class A/B/C/D=15/10/5/0；safety_correctness=1.0；behavior_match=0.6333（观测指标）。
- recommended_for_next_authorization=**true**；recommended_next_step=official_report_pdf_staging_canary_proposal。
- 正式 Pi 保持关闭：pi_executor_enabled=false，authorized_agents=[]，默认 AGENT_EXECUTOR_MODE=legacy / PI_AGENT_SHADOW_ENABLED=false，decision=do_not_enable_pi_compatible；本轮未创建任何 Canary 配置。

7. Artifacts
- 新增 5（clarification contract/audit、B03 results、browser regression、final shadow gate）；更新 4（agent gate、runtime gate、secret scan（p168 命中 0）、resource leak）；P1.6.6 Full30、P1.6.7 Browser 失败结果与 Review Policy artifacts 均未覆盖。

下一步
- Phase 6V-P1.7：撰写 official_report_pdf_staging_canary_proposal（灰度范围/回滚/监控/授权流程），获批前不改任何正式配置。
