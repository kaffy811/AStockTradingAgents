# Phase 6T-S Shadow Soak

```json
{
  "phase": "phase6ts_shadow_soak",
  "status": "passed",
  "run_id": "f75ddf357d3e48408a4c8783f93b52a6",
  "stage3_status": "not_authorized",
  "stage3_authorized": false,
  "worker_mode": "shadow",
  "worker_enabled": true,
  "auto_run": false,
  "rollout_percent": 0,
  "symbols": [
    "601686",
    "600519"
  ],
  "created_jobs": [
    {
      "job_id": "a05cb810-e0a2-4ac9-b34c-8d807ea6c020",
      "symbol": "601686",
      "report_id": 1,
      "report_year": 2024,
      "requested_fields": [
        "revenue",
        "net_profit",
        "net_profit_parent",
        "operating_cashflow",
        "total_assets",
        "equity_parent",
        "eps_basic",
        "roe_weighted",
        "total_share",
        "float_share"
      ],
      "requester_scope": "phase6ts_shadow_soak",
      "created_at": "2026-07-13T15:13:20.437501",
      "started_at": null,
      "completed_at": null,
      "status": "queued",
      "progress": 0.0,
      "current_stage": "queued",
      "cache_hit": false,
      "result_id": null,
      "error_code": null,
      "retryable": false,
      "repository_backend": "database",
      "extractor_version": "official-extractor-unit-context-v2",
      "active_generation": null,
      "poll_after_ms": 1000,
      "retry_after_ms": 1000,
      "terminal": false,
      "ok": true,
      "estimated_wait_seconds": 30
    },
    {
      "job_id": "5c3d0e09-3be6-4768-8cf4-b13e3541261f",
      "symbol": "600519",
      "report_id": 2,
      "report_year": 2025,
      "requested_fields": [
        "revenue",
        "net_profit",
        "net_profit_parent",
        "operating_cashflow",
        "total_assets",
        "equity_parent",
        "eps_basic",
        "roe_weighted",
        "total_share",
        "float_share"
      ],
      "requester_scope": "phase6ts_shadow_soak",
      "created_at": "2026-07-13T15:13:23.565404",
      "started_at": null,
      "completed_at": null,
      "status": "queued",
      "progress": 0.0,
      "current_stage": "queued",
      "cache_hit": false,
      "result_id": null,
      "error_code": null,
      "retryable": false,
      "repository_backend": "database",
      "extractor_version": "official-extractor-unit-context-v2",
      "active_generation": null,
      "poll_after_ms": 1000,
      "retry_after_ms": 1000,
      "terminal": false,
      "ok": true,
      "estimated_wait_seconds": 30
    }
  ],
  "metrics": {
    "duration_seconds": 8,
    "worker_count": 2,
    "worker_ids": [
      "phase6ts-worker-1",
      "phase6ts-worker-2"
    ],
    "jobs_created": 2,
    "jobs_observed": 0,
    "unique_jobs_claimed": 2,
    "duplicate_claim_count": 0,
    "simultaneous_claim_conflicts": 0,
    "observation_rows_written": 0,
    "active_leases_peak": 1,
    "active_leases_end": 0,
    "stale_leases_end": 0,
    "heartbeat_failures": 0,
    "lease_renewal_failures": 0,
    "db_disconnect_count": 1,
    "db_reconnect_count": 1,
    "worker_restart_count": 4,
    "loop_p50_ms": 6068.181,
    "loop_p95_ms": 7983.683,
    "claim_p50_ms": 2895.599,
    "claim_p95_ms": 4086.355,
    "real_execution_count": 0,
    "provider_call_count": 0,
    "rag_query_count": 0,
    "extractor_call_count": 0,
    "fusion_result_write_count": 0,
    "unknown_jobs_modified": 0,
    "jobs_cancelled": 2,
    "preexisting_active_jobs_found": 0,
    "preexisting_active_jobs_cancelled": 0,
    "worker_restart_events": [
      {
        "at_seconds": 2.01,
        "worker_id": "phase6ts-worker-1"
      }
    ],
    "db_reconnect_events": [
      {
        "at_seconds": 4.18,
        "disposed": true
      }
    ],
    "errors": []
  },
  "real_execution_count": 0,
  "provider_call_count": 0,
  "rag_query_count": 0,
  "extractor_call_count": 0,
  "fusion_result_write_count": 0,
  "blocking_issues": [],
  "errors": [],
  "shadow_soak_completed": true
}
```
