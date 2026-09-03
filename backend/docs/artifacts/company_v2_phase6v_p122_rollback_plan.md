# Phase 6V-P1.22 Rollback Plan

**Phase:** 6V-P1.22  
**Current rollout:** 75% (config_version=8, stable_bucket_salt=pi_v1)  
**Base SHA:** 43130fcf8e348b6c8dbdb27accee1e304638b95d  
**Status:** NOT APPLIED — rollback verified offline only  
**Rollback required:** false  
**Rollback applied:** false  

---

## Rollback Target

| Parameter | Current (P1.22) | Rollback Target |
|---|---|---|
| rollout_percent | 75 | 50 |
| config_version | 8 | 9 |
| stable_bucket_salt | pi_v1 | pi_v1 (unchanged) |
| live | false | false |
| production_enabled | false | false |

Config version increments to 9 on rollback to ensure no cache confusion between 75% and 50% states. The stable_bucket_salt remains pi_v1 to maintain deterministic bucket assignment for the retained 50% cohort.

---

## Trigger Conditions

Rollback from 75% to 50% is triggered by ANY of the following:

- Gate G (Safety): safety_correctness_rate < 1.0 OR zero_tolerance_violations > 0 OR pi_leakage > 0
- Gate H (Reliability): timeout_rate > 0.01 OR fallback_rate > 0.05 OR legacy_stall_rate > 0
- Gate I (Performance): Pi_p95 >= 5000ms in any window (hard rollback threshold)
- Gate J (Resources): CPU p95 >= 80% sustained OR memory_rss >= 512MB OR FD >= 600
- Any production secret exposed in shadow path
- Any business_writes > 0 or provider_serving_calls > 0 in dry-run mode

---

## Rollback Steps

### Step 1 — Update canary configuration

```bash
# Set rollout back to 50%, bump config_version to 9
export CANARY_ROLLOUT_PERCENT=50
export CANARY_CONFIG_VERSION=9
# stable_bucket_salt remains pi_v1
```

### Step 2 — Restart workers

```bash
# Rolling restart to pick up new config
supervisorctl restart tradingagents-worker:*
# OR (Docker)
docker compose restart backend
```

### Step 3 — Verify rollback

```bash
# Confirm effective config
curl -s http://localhost:8000/internal/canary/snapshot | python3 -m json.tool
# Expected: rollout_percent=50, config_version=9
```

### Step 4 — Run smoke tests

```bash
pytest tests/test_phase6v_p1*.py -x -q
# Expected: all pass with rollout=50 fixture
```

### Step 5 — Confirm no new violations

- Monitor selection_rate for 1 observation window (~1400 eligible, ~700 selected)
- Confirm zero_tolerance_violations = 0
- Confirm Pi_p95 returns to historical 50% band

---

## Rollback Verification

After rollback (if applied):

- selection_rate should converge to 0.50 (+/- 0.01)
- 50% cohort (bucket < 5000) is strict subset of prior 75% cohort (bucket < 7500)
- No requests that were NOT in the 50% cohort will suddenly receive Pi responses
- config_version=9 prevents any cached 75% decisions from being replayed

---

## Non-Application Note

As of P1.22 completion, rollback was NOT required and NOT applied. All safety, reliability, performance, and resource gates passed. The soak concluded with the decision to continue at 75% and proceed to P1.23 to resolve Gate C (deployed runtime probe).

**Evidence SHA:** TBD_evidence_sha
