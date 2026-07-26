# Phase 6V-P1.21 Rollback Plan

## Overview

This document describes the rollback procedure for the 75% staging shadow promotion
(Phase 6V-P1.21). Rollback reverts the shadow rollout from 75% to 50% via a
monotonic config version bump.

**Important:** `stable_bucket_salt` remains `'pi_v1'` during rollback. Rollback changes
only `rollout_percent` and `config_version`. It does NOT change the bucket salt.

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
pi_canary_rollout_percent = 50      # revert from 75 to 50
pi_canary_config_version = 9        # bump forward, NOT back to 7 or 8
# stable_bucket_salt = "pi_v1"      # UNCHANGED — do not modify
```

**Why config_version=9 and not revert to 7 or 8?**

Config version is **monotonic by design**. Reverting to a lower version number
(e.g., 7 or 8) would violate the monotonic invariant and could cause version
confusion in diagnostics logs and audit trails. A rollback is expressed as a
*forward* bump to a new version number (9) that encodes the rollback intent.
This preserves audit trail integrity.

**Why stable_bucket_salt unchanged?**

The stable_bucket_salt `'pi_v1'` is decoupled from config_version as of P1.21.
Rollback MUST NOT change the salt, as this would re-bucket all users (breaking
the cohort nesting invariant). The 50% cohort used during rollback will be the
same 50% cohort as P1.20 — the original, verified safe cohort.

### Step 2: Verify staging config immediately

```bash
# Confirm rollout reverted to 50%
pytest backend/tests/fundamental/test_phase6v_p121_seventy_five_percent_shadow.py \
    -k "test_rollout" -v

# Confirm config_version is now 9
grep -r "pi_canary_config_version" backend/app/core/config.py

# Confirm salt is still pi_v1
grep -r "stable_bucket_salt" backend/app/core/config.py
```

### Step 3: Confirm shadow load drops to 50%

Monitor the next 2 observation windows. Confirm:
- `selected / eligible ~= 0.50` (+-2%)
- No further hard rollback conditions triggered

---

## Verification Steps After Rollback

1. Run the full P1.21 rollback verification suite:
   ```bash
   pytest backend/tests/fundamental/ -k "p121" -v --tb=short
   ```

2. Confirm all safety invariants remain enforced:
   - `live = false`
   - `production_enabled = false`
   - `provider_calls_serving = 0`
   - `canary_mode = shadow`
   - `stable_bucket_salt = "pi_v1"` (unchanged)

3. Confirm repository defaults unchanged:
   - `pi_canary_rollout_percent` repo default = 0.0
   - `pi_canary_stable_bucket_salt` repo default = `"pi_v1"`

---

## Rollback Artifacts to Create

Upon triggering rollback, create the following artifacts in
`backend/docs/artifacts/`:

| Artifact | Description |
|---|---|
| `company_v2_phase6v_p121_rollback_applied.json` | Records the rollback event: trigger condition, rollout_before=75, rollout_after=50, config_version_before=8, config_version_after=9, stable_bucket_salt=pi_v1 (unchanged) |
| `company_v2_phase6v_p121_post_rollback_verification.json` | Records verification results after rollback: 2 observation windows at 50%, all safety gates re-confirmed |

Both artifacts must be created before the rollback phase is considered complete.

---

## Notes

- Rollback does **not** affect production or live serving (both remain false and
  unchanged).
- Rollback does **not** change repository defaults.
- Rollback does **not** change `stable_bucket_salt` — it remains `'pi_v1'`.
- The rollback is applied only to the staging shadow fixture override.
- config_version=9 is chosen for rollback (not reverting to 7 or 8) to prevent
  replay attacks on the configuration state machine and to maintain the monotonic
  version invariant.
- After rollback, a new phase (P1.22) must be initiated to re-attempt 75%
  soak with root cause analysis of the triggering condition.
- The 100% promotion decision is unaffected by this rollback plan — promotion
  requires a separate owner authorization artifact regardless of rollback status.
- Cohort nesting is preserved: the 50% rollback cohort is identical to P1.20's
  50% cohort (same salt), ensuring audit trail continuity.
