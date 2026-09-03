# Staging Canary Approval Checklist (proposal — no approvals recorded)

Required approvers (roles only, no personal data):
1. Agent/Runtime owner — [ ]
2. Release/Reliability owner — [ ]
3. (Optional) Product/Compliance owner — [ ]

Each approver must confirm:
- [ ] Shadow Gate passed (P1.6.8, sha 808b367)
- [ ] Browser B01–B05 passed
- [ ] Full30 30/30 executed with zero hard failures (P1.6.6)
- [ ] Review Policy signed (Class A/B/C/D = 15/10/5/0)
- [ ] Capability gap (annual-only) acknowledged; no silent degradation
- [ ] Legacy defects tracked separately; Pi does not replicate them
- [ ] Kill switches validated (global/environment/agent; S05)
- [ ] Auto rollback validated (S02/S04; zero-tolerance ignores sample size)
- [ ] rollout_percent=0 at approval time; staging only; no production permission
- [ ] Approval ticket reference recorded (redacted)

`authorization_status` may become `approved` only when every box is checked by the required approvers.
