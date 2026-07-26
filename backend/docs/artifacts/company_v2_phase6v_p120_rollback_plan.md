# Phase 6V-P1.20 Rollback Plan

## Overview

This document describes the rollback procedure for the sustained 50% staging shadow
soak (Phase 6V-P1.20). Rollback reverts the shadow rollout from 50% to 25% via a
monotonic config version bump.

---

## Trigger Conditions (Hard Rollback)

Any of the following conditions triggers an immediate hard rollback:

1. **pi_p95_ms >= 5000ms** in any observation window or combined result
2. **zero_tolerance_violations > 0** (fabricated URL, wrong entity, wrong year, wrong
   report type, provenance failure, stale wrong selection, third-party URL, business
   write, double write, unknown write, trace mismatch, terminal missing)
3. **unexpected_timeout_rate > 1%** in any window
4. **fallback_rate > 10%** in any window
5. **pi_over_6s_count > 0** in any window
6. **pool_exhaustion > 0** detected
7. **PendingRollbackError > 0** detected
8. **provider_serving_calls > 0** (any live provider call in shadow mode)
9. **business_writes > 0** (any write to production state)
10. **raw_500_count or raw_503_count > 5** in any window
11. **Monotonic upward drift** in memory, FD, or task count confirmed over 2+ consecutive windows

---

## Immediate Rollback Action

### Step 1: Update staging test fixture config override

Set the following fields in the staging test fixture:

```python
pi_canary_rollout_percent = 25      # revert from 50 to 25
pi_canary_config_version = 8        # bump forward, NOT back to 6 or 7
```

**Why config_version=8 and not revert to 6 or 7?**

Config version is **monotonic by design**. Reverting to a lower version number
(e.g., 6 or 7) would violate the monotonic invariant and could cause version
confusion in diagnostics logs and audit trails. A rollback is expressed as a
*forward* bump to a new version number (8) that encodes the rollback intent.
This preserves audit trail integrity.

Note: `config_version=8` is chosen (not 7) to prevent replay attacks on the
configuration state machine. Version 7 is the current production state; jumping
to 8 for rollback ensures that a future re-promotion cannot be confused with
the current rollback state.

### Step 2: Verify staging config immediately

```bash
# Confirm rollout reverted
pytest backend/tests/fundamental/test_phase6v_p120_sustained_fifty_shadow.py \
    -k "test_rollout" -v

# Confirm config_version is now 8
grep -r "pi_canary_config_version" backend/app/core/config.py
```

### Step 3: Confirm shadow load drops to 25%

Monitor the next 2 observation windows. Confirm:
- `selected / eligible ~= 0.25` (+-2%)
- No further hard rollback conditions triggered

---

## Verification Steps After Rollback

1. Run the full P1.20 rollback verification suite:
   ```bash
   pytest backend/tests/fundamental/ -k "p120" -v --tb=short
   ```

2. Confirm all safety invariants remain enforced:
   - `live = false`
   - `production_enabled = false`
   - `provider_calls_serving = 0`
   - `canary_mode = shadow`

3. Confirm repository defaults unchanged:
   - `pi_canary_rollout_percent` repo default = 0.0
   - `pi_canary_config_version` repo default = 1

---

## Rollback Artifacts to Create

Upon triggering rollback, create the following artifacts in
`backend/docs/artifacts/`:

| Artifact | Description |
|---|---|
| `company_v2_phase6v_p120_rollback_applied.json` | Records the rollback event: trigger condition, rollout_before=50, rollout_after=25, config_version_before=7, config_version_after=8 |
| `company_v2_phase6v_p120_post_rollback_verification.json` | Records verification results after rollback: 2 observation windows at 25%, all safety gates re-confirmed |

Both artifacts must be created before the rollback phase is considered complete.

---

## Notes

- Rollback does **not** affect production or live serving (both remain false and
  unchanged).
- Rollback does **not** change repository defaults.
- The rollback is applied only to the staging shadow fixture override.
- config_version=8 is chosen for rollback (not reverting to 7 or 6) to prevent
  replay attacks on the configuration state machine.
- After rollback, a new phase (P1.21) must be initiated to re-attempt 50%
  soak with root cause analysis of the triggering condition.
- The 75% promotion decision is unaffected by this rollback plan — promotion
  requires a separate owner authorization artifact regardless of rollback status.
