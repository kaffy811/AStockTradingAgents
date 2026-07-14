# Phase 6T-S Two-Hour Shadow Soak Gate

Gate status: **passed**.

- Official shadow soak run completed for **7200 seconds**.
- `run_id`: `9548e1efb8ec4f8cb6e40d5bf62b1c1a`
- Worker count: **2**
- Test symbols: `601686`, `600519`, `300750`, `000725`, `000001`
- Jobs created/cancelled: **5 / 5**
- Jobs observed / observation rows written: **30 / 30**
- Worker restart succeeded: **1** event at **1800.63s**
- DB disconnect/reconnect succeeded: **1 / 1** event at **3601.36s**
- Duplicate claim count: **0**
- Simultaneous claim conflicts: **0**
- Unknown jobs modified: **0**
- Active/stale leases at end: **0 / 0**
- Heartbeat / lease renewal failures: **0 / 0**
- Real Fusion execution count: **0**
- Provider / RAG / extractor / Fusion result writes: **0 / 0 / 0 / 0**
- Stage 3 remains **not authorized**.
- `auto_run=false`, `rollout_percent=0`; Canary has **not** started.

```json
{
  "phase6ts_passed": true,
  "stage3_status": "not_authorized",
  "stage3_authorized": false,
  "shadow_soak_completed": true,
  "run_id": "9548e1efb8ec4f8cb6e40d5bf62b1c1a",
  "status": "passed",
  "worker_mode": "shadow",
  "duration_seconds": 7200,
  "requested_duration_seconds": 7200,
  "actual_duration_seconds": 7200,
  "worker_count": 2,
  "jobs_created": 5,
  "jobs_cancelled": 5,
  "duplicate_claim_count": 0,
  "simultaneous_claim_conflicts": 0,
  "unknown_jobs_modified": 0,
  "active_leases_end": 0,
  "stale_leases_end": 0,
  "worker_restart_count": 1,
  "db_disconnect_count": 1,
  "db_reconnect_count": 1,
  "real_execution_count": 0,
  "provider_call_count": 0,
  "rag_query_count": 0,
  "extractor_call_count": 0,
  "fusion_result_write_count": 0,
  "auto_run": false,
  "rollout_percent": 0,
  "blocking_issues": []
}
```
