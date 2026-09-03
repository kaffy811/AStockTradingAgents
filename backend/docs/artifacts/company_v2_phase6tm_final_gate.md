# Phase 6T-M Final Gate

```json
{
  "phase6tm_passed": false,
  "phase6tl_passed": false,
  "phase6tk_passed": false,
  "stage2_rollout_status": "hold",
  "stage3_status": "not_authorized",
  "auto_run": false,
  "rollout_percent": 0,
  "blocking_issues": [
    {
      "code": "JOB_CREATE_P50_EXCEEDS_GATE",
      "detail": "Real steady-state job create p50 measured 400.88ms, above the 300ms gate."
    }
  ],
  "verified": {
    "database_connectivity_gate_passed": true,
    "warm_snapshot_gate_passed": true,
    "warm_latency_gate_passed": true,
    "warm_speedup_gate_passed": true,
    "singleflight_gate_passed": true,
    "cancel_gate_passed": true,
    "backend_full_tests_passed": true,
    "frontend_tests_passed": true,
    "frontend_build_passed": true
  },
  "recommendation_for_next_step": "hold"
}
```
