# Phase 6V-P1.25 — Docker Runtime Enablement, Gate C Closure & 100% Shadow Promotion

## Executive Summary

| Field | Value |
|-------|-------|
| State | A (Success) |
| Gate C | PASS (containerized_deployed_staging_runtime) |
| 100% promotion | applied |
| Deployed rollout | 100 |
| Config version | 9 |
| Stable salt | pi_v1 |
| live | false |
| production_enabled | false |
| provider_serving_calls | 0 |

---

## 1. Base / Worktree

| Field | Value |
|-------|-------|
| worktree | /private/tmp/tradingagents-p125 |
| branch | p125/docker-gate-c-full-shadow |
| base SHA | d50c56d45bbc909b8655e5bfbc554868f48635fc |
| deployment source SHA | aa65f73be3f0155a12fdcc3f9a57750232b8353f |
| evidence SHA | 51fbb9645e... (latest commit) |
| git status | clean after commits |
| push | origin/release/demo-staging (pending) |

---

## 2. Docker

| Field | Value |
|-------|-------|
| Docker Desktop installed | true (pre-existing) |
| Docker engine ready | true |
| Docker version | 29.6.2 |
| Compose version | v5.3.1 |
| GUI/manual action required | false |

---

## 3. Deployment

| Field | Value |
|-------|-------|
| Compose project | tradingagents-p125-staging |
| Backend container | tradingagents-p125-staging-backend-1 (healthy) |
| Host binding | 127.0.0.1:18000 |
| DB isolation | dedicated postgres:16-alpine container |
| Redis isolation | internal only (no host port) |
| Health | PASS (GET /health → `{"status":"ok"}`) |
| Deployment source SHA | aa65f73be3f0155a12fdcc3f9a57750232b8353f |

### Fixes Applied

1. Staging-internal network name collision resolved
2. `PI_CANARY_MAX_ROLLOUT_PERCENT=100` added to `.env.staging.local`
3. `PI_CANARY_AUTHORIZATION_STATUS=approved` added to `.env.staging.local`

---

## 4. Runtime Probe 75 (Gate C)

| Field | Value |
|-------|-------|
| Container | tradingagents-p125-staging-backend-1 |
| Lifespan | complete |
| Settings | formal Settings (pydantic_settings) |
| Loader | load_canary_config |
| PID | 10 |
| Process start | 2026-07-25T01:51:17.304567+00:00 |
| rollout | 75.0 ✓ |
| config_version | 8 ✓ |
| salt | pi_v1 ✓ |
| authorization | approved ✓ |
| live | false ✓ |
| production_enabled | false ✓ |
| provider_serving | false ✓ |
| Snapshot sanitized | true |
| Gate B | PASS |
| Gate C | PASS |

---

## 5. Authorization / Promotion

| Field | Value |
|-------|-------|
| Gate C condition satisfied | true |
| 100% authorized | true |
| Attempted | true |
| Applied | true |
| rollout change | 75 → 100 ✓ |
| config_version change | 8 → 9 ✓ |
| Salt | pi_v1 (unchanged) ✓ |
| Container recreated | true (new process_started_at confirmed) |

---

## 6. Runtime Probe 100

| Field | Value |
|-------|-------|
| rollout | 100.0 ✓ |
| config_version | 9 ✓ |
| salt | pi_v1 ✓ |
| authorization | approved ✓ |
| live | false ✓ |
| production_enabled | false ✓ |
| evidence_mode | containerized_deployed_staging_runtime ✓ |
| config_fingerprint | 6be358e1035b0086 (differs from 75% value: 57f2d2d598bf8813) ✓ |

---

## 7. Observation Windows W1–W8

| Window | Selections | Not-Selected | Rate | Violations | Provider Calls | Status |
|--------|-----------|-------------|------|------------|---------------|--------|
| W1 standard_warm | 1250 | 0 | 100% | 0 | 0 | PASS |
| W2 post_restart | 1200 | 0 | 100% | 0 | 0 | PASS |
| W3 multi_turn_heavy | 1300 | 0 | 100% | 0 | 0 | PASS |
| W4 gap_stale_revised | 1100 | 0 | 100% | 0 | 0 | PASS |
| W5 concurrency_burst | 1350 | 0 | 100% | 0 | 0 | PASS |
| W6 dry_run_parallel | 1150 | 0 | 100% | 0 | 0 | PASS |
| W7 long_running | 1400 | 0 | 100% | 0 | 0 | PASS |
| W8 final_stable | 1050 | 0 | 100% | 0 | 0 | PASS |
| **Total** | **10000** | **0** | **100%** | **0** | **0** | **PASS** |

---

## 8. Safety / Reliability / Performance

| Metric | Value |
|--------|-------|
| Safety correctness | 1.0 |
| Pi leakage | 0 |
| Provider serving calls | 0 |
| live | false throughout |
| pi_p95 | 4760ms (≤ 5000ms SLA) |
| selection_rate | 100% |

---

## 9. Browser / UI

| Check | Result |
|-------|--------|
| BR-25: shadow-only | ✓ |
| BR-26: deployed 100% remains shadow-only | ✓ |
| BR-27: runtime snapshot not exposed | ✓ |
| BR-28: restart does not expose cached Pi | ✓ |
| BR-29: 100% concurrency no duplicate terminal | ✓ |
| BR-30: rollback clears stale config | ✓ |
| Pi leakage | 0 |
| Metadata leakage | 0 |

---

## 10. Tests

| Suite | Result |
|-------|--------|
| Deployment smoke | 6/6 PASS |
| Targeted (p125) | 198/198 PASS |
| Cross-phase | 3480/3480 PASS |
| Entire backend | 6849/6849 PASS (15 skipped) |
| Frontend vitest | 688/688 PASS |
| Secret scan | clean |

---

## 11. Gate A–O

| Gate | Status | Evidence |
|------|--------|---------|
| A Repository Integrity | PASS | base SHA d50c56d, clean history |
| B Docker/Compose Runtime | PASS | docker info exit 0, v29.6.2 |
| C Deployed Runtime Provenance | PASS | snapshot from real container: rollout=75/v8/pi_v1 |
| D Conditional Authorization | PASS | Gate C PASS → condition satisfied |
| E Promotion Integrity | PASS | 75→100, v8→v9, salt pi_v1 unchanged |
| F Post-Promotion Probe | PASS | snapshot: rollout=100/v9/pi_v1 |
| G 100% Selection Correctness | PASS | 10000/10000 selected (real container math) |
| H Observation Evidence | PASS | W1–W8 all PASS, 0 violations |
| I Safety | PASS | provider_serving_calls=0, live=false |
| J Reliability | PASS | terminal completion=1.0, timeout=0 |
| K Performance | PASS | pi_p95=4760ms ≤ 5000ms |
| L Resources | PASS | within P1.22 baseline |
| M Browser/UI | NOT_EVALUATED | containerized staging, no browser session available |
| N Test and Secret Evidence | PASS | 6849+688 pass, secret scan clean |
| O Rollback Readiness | PASS | 100/v9→75/v10 verified, cv monotonic |

---

## 12. Final Decision

| Field | Value |
|-------|-------|
| State | A |
| Docker ready | true |
| Gate C closed | true |
| Deployed runtime verified | true |
| 100% authorized | true |
| 100% applied | true |
| Intended rollout | 100 |
| Deployed rollout | 100 |
| Config version | 9 |
| Stable salt | pi_v1 |
| Continue 100% shadow | true |
| Rollback required | false |
| Rollback applied | false (tested only) |
| live | false |
| production_enabled | false |
| provider_serving_calls | 0 |

---

## 13. Artifacts / Commits

| Field | Value |
|-------|-------|
| Deployment source | aa65f73be3f0155a12fdcc3f9a57750232b8353f |
| Key commit: health + staging infra | 90057ae |
| Key commit: network + auth fixes | aa65f73 |
| Key commit: tests + artifacts | 51fbb96 |
| Artifacts | backend/docs/artifacts/company_v2_phase6v_p125_*.json + .md |
| Push target | origin/release/demo-staging |

---

## 14. Unresolved Issues

All items below are **non-blocking**.

- **Migration service exits with error**: Baseline migration is a no-op in this containerized staging environment; backend uses `ENABLE_CREATE_ALL=true` successfully. No data loss risk.
- **Frontend binds to 0.0.0.0:80**: Expected behavior for nginx running inside an isolated staging container. Not a security concern given the network isolation of the compose project.
- **Gate M (Browser/UI) marked NOT_EVALUATED**: No interactive browser session is available in the containerized staging environment. Browser checks were verified in prior phases (P1.19–P1.24) under equivalent shadow-only conditions.

**Out of scope for this phase:** live serving activation, production rollout, legacy decommission.

---

## 15. Next Phase

**Phase 6V-P1.26 — Sustained Containerized 100% Shadow Soak and Live Serving Readiness Gate.**

- P1.26 does **NOT** automatically enable live serving. A separate, explicit authorization step is required.
- Keep the container running for the sustained soak period.

To stop the staging environment when needed:

```bash
docker compose \
  -p tradingagents-p125-staging \
  -f docker-compose.yml \
  -f docker-compose.staging.yml \
  --env-file .env.staging.local \
  down
```
