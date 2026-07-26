# Financial Agent Live Shadow Summary

- Mode: `live_shadow_required_not_executed`
- Execution status: `blocked`
- Requested sample count: `56`
- Executed sample count: `0`
- Intent sample counts: `{"financial_comparison": 11, "financial_report": 12, "financial_snapshot": 11, "official_report_pdf": 11, "quote_query": 11}`
- Intent match: `None`
- Entity match: `None`
- Numeric fact match: `None`
- Unsupported numeric facts: `None`
- Cold latency p50/p95: `None` / `None`
- Warm latency p50/p95: `None` / `None`
- Live external suite: `{"status": "failed", "passed": 0, "skipped": 0, "failed": 15, "reason": "DNS_RESOLUTION_FAILED_FOR_SUPABASE_POOLER"}`
- Soak suite: `{"status": "no_tests_collected", "passed": 0, "skipped": 0, "failed": 0, "reason": "NO_TESTS_MATCHED_SOAK_MARKER"}`
- Layered enabled: `False`
- Authorized intents: `[]`

## Intent Gates

- `official_report_pdf`: passed=`False`, executed_samples=`0`, blockers=`live_shadow_samples_not_executed, browser_acceptance_not_recorded, live_external_suite_not_run`
- `quote_query`: passed=`False`, executed_samples=`0`, blockers=`live_shadow_samples_not_executed, browser_acceptance_not_recorded, live_external_suite_not_run`
- `financial_snapshot`: passed=`False`, executed_samples=`0`, blockers=`live_shadow_samples_not_executed, browser_acceptance_not_recorded, live_external_suite_not_run`
- `financial_report`: passed=`False`, executed_samples=`0`, blockers=`live_shadow_samples_not_executed, browser_acceptance_not_recorded, live_external_suite_not_run`
- `financial_comparison`: passed=`False`, executed_samples=`0`, blockers=`live_shadow_samples_not_executed, browser_acceptance_not_recorded, live_external_suite_not_run`

## Runtime Gate

`do_not_enable_layered_v1`

## Blockers

- live_shadow_samples_not_executed
- browser_acceptance_not_recorded
- live_security_master_sampling_not_run
- live_external_suite_not_run

This is not a hermetic latency artifact. If live execution is blocked, no sample is counted as accepted.
