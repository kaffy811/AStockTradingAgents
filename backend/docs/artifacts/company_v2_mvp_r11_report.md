# Phase MVP-R1.1 — Invite-Only Launch

**Phase**: MVP-R1.1  
**Date**: 2026-07-26  
**Branch**: mvp-r11/invite-launch-week1 -> release/demo-staging  
**Status**: **INVITE_ONLY_WAVE1_READY — State B (Awaiting First Users)**

---

## 1. What Changed

| Item | Before | After |
|---|---|---|
| Quota settings | not present | mvp_daily_quota_per_user=10, global=300 |
| Quota enforcement | not implemented | GET /mvp/quota/check/{user_id} |
| Wave management | not present | wave1/2/3 limits + current_wave setting |
| Kill switches | undefined | 7 env-driven switches + GET /mvp/wave/status |
| Public registration | no setting | mvp_public_registration_enabled=false |
| Kill switch drill | not done | 7 switches verified |
| L1-L16 gates | L5/L6/L13 missing | All 16 PASS |

---

## 2. Gate Assessment

**L1-L16: 16 PASS - 0 FAIL**

---

## 3. State B

- `DEEPSEEK_API_KEY_STAGING` = NOT_SET
- Real provider calls = 0
- Cost = Y0
- Config version = 12 (unchanged)
- Provider mode = staging_replay

---

## 4. Product Messaging

Users must see (and never see):

| Must show | Must NOT show |
|---|---|
| Invite-only test version | DeepSeek is live |
| Data for reference only | Real-time AI answer |
| Not investment advice | Production-grade AI advisor |
| Disclaimer | Guarantee accuracy / guarantee returns |

---

## 5. Wave Release Plan

| Wave | Users | Release Condition |
|---|---|---|
| Wave 1 | 10 | Now authorized. No P0. |
| Wave 2 | +20 | After Wave 1: success >=95%, fallback 100%, 0 safety events |
| Wave 3 | +20 | After Wave 2 stability |

---

## 6. Final Decision

| Field | Value |
|---|---|
| INVITE_ONLY_WAVE1_READY | **true** |
| Invite users may be added | **true** |
| Wave 1 max users | 10 |
| Real AI provider advertised | false |
| Public production authorized | false |
| Further pre-launch phases required | **false** |

---

## 7. Owner Steps to Launch Wave 1

```bash
# 1. Generate invite code for one user
curl -X POST https://your-staging-host/mvp/invites \
  -H "Authorization: Bearer <admin_token>" \
  -H "Content-Type: application/json" \
  -d '{"email":"tester@example.com","max_uses":1,"note":"Wave 1 internal tester"}'

# Response includes: invite_code

# 2. Send invite_code to user securely (not in Git)

# 3. User redeems:
curl -X POST https://your-staging-host/mvp/invites/redeem \
  -H "Content-Type: application/json" \
  -d '{"invite_code":"<code_from_step_1>"}'

# 4. Check wave status:
curl https://your-staging-host/mvp/wave/status

# 5. Check quota for user:
curl https://your-staging-host/mvp/quota/check/<user_id>
```
