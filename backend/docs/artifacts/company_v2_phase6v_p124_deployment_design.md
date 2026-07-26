# Phase 6V-P1.24 — Containerized Staging Deployment Design

## Status: BLOCKED (Docker not installed)

Docker Engine is required but not installed on this machine.
Install via: `brew install --cask docker-desktop`

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│  Compose Project: tradingagents-p124-staging            │
│  Network:         staging-internal                       │
│                                                         │
│  ┌──────────┐    ┌───────────────────────────────────┐  │
│  │  redis   │    │  backend:8000                     │  │
│  │ (alpine) │◄───│  FastAPI + uvicorn                │  │
│  └──────────┘    │  Settings.pi_canary_rollout=75    │  │
│                  │  load_canary_config()             │  │
│                  │  → snapshot → /tmp/.../snap.json  │  │
│                  └───────────────────────────────────┘  │
│                           ↕ 127.0.0.1:18000              │
└─────────────────────────────────────────────────────────┘
```

## Gate C Verification Flow

```
1. docker compose up -d --build
2. healthcheck: curl 127.0.0.1:18000/health → 200 OK
3. docker compose exec -T backend cat /tmp/tradingagents-runtime/pi_canary_snapshot.json
4. Verify:
   - rollout_percent = 75
   - config_version = 8
   - stable_bucket_salt_version = pi_v1
   - authorization_status = authorized
   - evidence_mode = containerized_deployed_staging_runtime
   - live = false
   - production_enabled = false
   - deployment_sha = <current_git_sha>
   - process_id = <real_PID>
5. Gate C = PASS → proceed to 100%/v9
```

## Config Environment Variable Mapping

| Settings Field | Environment Variable | Repository Default | Staging Value |
|---|---|---|---|
| `pi_canary_rollout_percent` | `PI_CANARY_ROLLOUT_PERCENT` | 0.0 | 75.0 |
| `pi_canary_config_version` | `PI_CANARY_CONFIG_VERSION` | 1 | 8 |
| `pi_canary_stable_bucket_salt` | `PI_CANARY_STABLE_BUCKET_SALT` | pi_v1 | pi_v1 |
| `pi_canary_authorization_status` | `PI_CANARY_AUTHORIZATION_STATUS` | proposed | authorized |
| `pi_canary_environment` | `PI_CANARY_ENVIRONMENT` | staging | staging |
| `pi_canary_snapshot_path` | `PI_CANARY_SNAPSHOT_PATH` | "" | /tmp/tradingagents-runtime/pi_canary_snapshot.json |
| `pi_canary_environment_kill_switch` | `PI_CANARY_ENVIRONMENT_KILL_SWITCH` | false | false |
| `pi_canary_agent_kill_switch` | `PI_CANARY_AGENT_KILL_SWITCH` | false | false |

## Isolation Requirements

| Requirement | Design |
|---|---|
| Compose project | `tradingagents-p124-staging` |
| Network | `staging-internal` |
| Backend host port | `127.0.0.1:18000` |
| Frontend host port | `127.0.0.1:18080` |
| Database | Dedicated staging DB only |
| Redis | Scoped within staging-internal network |
| Public exposure | NONE |
| Secrets committed | NONE (.env.staging.local gitignored) |
