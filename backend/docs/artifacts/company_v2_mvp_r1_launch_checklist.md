# MVP-R1 Launch Checklist

**Phase**: MVP-R1  
**Date**: 2026-07-26  
**Status**: READY (State B — legacy MVP)

---

## P0 — Must Pass Before Any User Invited

- [x] L1 — Core User Flow PASS
- [x] L2 — Invite-Only Access PASS
- [x] L3 — Data Source and Freshness PASS
- [x] L4 — Chat and Multi-Turn PASS
- [x] L5 — Review and Disclaimer PASS
- [x] L6 — Legacy Fallback PASS
- [x] L7 — No Duplicate or Session Mix-Up PASS
- [x] L8 — Feedback PASS
- [x] L9 — Analytics PASS
- [x] L10 — Monitoring PASS
- [x] L11 — Quota and Abuse Protection PASS
- [x] L12 — Kill Switches PASS
- [x] L13 — Canonical Tests PASS
- [x] L14 — Secret Protection PASS

## Real Provider Gates (State B — NOT_EXECUTED)

- [x] RP1 — Formal Control Path PASS (8/8 checks wired)
- [ ] RP2 — Staging Credential NOT_EXECUTED
- [ ] RP3 — Real Connectivity NOT_EXECUTED
- [ ] RP4 — Usage and Cost NOT_EXECUTED
- [ ] RP5 — Safety and Fallback NOT_EXECUTED
- [x] RP6 — Replay Restoration PASS

## Invite Configuration

- [ ] Generate invite codes for first 20–50 users
- [ ] Set daily quota: 10 questions/user
- [ ] Set global daily quota: 300 questions
- [ ] Set weekly cost budget: ¥50

## What To Tell Users

- "基础 AI 分析功能上线邀请内测"
- Do NOT mention DeepSeek
- Do NOT claim real-time AI model calling is active
- Do mention: 数据来源、更新时间、AI免责声明

## Go / No-Go Decision

**State B — Legacy MVP READY**
- invite_only_legacy_mvp = READY
- real_provider_feature_visible = false
- Public production: NOT authorized
