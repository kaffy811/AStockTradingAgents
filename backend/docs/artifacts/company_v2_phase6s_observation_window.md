# CompanyV2 Phase 6S Observation Window

Recommended observation window: 24-48 hours after production default v2 cutover.

## Metrics

1. `debug_full_error_rate`
2. `debug_full_latency_p95`
3. `providers_timeout`
4. `providers_data_success`
5. `modules_renderable`
6. `data_quality_score`
7. `strong_failed_count`
8. `semantic_warning_count`
9. `fallback_to_legacy_count`
10. Frontend console/page errors
11. Forbidden DATA_MODE message count
12. User-reported scroll issues

## Stable

- No strong failures.
- No critical failures.
- `modules_renderable >= 8`.
- No page crash.
- No rollback trigger.

## Watch

- Semantic warnings increase.
- Coverage decreases.
- Latency p95 is elevated.
- Data remains visible and usable.

## Rollback

- `modules_renderable < 8`.
- `providers_data_success = 0`.
- p95 latency stays above 30s.
- `strong_failed_count > 0`.
- Page cannot open or cannot scroll.
- Forbidden DATA_MODE message reappears.
