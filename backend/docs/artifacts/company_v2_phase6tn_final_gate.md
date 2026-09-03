# Phase 6T-N Final Gate

## Result

- `phase6tn_passed`: `false`
- `stage2_rollout_status`: `hold`
- `blocking_issues`: `STEADY_STATE_JOB_CREATE_P50_EXCEEDS_GATE`

## Observed performance

- steady-state create p50: `1367.75 ms`
- steady-state create p95: `2097.94 ms`
- minimum expected DB floor: `1863.75 ms`

## Conclusion

The create path is materially improved, but the current remote database floor still prevents the median steady-state job admission latency from satisfying the `300 ms` gate.
