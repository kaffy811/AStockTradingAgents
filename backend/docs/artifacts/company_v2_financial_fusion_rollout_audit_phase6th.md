# Company V2 Financial Fusion Rollout Audit Phase 6T-H

- symbols_total: 5
- reports_total: 1
- fields_total: 20
- cache_hit_rate: 1.00
- p50_latency_ms: 0.0
- p95_latency_ms: 0.0
- circuit_state: closed

## stage_1
- allowlist: 601686
- health: healthy
- review_queue_size: 0

| symbol | report_id | eligibility | cache_hit | singleflight | final_status |
| --- | --- | --- | --- | --- | --- |
| 601686 | 1 | ALLOWLIST / True | False | completed | passed |

## stage_2
- allowlist: 601686,600519,300750,000725,000001
- health: healthy
- review_queue_size: 0

| symbol | report_id | eligibility | cache_hit | singleflight | final_status |
| --- | --- | --- | --- | --- | --- |
| 601686 | 1 | ALLOWLIST / True | True | None | passed |
| 600519 | 0 | REPORT_NOT_READY / False | False | None | ineligible |
| 300750 | 0 | REPORT_NOT_READY / False | False | None | ineligible |
| 000725 | 0 | REPORT_NOT_READY / False | False | None | ineligible |
| 000001 | 0 | REPORT_NOT_READY / False | False | None | ineligible |

