# Phase 6T-J Final Gate

- phase6tj_passed: true
- phase6tj1_passed: true
- phase6tj2_passed: true
- stage2_status: ready
- multistock_fusion_gate_passed: true
- confirmed_value_conflict_total: 0
- false_conflict: 0
- recommendation_for_production_fusion_rollout: proceed_stage_2

## Scope
proceed_stage_2 means Stage 2 allowlist/manual rollout only; not Stage 3, not full-market, rollout_percent remains 0, auto_run remains false.

## Summary
{
  "symbols_total": 4,
  "reports_ready": 4,
  "reports_failed": 0,
  "fields_total": 40,
  "verified": 3,
  "normalized_match": 0,
  "definition_mismatch": 12,
  "period_basis_mismatch": 5,
  "unit_mismatch": 2,
  "value_conflict": 0,
  "false_conflict": 0,
  "cross_report_leakage": 0,
  "cross_symbol_leakage": 0,
  "missing_citation": 0,
  "incomplete_source_trace": 0,
  "unsupported_merge": 0,
  "timeouts": 0,
  "p50_latency_ms": 31978.15,
  "p95_latency_ms": 49843.46,
  "cache_hit_rate": 0.0,
  "circuit_state": "closed",
  "review_queue_size": 0,
  "health_status": "insufficient_data",
  "confirmed_value_conflict_total": 0,
  "timeout_count": 0,
  "timeout_rate": 0.0,
  "stale_generation_usage": 0,
  "invalid_page_citation": 0
}

## Key Regressions
{
  "300750_net_profit": {
    "classification": "verified",
    "structured_value": 76786309000,
    "structured_unit": "CNY",
    "raw_official_value": 76786309.0,
    "raw_unit": "千元",
    "unit_scale": 1000.0,
    "unit_source": "table_level",
    "normalized_official_value": 76786309000.0,
    "normalized_unit": "CNY",
    "evidence_page": 200,
    "table_scope_id": "p200#u738",
    "table_title": "合并利润表",
    "value_conflict": false
  },
  "600519_revenue": {
    "classification": "definition_mismatch",
    "structured_definition": "main_business_revenue",
    "official_definition": "营业收入",
    "raw_official_value": 168838102514.79,
    "raw_unit": "元",
    "unit_scale": 1.0,
    "unit_source": "table_level",
    "value_conflict": false
  }
}

## Performance
{
  "cold_sample_count": 4,
  "per_symbol_cold_latency_ms": {
    "600519": 42713.38,
    "300750": 29367.08,
    "000725": 30749.7,
    "000001": 33206.6
  },
  "p50_latency_ms": 31978.15,
  "p95_latency_ms": 49843.46,
  "timeout_count": 0,
  "warm_latency_ms": null,
  "singleflight_status": "no_sample"
}
