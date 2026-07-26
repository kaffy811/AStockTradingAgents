# MVP-R1 Operations Runbook

**Phase**: MVP-R1  
**Date**: 2026-07-26

---

## Kill Switch Procedures

### Close New Chat (Immediate)

```env
# Set in .env or environment:
PI_REAL_PROVIDER_KILL_SWITCH=true
PI_REAL_PROVIDER_ENABLED=false
```

Restart backend. Verify: GET /mvp/health → real_provider_enabled=false.

### Close New Invites

Delete or expire invite codes in mvp_invite table:

```sql
UPDATE mvp_invite SET expires_at = NOW() WHERE redeemed = false;
```

### Disable Single User

```sql
UPDATE users SET is_active = false WHERE email = 'user@example.com';
```

### Switch to Legacy-Only

Already the default (staging_replay mode). No action needed in State B.

### Kill Switch Live Canary

```env
PI_CANARY_LIVE_ROLLOUT_PERCENT=0
```

Restart backend. Verify shadow still active.

---

## Monitoring Queries

### Daily Active Users

```sql
SELECT DATE(created_at), COUNT(DISTINCT user_id)
FROM mvp_analytics_event
WHERE event_name = 'chat_message_sent'
GROUP BY 1 ORDER BY 1 DESC LIMIT 7;
```

### Answer Success Rate

```sql
SELECT
  COUNT(*) FILTER (WHERE event_name = 'chat_answer_completed') as success,
  COUNT(*) FILTER (WHERE event_name = 'chat_answer_failed') as failed,
  COUNT(*) FILTER (WHERE event_name = 'fallback_triggered') as fallback
FROM mvp_analytics_event
WHERE created_at > NOW() - INTERVAL '24 hours';
```

### Feedback Summary

```sql
SELECT feedback_type, COUNT(*)
FROM chat_feedback
WHERE created_at > NOW() - INTERVAL '7 days'
GROUP BY feedback_type;
```

---

## Alert Response

| Alert | Response |
|---|---|
| HTTP 5xx > 5% | Check DB/Redis, restart backend |
| Session mismatch | Immediate kill switch, investigate |
| Credential leak | State D safety stop, rotate keys |
| Data fabrication | Kill switch AI, flag session |
| DB unavailable | Read-only mode, notify users |

---

## Week-1 Review Checklist (Day 7)

- [ ] Export daily metrics for 7 days
- [ ] Review feedback categories
- [ ] Identify top 3 user friction points
- [ ] List fallback trigger causes
- [ ] Decide: expand invites or fix issues first
- [ ] Pick 3 highest-priority issues for next iteration
