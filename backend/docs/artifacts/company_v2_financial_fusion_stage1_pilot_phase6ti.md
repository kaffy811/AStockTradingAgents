# Phase 6T-I Stage 1 Controlled Pilot

- stage1_status: ready
- stage2_status: partially_ready
- recommendation_for_production_fusion_rollout: continue_stage_1

## Summary
{
  "requests_total": 2,
  "cold_runs": 1,
  "cache_hits": 1,
  "cache_misses": 0,
  "singleflight_reused": 2,
  "success": 4,
  "partial": 0,
  "failed": 0,
  "timeouts": 0,
  "latency_sample_count": 12,
  "p50_latency_ms": 24.843374732881784,
  "p95_latency_ms": 43.22608280926943,
  "cold_latency_ms": 43.25,
  "warm_latency_ms": 0.39,
  "cache_hit_rate": 1.0,
  "circuit_state": "closed",
  "false_conflict": 0,
  "cross_report_leakage": 0,
  "missing_citation": 0,
  "incomplete_source_trace": 0
}

## Stage 1 Runs
[
  {
    "name": "cold_run",
    "refresh": true,
    "fields": [
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
    "ok": true,
    "status": null,
    "reason": "ALLOWLIST",
    "error_code": null,
    "cache_hit": false,
    "singleflight_status": "completed",
    "singleflight_request_id": "cold_run-stage1-cold",
    "elapsed_ms": 43.25,
    "timings": {
      "eligibility_latency_ms": 0.01,
      "cache_lookup_latency_ms": 0.0,
      "resolver_latency_ms": 42.09,
      "retrieval_latency_ms": 42.09,
      "alignment_latency_ms": 0.32,
      "persistence_latency_ms": 0.28,
      "computed_latency_ms": 42.7,
      "total_latency_ms": 43.25,
      "waiting_on_singleflight_ms": 0.0,
      "singleflight_reuse_latency_ms": 0.0
    },
    "summary": {
      "fields_total": 10,
      "verified": 1,
      "normalized_match": 0,
      "likely_match": 0,
      "definition_mismatch": 3,
      "period_basis_mismatch": 1,
      "unit_mismatch": 0,
      "value_conflict": 0,
      "structured_field_missing": 4,
      "official_field_not_found": 0,
      "insufficient_evidence": 1,
      "not_applicable": 0,
      "failed": 0
    },
    "timeout": false,
    "final_status": "passed"
  },
  {
    "name": "warm_cache_run",
    "refresh": false,
    "fields": [
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
    "ok": true,
    "status": null,
    "reason": "ALLOWLIST",
    "error_code": null,
    "cache_hit": true,
    "singleflight_status": null,
    "singleflight_request_id": null,
    "elapsed_ms": 0.39,
    "timings": {
      "eligibility_latency_ms": 0.01,
      "cache_lookup_latency_ms": 0.0,
      "cache_hit_latency_ms": 0.0,
      "computed_latency_ms": 0.0,
      "waiting_on_singleflight_ms": 0.0,
      "singleflight_reuse_latency_ms": 0.0,
      "retrieval_latency_ms": 0.0,
      "resolver_latency_ms": 0.0,
      "alignment_latency_ms": 0.0,
      "persistence_latency_ms": 0.0,
      "total_latency_ms": 0.39
    },
    "summary": {
      "fields_total": 10,
      "verified": 1,
      "normalized_match": 0,
      "likely_match": 0,
      "definition_mismatch": 3,
      "period_basis_mismatch": 1,
      "unit_mismatch": 0,
      "value_conflict": 0,
      "structured_field_missing": 4,
      "official_field_not_found": 0,
      "insufficient_evidence": 1,
      "not_applicable": 0,
      "failed": 0
    },
    "timeout": false,
    "final_status": "passed"
  },
  {
    "name": "subset_run",
    "refresh": false,
    "fields": [
      "revenue",
      "net_profit",
      "net_profit_parent"
    ],
    "ok": true,
    "status": null,
    "reason": "ALLOWLIST",
    "error_code": null,
    "cache_hit": false,
    "singleflight_status": "completed",
    "singleflight_request_id": "subset_run-stage1-subset",
    "elapsed_ms": 10.55,
    "timings": {
      "eligibility_latency_ms": 0.0,
      "cache_lookup_latency_ms": 0.0,
      "resolver_latency_ms": 10.05,
      "retrieval_latency_ms": 10.05,
      "alignment_latency_ms": 0.09,
      "persistence_latency_ms": 0.1,
      "computed_latency_ms": 10.24,
      "total_latency_ms": 10.55,
      "waiting_on_singleflight_ms": 0.0,
      "singleflight_reuse_latency_ms": 0.0
    },
    "summary": {
      "fields_total": 3,
      "verified": 1,
      "normalized_match": 0,
      "likely_match": 0,
      "definition_mismatch": 2,
      "period_basis_mismatch": 0,
      "unit_mismatch": 0,
      "value_conflict": 0,
      "structured_field_missing": 0,
      "official_field_not_found": 0,
      "insufficient_evidence": 0,
      "not_applicable": 0,
      "failed": 0
    },
    "timeout": false,
    "final_status": "passed"
  },
  {
    "name": "circuit_smoke",
    "refresh": true,
    "fields": [
      "revenue",
      "net_profit",
      "net_profit_parent"
    ],
    "ok": true,
    "status": null,
    "reason": "ALLOWLIST",
    "error_code": null,
    "cache_hit": false,
    "singleflight_status": "completed",
    "singleflight_request_id": "circuit_smoke-stage1-circuit",
    "elapsed_ms": 10.57,
    "timings": {
      "eligibility_latency_ms": 0.0,
      "cache_lookup_latency_ms": 0.0,
      "resolver_latency_ms": 10.04,
      "retrieval_latency_ms": 10.04,
      "alignment_latency_ms": 0.08,
      "persistence_latency_ms": 0.1,
      "computed_latency_ms": 10.22,
      "total_latency_ms": 10.57,
      "waiting_on_singleflight_ms": 0.0,
      "singleflight_reuse_latency_ms": 0.0
    },
    "summary": {
      "fields_total": 3,
      "verified": 1,
      "normalized_match": 0,
      "likely_match": 0,
      "definition_mismatch": 2,
      "period_basis_mismatch": 0,
      "unit_mismatch": 0,
      "value_conflict": 0,
      "structured_field_missing": 0,
      "official_field_not_found": 0,
      "insufficient_evidence": 0,
      "not_applicable": 0,
      "failed": 0
    },
    "timeout": false,
    "final_status": "passed"
  }
]

## Stage 2 Readiness
[
  {
    "symbol": "601686",
    "report_year": 2024,
    "report_id": 1,
    "discovery_status": "report_discovered",
    "pdf_status": "pdf_downloaded",
    "parse_status": "parsed",
    "rag_status": "indexed",
    "structured_status": "ready",
    "fusion_ready": true,
    "missing_prerequisites": [],
    "next_manual_action": "run_fusion",
    "status": "ready",
    "reason": null,
    "reports": []
  },
  {
    "symbol": "600519",
    "report_year": 2024,
    "report_id": null,
    "discovery_status": "report_discovered",
    "pdf_status": "pdf_not_downloaded",
    "parse_status": "parse_pending",
    "rag_status": "rag_not_indexed",
    "structured_status": "structured_data_missing",
    "fusion_ready": false,
    "missing_prerequisites": [
      "pdf_download"
    ],
    "next_manual_action": "download_report",
    "status": "pdf_not_downloaded",
    "reason": "report not ready",
    "reports": []
  },
  {
    "symbol": "300750",
    "report_year": 2024,
    "report_id": null,
    "discovery_status": "report_discovered",
    "pdf_status": "pdf_not_downloaded",
    "parse_status": "parse_pending",
    "rag_status": "rag_not_indexed",
    "structured_status": "structured_data_missing",
    "fusion_ready": false,
    "missing_prerequisites": [
      "pdf_download"
    ],
    "next_manual_action": "download_report",
    "status": "pdf_not_downloaded",
    "reason": "report not ready",
    "reports": []
  },
  {
    "symbol": "000725",
    "report_year": 2024,
    "report_id": null,
    "discovery_status": "report_discovered",
    "pdf_status": "pdf_not_downloaded",
    "parse_status": "parse_pending",
    "rag_status": "rag_not_indexed",
    "structured_status": "structured_data_missing",
    "fusion_ready": false,
    "missing_prerequisites": [
      "pdf_download"
    ],
    "next_manual_action": "download_report",
    "status": "pdf_not_downloaded",
    "reason": "report not ready",
    "reports": []
  },
  {
    "symbol": "000001",
    "report_year": 2024,
    "report_id": null,
    "discovery_status": "report_discovered",
    "pdf_status": "pdf_not_downloaded",
    "parse_status": "parse_pending",
    "rag_status": "rag_not_indexed",
    "structured_status": "structured_data_missing",
    "fusion_ready": false,
    "missing_prerequisites": [
      "pdf_download"
    ],
    "next_manual_action": "download_report",
    "status": "pdf_not_downloaded",
    "reason": "report not ready",
    "reports": []
  }
]