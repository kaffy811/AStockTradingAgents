# MVP Post-Launch Backlog

**Phase**: Post-P1.32  
**Date**: 2026-07-26  
**Type**: Non-blocking issues and future enhancements

---

## P1.33 — Real Provider Activation (Next Phase)

**Prerequisite**: Provision `DEEPSEEK_API_KEY_STAGING`

Steps:
1. Provision staging-only DeepSeek API key at platform.deepseek.com
2. Verify official model IDs (`deepseek-chat` for V3, `deepseek-reasoner` for R1)
3. Verify pricing from platform.deepseek.com/api-docs/pricing
4. Update `deepseek_prices.json`: `verified=true`, `source_url`, `source_retrieval_date`
5. Set `enabled_for_staging_real=true` for `deepseek-chat`
6. Set `PI_REAL_PROVIDER_ENABLED=true` and `PI_REAL_PROVIDER_KILL_SWITCH=false` in staging env
7. **Obtain explicit project owner authorization**
8. Execute P1.33: ≤100 requests, ≤¥100 CNY, restore replay after

---

## MVP-R1 — Invite-Only Launch

**After P0 checklist cleared:**

1. Invite 20–50 initial users
2. Set per-user daily quota (10 questions/day default)
3. Set total cost budget (¥50/week)
4. Monitor daily via `mvp_analytics_event` queries
5. Weekly feedback review from `chat_feedback`
6. One-week retrospective before expanding

---

## Frontend Integration Backlog

| Item | Priority |
|---|---|
| Frontend invite code input flow | P1 |
| Frontend feedback UI (thumbs up/down/report modal) | P1 |
| Frontend analytics event emission | P1 |
| User quota display ("N questions remaining today") | P2 |
| Provider cost transparency ("powered by DeepSeek") | P2 |

---

## Analytics & Monitoring Backlog

| Item | Priority |
|---|---|
| Analytics dashboard (query templates) | P2 |
| Automated funnel reports (weekly) | P2 |
| Feedback review workflow UI | P2 |
| Error alerting integration (Slack/email on P0) | P1 |
| Cost tracking dashboard | P1 |
| 7-day retention query | P2 |

---

## Product Quality Backlog

| Item | Priority |
|---|---|
| Mobile PWA fully optimized | P2 |
| All financial modules polished | P2 |
| Advanced export (PDF, CSV) | P2 |
| Personalized stock recommendations | P2 |
| Multi-language full coverage | P2 |
| Dark mode refinement | P2 |

---

## Infrastructure Backlog

| Item | Priority |
|---|---|
| Batch invite code generation CLI | P1 |
| Provider cost alerts (> ¥10/day) | P1 |
| Automated kill switch trigger on budget breach | P2 |
| Multi-provider fallback chain | P2 |
| Read replica for analytics queries | P2 |

---

## Non-Blocking Issues for MVP Launch

The following do NOT block invite-only MVP launch:

- UI not perfectly polished
- Some animations not smooth
- Advanced export formats incomplete
- Rare stocks missing some indicators
- Answers occasionally slightly verbose
- Mobile not 100% perfect
- Personalized recommendations not built
- All financial modules not complete
- Multi-provider switching not complete
