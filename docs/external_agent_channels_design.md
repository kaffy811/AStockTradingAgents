# External Agent Channels Design

**Phase C11–C12 — Design Document Only**  
_External sending is explicitly declined with a polite refusal. Refusal mentions /history export as the current alternative._

**C12 Refusal Behavior（已实装）：**
- 触发词：邮箱/email/微信/WeChat/钉钉/DingTalk/推送/发到
- 拒绝回复：不声称已发送（无"已发送"/"发送成功"等词）
- 引导替代：提及"历史报告"和"导出"功能
- 测试覆盖：`test_c12_rag_agent_contract.py::TestExternalChannelRefusal` 5 tests PASS

---

## Overview

External channel agents would push research output (reports, summaries, alerts) to external communication platforms. This document captures the intended design for future reference.

**Current status:** The Chat Copilot intercepts `_match_external_channel()` intents (email, WeChat, DingTalk, Feishu, Slack, Telegram) and returns a polite refusal:

> "目前系统暂不支持向外部渠道（邮件、微信、钉钉等）推送报告。"

---

## Proposed Architecture (Future)

### Channel Agents

| Agent | Trigger Intent | External API | Safety Gate |
|-------|---------------|--------------|-------------|
| `EmailChannelAgent` | 发到邮箱 / send to email | SMTP / SendGrid | Allowlist of verified recipient addresses |
| `WeChatChannelAgent` | 发到微信 / WeChat | WeChat Work Bot API | No content with buy/sell signals |
| `DingTalkChannelAgent` | 钉钉通知 | DingTalk Webhook | Same as above |
| `FeishuChannelAgent` | 飞书发送 | Feishu Bot API | Same as above |

### Safety Boundaries

1. **No trading advice in output**: All channel agents must strip or refuse content containing `买入`, `卖出`, `目标价`, `稳赚` before sending.
2. **Allowlist recipients**: Only pre-verified email addresses / group IDs may receive pushes.
3. **Rate limiting**: Max 5 pushes per user per day to prevent abuse.
4. **Audit trail**: All channel sends must be logged to `chat_audit_log` with `permission_level = "external_push"`.
5. **Confirmation required**: User must confirm before any external push (same flow as `add_watchlist` / `create_analysis_run`).

### Confirmation Flow

```
User: "把 688146 报告发到我的邮箱"
  → _match_external_channel() → _handle_external_channel()
  → Currently: polite refusal
  → Future: confirmation dialog →
      EmailChannelAgent.send(recipient, report_content)
      → AuditLog.record(...)
```

### Content Filtering

The `ChannelSafetyGuard` would scan outgoing content for:
- Explicit trading instructions
- Price predictions
- Content sourced from unverified external news (marked `external_content=True` by RAG)

---

## Why Not Implemented Now

1. External API credentials (SMTP, WeChat Work app ID) not configured in deployment environment.
2. Recipient allowlist management requires a new DB table and admin UI.
3. Rate limiting infrastructure not yet in place.
4. Legal/compliance review of what constitutes "investment advice" in push notifications is pending.

---

## Related Docs

- `chat_agent_safety_policy.md` — Safety rules for all outputs
- `chat_agent_architecture.md` — System architecture with channel layer
- `chat_agent_readiness_checklist.md` — C11 readiness gates
