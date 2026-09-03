# Phase 6V-P1.23 Report — Deployed Runtime Probe Closure

**Outcome: State B** — Gate C = UNKNOWN, runtime probe not closeable, 100% promotion NOT executed

| Field | Value |
|---|---|
| Phase | 6V-P1.23 |
| Base SHA | 779da4cd3f33ff6a1b21b7c36cf182b7b2c4500d |
| Generated At | 2026-07-23T17:00:00.000000+00:00 |
| Rollout (before) | 75% / config_version=8 |
| Rollout (after) | 75% / config_version=8 (unchanged) |
| Promotion applied | No |
| Gate C status | UNKNOWN (unchanged from P1.22) |

---

## Objective

P1.23 aimed to close **Gate C** — the sole remaining blocker for the conditional owner authorization to promote rollout from 75% to 100%. Gate C requires a deployed staging runtime probe confirming that the live staging process reads `rollout_percent=75` and `authorization_status=authorized` from its actual environment.

---

## Deployment Investigation Findings

A systematic investigation was conducted to locate the running staging instance:

### What was found

- **docker-compose.yml** exists in the repository root — deployment infrastructure is present.
- Deployment type: **self-hosted VPS + Docker Compose**.
- Startup command: `docker compose up -d`.
- Environment source: `.env` file on the staging server (not committed to the repository).

### What was not found

- **No CI/CD pipeline**: `.github/workflows/` does not exist. No automated pipeline to probe staging in CI.
- **No running staging service**: `curl --noproxy localhost http://localhost:8000` returned exit code 7 (Connection refused). No service is listening on localhost:8000 in the current environment.
- **No staging URL**: No staging URL was discovered in any config files, docker-compose.yml, .env.example, or documentation.
- **No pi_canary vars in .env.example**: `.env.example` does not contain `PI_CANARY_ROLLOUT_PERCENT` or any `pi_canary_*` variables. Staging overrides require manual configuration on the server.
- **Local proxy is not staging**: `http_proxy=http://127.0.0.1:7890` is a local proxy tool (e.g., Clash/V2Ray). It is not a staging service.

### Conclusion

The staging deployment exists as infrastructure (docker-compose.yml) but is not accessible from the current environment. Probing Gate C requires direct VPS/SSH access to the running staging container.

---

## Runtime Probe Attempt

A runtime probe was executed using `get_effective_shadow_config_snapshot()` with real `pydantic_settings.Settings` (not a mock). The probe ran successfully and returned a valid snapshot:

```json
{
  "rollout_percent": 0.0,
  "config_version": 1,
  "authorization_status": "proposed",
  "evidence_mode": "runtime_loader_integration_verified"
}
```

**Why this does not satisfy Gate C:**

The probe ran in the local environment without `PI_CANARY_ROLLOUT_PERCENT=75` set. It returned repository defaults (`rollout=0.0`, `proposed`) rather than the staging values (`rollout=75`, `authorized`). The probe confirms the runtime loader is correctly wired to `pydantic_settings.Settings`, but it does not confirm the staging deployment's actual configuration.

Section 7 requires the probe to run against the **actual deployed staging process** — inside the staging Docker container configured with the staging `.env`. A local probe with repository defaults does not satisfy this requirement.

**Gate C status after probe: UNKNOWN** (no change from P1.22).

---

## Gate Results

| Gate | Status | Notes |
|---|---|---|
| A | PASS | Carried forward from P1.22 |
| B | PASS | Carried forward from P1.22 |
| C | UNKNOWN | Probe performed but does not satisfy Section 7 deployed runtime requirements |
| D–N | Not evaluated | Promotion not executed; these gates are not applicable |

---

## State B Outcome

The conditional owner authorization requires Gate C = PASS. Since Gate C remains UNKNOWN:

- **Promotion authorized**: No
- **Promotion attempted**: No
- **Promotion applied**: No
- **Rollback required**: No
- **Rollout after phase**: 75% / config_version=8 / stable_bucket_salt=pi_v1 (unchanged)
- **Shadow continuation**: 75% shadow soak continues

Cumulative soak status through P1.22: **45,373 selections, 0 violations**. The shadow remains healthy.

---

## Test Results

All test suites pass:

| Suite | Collected | Passed | Failed | Skipped |
|---|---|---|---|---|
| P1.23 targeted | 156 | 156 | 0 | 0 |
| Cross-phase P1.* | 3,159 | 3,159 | 0 | 0 |
| Full fundamental | 4,712 | 4,697 | 0 | 15 |
| Entire backend | 6,543 | 6,528 | 0 | 15 |
| Frontend vitest (62 files) | 688 | 688 | 0 | 0 |
| Frontend build | — | PASS | — | — |
| Secret scan | — | clean | — | — |

*15 skips: external data source unavailable in CI (expected).*

---

## Recommendation for P1.24

**Objective**: Close Gate C via deployed staging runtime probe.

**Required steps**:

1. Gain SSH/direct access to the staging VPS server.
2. Confirm the staging `.env` contains `PI_CANARY_ROLLOUT_PERCENT=75` and `PI_CANARY_CONFIG_VERSION=8`.
3. Confirm the staging Docker container is running (`docker compose ps`).
4. Execute the runtime probe via one of:
   - SSH into the running container: `docker compose exec backend python -c "from app.canary import get_effective_shadow_config_snapshot; import asyncio; print(asyncio.run(get_effective_shadow_config_snapshot()))"`
   - Or expose a `/diagnostics/canary-snapshot` endpoint and call it from the probe script.
5. Confirm probe returns `rollout_percent=75.0` and `authorization_status=authorized`.
6. Record probe result — Gate C = PASS.
7. Proceed with conditional owner authorization and promote to 100% (config_version=9).

---

*Phase 6V-P1.23 | State B | 2026-07-23*
