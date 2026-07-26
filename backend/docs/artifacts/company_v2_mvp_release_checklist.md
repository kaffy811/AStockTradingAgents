# MVP Release Checklist

**Phase**: 6V-P1.32  
**Date**: 2026-07-26  
**Release Type**: Invite-Only MVP  
**State**: B — MVP RC implemented, real provider pending P1.33

---

## P0 — Must Pass (Blocking)

### Core Flow
- [x] User login and auth working
- [x] Stock search functional
- [x] Company financial page loads (5-tab)
- [x] Chat single-turn completes successfully
- [x] Chat multi-turn with context works
- [x] History sessions saved and retrievable
- [x] Only one final answer visible to user per request (exactly-once)

### Provider Safety
- [x] Real provider kill switch active by default (`pi_real_provider_kill_switch=True`)
- [x] Real provider NOT enabled by default (`pi_real_provider_enabled=False`)
- [x] ProviderActivationGate wired into factory.py call path
- [x] Legacy fallback active and verified (100% fallback on any Pi failure)
- [x] No real provider calls without explicit project owner authorization

### Security
- [x] `DEEPSEEK_API_KEY_STAGING` NOT in Git
- [x] `DEEPSEEK_API_KEY_STAGING` NOT in any artifact
- [x] No staging key in browser network traffic
- [x] Runtime probe sanitized (fingerprint prefix only)
- [x] Audit log records hashes only (no raw prompts/responses)

### Invite-Only Access
- [x] `mvp_invite` table implemented (migration `n2o3p4q5r6s7`)
- [x] `POST /mvp/invites/check` — validate code without consuming
- [x] `POST /mvp/invites/redeem` — consume invite with use_count tracking
- [x] `POST /mvp/invites` — admin creates codes
- [x] Expired invite codes rejected
- [x] Fully redeemed codes rejected
- [x] Public production NOT deployed (`production_authorized=false`)

### Feedback Loop
- [x] `chat_feedback` table implemented
- [x] `POST /chat/feedback` endpoint accepting thumbs_up/thumbs_down/report
- [x] Feedback stored without PII (snippet max 200 chars)
- [x] Feedback visible in database for review

### Analytics Baseline
- [x] `mvp_analytics_event` table implemented
- [x] `POST /mvp/analytics/event` endpoint
- [x] PII-named keys stripped from properties
- [x] P0/P1 errors emit server log.error()
- [x] Canonical event list documented

### Monitoring
- [x] Structured error events with severity levels (p0/p1/p2/info)
- [x] `GET /mvp/health` probe returns gate status
- [x] Kill switch runbook written and complete

### Testing
- [x] P1.32 targeted suite: 80 PASS, 0 FAIL
- [x] P1.31 regression: 176 PASS
- [x] P1.30 regression: 231 PASS
- [x] P1.29 regression: 312 PASS
- [x] Entire backend: exit code 0
- [x] Frontend vitest: 414 PASS

### Data Quality
- [x] Disclaimer present in all AI responses
- [x] Data source attributable (SourceRef)
- [x] No fabrication patterns (financial_safety_postprocessor active)
- [x] Zero zero-tolerance violations (cumulative = 0 across all soak phases)

---

## P1 — Recommended (Non-Blocking)

- [ ] Real provider activated and validated (deferred to P1.33 — staging key needed)
- [ ] Official pricing verified from authoritative source
- [ ] User-facing invite flow integrated in frontend
- [ ] Frontend feedback UI components implemented
- [ ] Frontend analytics event emission implemented
- [ ] Daily quota enforcement per user (rate limiting by user_id)
- [ ] Provider cost dashboard

---

## P2 — Post-Launch Optimization

- [ ] Analytics dashboard / BI queries
- [ ] Batch invite code generation tool
- [ ] Feedback review workflow UI
- [ ] Advanced export formats
- [ ] Mobile PWA refinement
- [ ] All financial modules polished
- [ ] Multi-provider switching
- [ ] Personalized stock recommendations
- [ ] Provider real-time cost display

---

## Release Decision

| Criterion | Status |
|---|---|
| All P0 items pass | YES |
| Live > 1% | NO (blocked) |
| Public production | NO (blocked) |
| Legacy removal | NO (blocked) |
| Invite-only MVP ready | **YES** |

**Recommendation**: Invite-only MVP launch ready pending project owner sign-off.  
Real provider activation (P1.33) requires: DEEPSEEK_API_KEY_STAGING + pricing verification + explicit authorization.
