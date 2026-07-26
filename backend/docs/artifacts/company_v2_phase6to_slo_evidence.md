# Phase 6T-O SLO Evidence

## Observed floor

- `SELECT 1` p50: `525.73 ms`
- primary-key select p50: `526.59 ms`
- insert + commit p50: `811.43 ms`
- steady-state create p50: `1367.75 ms`
- steady-state create p95: `2097.94 ms`

## Interpretation

The current local path is consistent with a cross-continent deployment from an estimated US workstation to an `ap-northeast-2` database region. The current environment does not support a truthful same-region live acceptance result.

## Candidate decisions

1. Keep the `300 ms` gate and require same-region deployment.
2. Change the production SLO through a separate architecture approval.
3. Hold the rollout.
