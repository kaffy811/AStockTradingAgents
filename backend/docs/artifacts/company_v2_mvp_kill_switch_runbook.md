# MVP Kill Switch Runbook

**Phase**: 6V-P1.32  
**Last Updated**: 2026-07-26  
**Owner**: Project Lead

---

## 1. Kill Switch Types

| Kill Switch | Config Field | Default | Effect |
|---|---|---|---|
| Real Provider | `PI_REAL_PROVIDER_KILL_SWITCH=true` | ON (safe) | Blocks all real DeepSeek calls → staging_replay |
| Pi Live | `PI_CANARY_LIVE_ENABLED=false` | ON | Disables 1% live arbitration → replay+legacy only |
| Pi Shadow | `PI_CANARY_SHADOW_ROLLOUT_PERCENT=0` | 100% | Stops shadow traffic collection |
| New Chat | Backend: rate limit or feature flag | N/A | Prevents new chat sessions |
| New Registration | Stop creating invite codes | N/A | No new users can register |
| Production | `PI_PRODUCTION_ENABLED=false` | OFF | Enforces staging-only operation |

---

## 2. When to Use Each Kill Switch

### Real Provider Kill Switch
**Trigger when:**
- Provider cost spike beyond ¥100/day
- Unexpected provider errors > 5% of requests
- Security incident involving provider API
- Budget exhaustion approaching

**Do NOT use for:**
- Normal provider rate limiting (handled automatically by rate limiter)
- Single failed request

### Pi Live Kill Switch
**Trigger when:**
- Pi live responses diverge significantly from legacy
- Zero-tolerance violations detected
- Review Agent rejection rate > 10%
- User complaints about answer quality spike

### New Registration Kill Switch
**Trigger when:**
- Abuse of invite codes detected
- System load > safe threshold
- Preparing for controlled capacity expansion

---

## 3. Real Provider Kill Switch Procedure

### Activating (Blocking Real Provider)

```bash
# Step 1: Set kill switch in environment
export PI_REAL_PROVIDER_KILL_SWITCH=true
export PI_REAL_PROVIDER_ENABLED=false

# Step 2: Restart backend (or trigger hot-reload if supported)
# Docker:
docker-compose restart backend

# Step 3: Verify probe
curl -s http://localhost:8000/mvp/health | python3 -m json.tool
# Expected: "real_provider_enabled": false, "real_provider_kill_switch": true
```

### Verifying (after activation)

```bash
# Run 5 test requests and confirm:
# - real_provider_calls = 0
# - legacy fallback = 5
# - HTTP status = 200 for all
curl -X POST http://localhost:8000/api/v1/chat/sessions/{session_id}/messages \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"content": "test"}'
```

### Confirmation Criteria
- [ ] `/mvp/health` shows `real_provider_enabled: false`
- [ ] `/pi-canary/provider-budget` shows `real_provider_enabled: false`
- [ ] No new real provider audit entries in `pi_real_provider_audit` table
- [ ] Chat responses still return 200 (legacy serving)

---

## 4. Pi Live Kill Switch Procedure

### Activating

```bash
# Set PI_CANARY_LIVE_ENABLED=false
# This triggers cv increment to next version (failsafe)
export PI_CANARY_LIVE_ENABLED=false
docker-compose restart backend
```

### Verifying

```bash
curl -s http://localhost:8000/api/v1/debug/canary-snapshot | python3 -m json.tool
# Expected: live_rollout_percent: 0 or live_enabled: false
```

### Confirmation Criteria
- [ ] 0% of requests enter live arbitration
- [ ] All requests use replay or legacy path
- [ ] Shadow collection continues unaffected (optional)

---

## 5. Recovery Procedures

### Re-enabling Real Provider (after incident resolved)

```bash
# Prerequisites: All of the following must be true:
# 1. Root cause identified and resolved
# 2. Budget confirmed within limits
# 3. Explicit project owner authorization obtained

export PI_REAL_PROVIDER_KILL_SWITCH=false
export PI_REAL_PROVIDER_ENABLED=true
docker-compose restart backend

# Verify gate passes:
curl -s http://localhost:8000/mvp/health
# Expected: "gate_pass": true (only if credential, pricing also in order)
```

### Re-enabling Pi Live

```bash
export PI_CANARY_LIVE_ENABLED=true
docker-compose restart backend
```

---

## 6. Data Protection During Kill Switch

- No in-flight request data is lost: legacy completes all active requests
- Database transactions in progress are safely rolled back or committed
- Redis budget counters persist (not reset) — cumulative totals maintained
- Chat history unaffected: all completed sessions remain accessible
- Audit logs preserved: `pi_real_provider_audit` table intact

---

## 7. Escalation

| Severity | Action | Timeframe |
|---|---|---|
| P0 (data leak, cost spike > ¥100) | Activate all kill switches immediately | < 5 minutes |
| P1 (error rate > 5%, budget > 80%) | Activate real provider kill switch | < 15 minutes |
| P2 (degraded quality, minor anomaly) | Monitor and document | < 1 hour |

---

## 8. Post-Kill-Switch Checklist

- [ ] Kill switch activated and verified
- [ ] Affected requests served by legacy (200 returned)
- [ ] Budget audit confirmed (no overspend)
- [ ] Incident documented in `mvp_analytics_event` (error category)
- [ ] Root cause investigated
- [ ] Project owner notified
- [ ] Recovery decision made with explicit authorization
