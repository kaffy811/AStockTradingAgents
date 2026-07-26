# CompanyV2 Production Monitoring Plan

This plan defines metrics and log aggregation fields for CompanyV2 production rollout. These metrics do not all need immediate Prometheus integration, but their source and aggregation semantics are fixed.

## Traceability

- Every CompanyV2 debug response includes `request_id`.
- Frontend error/fallback logs must include `request_id` when a debug response is available.
- Backend provider/debug logs must include `request_id`, `market`, `symbol`, `module_key`, `provider`, `endpoint`, `status`, `error_code`, and `latency_ms`.
- Do not log secrets, auth tokens, API keys, passwords, or internal `local_path` values.

## Frontend Metrics

| Metric | Type | Source | Aggregation |
| --- | --- | --- | --- |
| `company_v2_render_success_rate` | ratio | CompanyV2 page load completes and renders at least one module | successes / CompanyV2 page attempts |
| `company_v2_fallback_to_legacy_count` | counter | `CompanyV2View` embedded load error triggers legacy fallback | count by route, market, symbol |
| `company_v2_page_load_error_count` | counter | CompanyV2 fetch/render error | count by error_code/status |
| `company_v2_console_error_count` | counter | browser console errors during CompanyV2 session | count by route/browser build |
| `company_v2_scroll_bottom_visible_rate` | ratio | bottom sentinel visible in browser/e2e/manual checks | visible / checked sessions |
| `company_v2_raw_json_drawer_error_count` | counter | RawJsonDrawer open/copy failure | count by browser/error |
| `company_v2_forbidden_legacy_data_mode_message_count` | counter | legacy DATA_MODE text detected in v2 UI | must remain zero |

## Backend Metrics

| Metric | Type | Source | Aggregation |
| --- | --- | --- | --- |
| `company_v2_debug_full_latency_ms_p50` / `p95` | histogram | `/api/v2/company/{market}/{symbol}/debug/full` request timing | by market, provider set, cache status |
| `company_v2_providers_timeout_count` | counter | `summary.providers_timeout` | by provider/module/error_code |
| `company_v2_modules_renderable_distribution` | histogram | `summary.modules_renderable` | by market/symbol cohort |
| `company_v2_modules_unavailable_distribution` | histogram | `summary.modules_unavailable` | by market/symbol cohort |
| `company_v2_baostock_aggregate_calls` | counter | `summary.baostock_aggregate_calls` | expected 1 for full financial path |
| `company_v2_cache_hit_count` | counter | `summary.cache_hit_count` | by cache backend |
| `company_v2_cache_stale_count` | counter | `summary.cache_stale_count` | stale fallback frequency |
| `company_v2_cache_unavailable_count` | counter | `summary.cache_unavailable_count` | Redis/memory fail-open events |
| `company_v2_report_pdf_not_found_count` | counter | `summary.report_pdf_not_found_count` | report discovery/DB gap |
| `company_v2_report_not_ingested_count` | counter | `summary.report_not_ingested_count` | PDF exists but RAG chunks missing |
| `company_v2_mapping_error_count` | counter | `summary.mapping_error_count` | raw rows exist but normalized/render failed |
| `company_v2_render_rule_error_count` | counter | `summary.render_rule_error_count` | normalized data exists but render=false |
| `company_v2_fallback_to_legacy_count` | counter | frontend fallback event, optionally mirrored to backend telemetry | count by route/symbol |

## Alert Suggestions

- `providers_timeout_count` sustained increase over baseline.
- `modules_renderable` median below 10.
- `debug/full` p95 above rollout threshold.
- Any `forbidden_legacy_data_mode_message_count > 0`.
- Any auth/401 storm correlated with CompanyV2 page load.
- `mapping_error_count > 0` for representative symbols.

## Debug Payload Security

- `include_raw=false` is the production default.
- `include_raw=true` remains dev/admin only.
- Raw previews are sanitized and truncated.
- Aggregation must use `error_code` and `diagnosis.primary_issue`, not free-form text.
