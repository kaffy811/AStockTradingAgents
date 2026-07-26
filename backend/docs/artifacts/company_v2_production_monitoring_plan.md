# CompanyV2 Production Monitoring Plan

CompanyV2 production cutover keeps the legacy Company Tab available. Monitoring is based on structured JSON logs, debug/full summaries, validation summaries, smoke tests, and daily health snapshots.

## API Health

Metrics:
- `debug_full_request_count`
- `debug_full_success_count`
- `debug_full_error_count`
- `debug_full_latency_ms_p50`
- `debug_full_latency_ms_p95`
- `debug_full_latency_ms_p99`
- `debug_full_partial_count`
- `debug_full_timeout_count`
- `request_id_missing_count`

Thresholds:
- p95 `< 15s`: healthy
- p95 `15s-30s`: warning
- p95 `> 30s`: alert
- error rate `> 5%`: alert
- partial rate `> 20%`: warning

## Provider Health

Metrics:
- `providers_attempted`
- `providers_success`
- `providers_data_success`
- `provider_data_failure_count`
- `providers_timeout`
- `provider_network_error_count`
- `baostock_aggregate_calls`
- `akshare_data_success_rate`
- `cache_hit_count`
- `cache_stale_count`
- `cache_unavailable_count`

Thresholds:
- `providers_timeout > 0` sustained: warning
- `providers_data_success = 0`: alert
- `baostock_aggregate_calls != 1`: warning
- high `cache_unavailable_count`: warning

## Render Health

Metrics:
- `modules_renderable`
- `modules_unavailable`
- `modules_renderable_avg`
- `render_rule_error_count`
- `mapping_error_count`
- `trace_missing_count`
- `coverage_avg`
- `low_coverage_module_count`

Thresholds:
- `modules_renderable < 8`: alert
- `mapping_error_count > 0`: alert
- `trace_missing_count > 0`: warning
- `coverage_avg < 60`: warning
- `coverage_avg < 40`: alert

## Data Quality Health

Metrics:
- `validation_status`
- `data_quality_score`
- `strong_failed_count`
- `semantic_warning_count`
- `weak_warning_count`
- `critical_validation_failures`
- `dupont_semantic_warning_count`
- `net_margin_semantic_warning_count`
- `provider_conflict_count`
- `market_cap_formula_fail_count`

Thresholds:
- `critical_validation_failures > 0`: alert
- `strong_failed_count > 0`: alert
- `data_quality_score < 70`: warning
- `data_quality_score < 50`: alert
- `semantic_warning_count`: observation panel only
- sudden increase in `semantic_warning_count`: warning

## Frontend Runtime Health

Metrics:
- `company_v2_render_success`
- `company_v2_fallback_to_legacy`
- `company_v2_page_error`
- `company_v2_console_error`
- `company_v2_bottom_sentinel_visible`
- `company_v2_raw_drawer_error`
- `forbidden_legacy_datamode_message_count`

Thresholds:
- `fallback_to_legacy > 0`: warning
- `page_error > 0`: alert
- forbidden legacy DATA_MODE message `> 0`: alert
- bottom sentinel invisible: warning

## Structured Log Event

Required event:

```json
{
  "event_name": "company_v2_debug_full_completed",
  "request_id": "request-id",
  "market": "CN",
  "symbol": "600519",
  "ts_code": "600519.SH",
  "schema_version": "2.0",
  "latency_ms": 1234,
  "partial": false,
  "providers_data_success": 8,
  "providers_timeout": 0,
  "modules_renderable": 9,
  "coverage_avg": 66.21,
  "validation_status": "warning",
  "data_quality_score": 89,
  "strong_failed_count": 0,
  "semantic_warning_count": 2,
  "fallback_to_legacy": false
}
```

The event must not include `raw_full`, `secret`, `token`, or `local_path`. Semantic warnings are monitorable quality hints, not user-facing recommendations.
