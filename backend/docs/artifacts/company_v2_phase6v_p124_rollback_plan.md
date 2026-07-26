# Phase 6V-P1.24 Rollback Plan

## Current State (P1.24 State B)

No promotion was applied. Rollback is not required.

| Field | Value |
|---|---|
| Intended staging rollout | 75% |
| Config version | 8 |
| Stable bucket salt | pi_v1 |
| Deployed effective runtime | None (Docker not available) |
| Rollback required | false |

## Hypothetical Post-Promotion Rollback (If P1.25 Succeeds)

If P1.25 successfully deploys 100%/v9 and a rollback is needed:

```text
Rollout before: 100% / config_version=9
Rollback target: 75% / config_version=10
Stable bucket salt: pi_v1 (NEVER changes)
```

### Steps

1. Update `.env.staging.local`:
   ```
   PI_CANARY_ROLLOUT_PERCENT=75
   PI_CANARY_CONFIG_VERSION=10
   PI_CANARY_STABLE_BUCKET_SALT=pi_v1
   ```

2. Restart containerized staging service:
   ```bash
   docker compose -p tradingagents-p124-staging \
     -f docker-compose.yml -f docker-compose.staging.yml \
     --env-file .env.staging.local \
     up -d --build backend
   ```

3. Wait for healthcheck, then probe:
   ```bash
   docker compose ... exec -T backend \
     cat /tmp/tradingagents-runtime/pi_canary_snapshot.json
   ```

4. Verify:
   ```json
   {"rollout_percent": 75, "config_version": 10, "stable_bucket_salt_version": "pi_v1"}
   ```

### Invariants During Rollback

- `live = false` — NEVER changes
- `production_enabled = false` — NEVER changes
- `provider_serving_calls = 0` — NEVER changes
- `stable_bucket_salt = "pi_v1"` — NEVER changes
- `config_version` — ONLY increases (10 > 9)
- Repository defaults (`rollout=0.0, status=proposed`) — NEVER changes

### Zero-Tolerance Triggers

If any of the following occur during 100% observation, immediately roll back:
- Pi output visible to any real user
- `provider_serving_calls > 0`
- Memory monotonic drift over 4 consecutive windows
- Pi p95 >= 4800ms in 2+ consecutive non-burst windows
- Any database write from Pi agent code path
- Any safety violation
