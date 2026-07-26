# Phase 6V-P1.25 Rollback Plan

## Current State

| Field | Value |
|-------|-------|
| rollout | 100 |
| config_version | 9 |
| salt | pi_v1 |
| live | false |
| production_enabled | false |
| environment | containerized staging (tradingagents-p125-staging) |

## Rollback Target

| Field | Value |
|-------|-------|
| rollout | 75 |
| config_version | 10 |
| salt | pi_v1 (unchanged) |

## Rollback Steps

### Step 1 — Update `.env.staging.local`

Edit `.env.staging.local` and set:

```
PI_CANARY_ROLLOUT_PERCENT=75
PI_CANARY_CONFIG_VERSION=10
```

All other variables remain unchanged, including `PI_CANARY_STABLE_BUCKET_SALT=pi_v1`.

### Step 2 — Recreate Backend Container

```bash
DEPLOYMENT_SHA=$(git rev-parse HEAD) \
docker compose \
  -p tradingagents-p125-staging \
  -f docker-compose.yml \
  -f docker-compose.staging.yml \
  --env-file .env.staging.local \
  up -d --force-recreate backend
```

### Step 3 — Wait for Health

```bash
curl http://127.0.0.1:18000/health
```

Expected response: `{"status":"ok"}`

Retry with a short delay if the container is still starting.

### Step 4 — Verify Snapshot

```bash
docker exec tradingagents-p125-staging-backend-1 \
  cat /tmp/tradingagents-runtime/pi_canary_snapshot.json
```

### Step 5 — Confirm Rollback Values

Verify the snapshot contains:

| Field | Expected |
|-------|----------|
| rollout | 75 |
| config_version | 10 |
| salt | pi_v1 |
| live | false |
| production_enabled | false |

## Invariants Preserved

- **stable_bucket_salt**: `pi_v1` — never changed during any rollout or rollback operation; bucket assignments remain stable across config versions.
- **config_version monotonic**: versions proceed `8 → 9 → 10`; a rollback increments the version (does not reuse 8) to prevent config cache collisions.
- **live=false always**: live serving is not activated by any rollout percentage change; this requires an explicit, separate authorization step.

## Rollback Verified

- Tested: **yes**
- Verified in this phase
- process_started_at at time of rollback test: `2026-07-25T01:56:16.259232+00:00`
- Rollback execution confirmed: container recreated with rollout=75, config_version=10, salt=pi_v1, snapshot sanitized=true

## Production Impact

**NOT affected.** This rollback procedure applies exclusively to the containerized staging environment (`tradingagents-p125-staging`). Production deployments are governed by a separate authorization and promotion pipeline and are not modified by any operation in this phase.
