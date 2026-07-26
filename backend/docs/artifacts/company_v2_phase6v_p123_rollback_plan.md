# Phase 6V-P1.23 Rollback Plan

**Status: FOR REFERENCE ONLY — Not triggered. Promotion was not applied.**

---

## Current State (Post-P1.23)

| Parameter | Value |
|---|---|
| Rollout percent | 75 |
| config_version | 8 |
| stable_bucket_salt | pi_v1 |
| Promotion applied | No |
| Rollback required | No |

Since the 100% promotion was not executed in P1.23 (Gate C = UNKNOWN, promotion blocked), the system remains at the P1.22 final state: **rollout=75, config_version=8**. No rollback action is needed.

---

## Hypothetical Rollback Procedure

*If 100% promotion had been applied and then required rollback, the following would apply:*

### Rollback Target

| Parameter | Rollback Value | Notes |
|---|---|---|
| rollout_percent | 75 | Return to prior stable shadow level |
| config_version | 10 | Increment from promotion cv=9 to signal rollback event |
| stable_bucket_salt | pi_v1 | Unchanged — preserve bucket stability |
| authorization_status | authorized | Remains authorized for 75% shadow |

### Rollback Steps

1. **Set environment variables** on staging server `.env`:
   ```
   PI_CANARY_ROLLOUT_PERCENT=75
   PI_CANARY_CONFIG_VERSION=10
   PI_CANARY_STABLE_BUCKET_SALT=pi_v1
   ```

2. **Restart staging service**:
   ```bash
   docker compose down && docker compose up -d
   ```

3. **Verify rollback via runtime probe**:
   ```python
   get_effective_shadow_config_snapshot()
   # Expected: rollout_percent=75.0, config_version=10, authorization_status=authorized
   ```

4. **Confirm zero provider serving calls** post-rollback.

5. **Record rollback artifacts**:
   - `company_v2_phase6v_p123_rollback_applied.json`
   - `company_v2_phase6v_p123_post_rollback_probe.json`

### Rollback Trigger Conditions

Rollback would be triggered if any of the following occurred after a 100% promotion:
- Gate D (zero violations confirmation) fails
- Unexpected provider serving calls detected
- live or production_enabled unexpectedly flipped to true
- Any canary selection violation observed

---

## Shadow Continuation Decision

With State B confirmed (no promotion), the shadow soak continues at:
- **75% rollout**, config_version=8, stable_bucket_salt=pi_v1
- Cumulative: 45,373 selections, 0 violations through P1.22
- Next phase (P1.24) will re-attempt Gate C closure

---

*Generated: 2026-07-23T17:00:00.000000+00:00*
*Phase: 6V-P1.23 State B*
*Base SHA: 779da4cd3f33ff6a1b21b7c36cf182b7b2c4500d*
