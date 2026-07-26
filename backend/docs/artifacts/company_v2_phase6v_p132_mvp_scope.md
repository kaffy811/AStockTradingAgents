# Phase 6V-P1.32 — MVP Scope

**Phase**: 6V-P1.32  
**Date**: 2026-07-26  
**Status**: MVP Release Candidate — State B (Real Provider NOT_EXECUTED)

---

## MVP Core User Loop

```
User Login
→ Search or select stock
→ View company core financial info
→ Ask financial question
→ Receive real data
→ AI Analysis
→ Review Agent validation
→ Single visible answer returned
→ Data source + update time + disclaimer shown
→ Follow-up questions
→ History saved
→ User rates (thumbs up/down) or submits feedback
→ System records success rate, fallback, cost, errors
```

## MVP Scope — Implemented in P1.32

| Feature | Status |
|---------|--------|
| User login / auth | EXISTING (P-series phases) |
| Stock search | EXISTING |
| Company financial page (5-tab) | EXISTING |
| Chat single-turn | EXISTING |
| Chat multi-turn | EXISTING |
| History sessions | EXISTING |
| Legacy fallback (100%) | EXISTING |
| Disclaimer | EXISTING |
| Data source attribution | EXISTING |
| Review Agent gate | EXISTING |
| Provider control plane | P1.31 |
| Provider call path wiring | **P1.32** |
| Invite-only access | **P1.32** |
| Answer feedback (thumbs/report) | **P1.32** |
| Analytics events (MVP funnel) | **P1.32** |
| Structured error monitoring | **P1.32** |
| Kill switch runbook | **P1.32** |
| MVP release checklist | **P1.32** |

## Out of Scope — P1.32 and MVP Launch

- Live rollout > 1%
- Public production deployment
- Ordinary external user traffic
- Legacy executor removal
- Real provider activation (moved to P1.33 — requires staging key)
- Analytics dashboard / BI platform
- Advanced export formats
- All financial modules perfectly polished
- Personalized recommendations
- Multi-provider switching
- Mobile PWA fully optimized

## MVP Non-Blocking Issues (Post-Launch Backlog)

See: `company_v2_mvp_post_launch_backlog.md`
