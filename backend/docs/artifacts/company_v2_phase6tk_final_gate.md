# Phase 6T-K Final Gate

```json
{
  "phase": "phase6tk_final_gate",
  "generated_at": "2026-07-12T12:47:07.053461+00:00",
  "phase6tj_prerequisite_passed": true,
  "phase6tk_passed": false,
  "stage2_rollout_status": "hold",
  "stage3_status": "not_authorized",
  "auto_run": false,
  "rollout_percent": 0,
  "stage2_allowlist": [
    "601686",
    "600519",
    "300750",
    "000725",
    "000001"
  ],
  "stage2_allowlist_gate_passed": true,
  "manual_trigger_gate_passed": true,
  "no_auto_run_gate_passed": true,
  "async_job_gate_passed": true,
  "job_persistence_gate_passed": true,
  "progress_gate_passed": true,
  "profile_gate_passed": true,
  "warm_cache_gate_passed": false,
  "singleflight_gate_passed": true,
  "circuit_gate_passed": true,
  "review_queue_gate_passed": true,
  "operational_soak_gate_passed": false,
  "frontend_gate_passed": true,
  "safety_gate_passed": true,
  "tests_gate_passed": true,
  "blocking_issues": [
    {
      "code": "WARM_RESULT_P95_EXCEEDS_GATE",
      "actual_ms": 10569.73,
      "threshold_ms": 1500
    },
    {
      "code": "JOB_CREATE_P95_EXCEEDS_GATE",
      "actual_ms": 9698.44,
      "threshold_ms": 1000
    },
    {
      "code": "ALLOWLIST_SYMBOL_NOT_JOB_READY",
      "symbol": "601686",
      "reason": "RAG_NOT_INDEXED"
    },
    {
      "code": "OPERATIONAL_SOAK_CANCEL_INCOMPLETE",
      "actual": 4,
      "expected": 5
    }
  ],
  "recommendation_for_next_step": "hold",
  "metrics": {
    "profile_cold_p50_ms": 12140.42,
    "profile_cold_p95_ms": 23081.83,
    "soak_cold_p50_ms": 4384.92,
    "soak_cold_p95_ms": 7794.84,
    "warm_p50_ms": 4365.47,
    "warm_p95_ms": 10569.73,
    "warm_speedup_ratio_p50": 1.0,
    "job_create_p50_ms": 7500.35,
    "job_create_p95_ms": 9698.44,
    "requests_total": 65,
    "cache_hits": 25,
    "singleflight_reused": 10,
    "timeout_count": 0
  },
  "test_results": {
    "backend_targeted": "23 passed",
    "backend_full": "3044 passed",
    "frontend_tests": "55 files / 638 tests passed",
    "frontend_build": "passed"
  }
}
```

## Decision

Phase 6T-K is **not passed** in the current environment. Stage 2 remains manual allowlist only, but rollout should stay on **hold** until warm/job-create latency and 601686 readiness are fixed.
