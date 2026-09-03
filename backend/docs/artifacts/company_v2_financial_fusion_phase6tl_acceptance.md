# Phase 6T-L Acceptance

```json
{
  "phase": "phase6tl_acceptance",
  "real_execution": true,
  "mock": false,
  "manual_only": false,
  "symbols": [
    "601686",
    "600519",
    "300750",
    "000725",
    "000001"
  ],
  "job_create_trace": {
    "p50_ms": 400.88,
    "p95_ms": 405.57,
    "results": [
      {
        "ok": true,
        "job_id": "b1bac43d-c2bb-460f-9ddf-3e75fa2fb46c",
        "status": "queued",
        "cache_hit": false,
        "poll_after_ms": 1000,
        "elapsed_ms": 2740.98,
        "sql_query_count": 15,
        "report_id": 1,
        "report_year": 2024
      },
      {
        "ok": true,
        "job_id": "9ab1a6b6-561b-4ca6-9669-e57d1a60c514",
        "status": "queued",
        "cache_hit": false,
        "poll_after_ms": 1000,
        "elapsed_ms": 354.08,
        "sql_query_count": 1,
        "report_id": 2,
        "report_year": 2025
      },
      {
        "ok": true,
        "job_id": "0d4601c8-ccfd-4768-a843-95ae8c0b7713",
        "status": "queued",
        "cache_hit": false,
        "poll_after_ms": 1000,
        "elapsed_ms": 400.29,
        "sql_query_count": 1,
        "report_id": 3,
        "report_year": 2025
      },
      {
        "ok": true,
        "job_id": "20c58b3e-3ce2-496f-a3f6-027fcdf3ed7e",
        "status": "queued",
        "cache_hit": false,
        "poll_after_ms": 1000,
        "elapsed_ms": 403.81,
        "sql_query_count": 1,
        "report_id": 4,
        "report_year": 2025
      },
      {
        "ok": true,
        "job_id": "f891135a-ed16-450c-ade5-0f69b7f75187",
        "status": "queued",
        "cache_hit": false,
        "poll_after_ms": 1000,
        "elapsed_ms": 401.46,
        "sql_query_count": 1,
        "report_id": 5,
        "report_year": 2025
      }
    ],
    "steady_state": {
      "p50_ms": 400.88,
      "p95_ms": 405.57,
      "sample_count": 4
    },
    "connection_cold_create": {
      "elapsed_ms": 2740.98,
      "sql_query_count": 15,
      "report_id": 1,
      "report_year": 2024
    }
  },
  "cold_trace": {
    "p50_ms": 503.12,
    "p95_ms": 4178.15,
    "results": [
      {
        "symbol": "601686",
        "report_id": 1,
        "ok": true,
        "cache_hit": false,
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
        "profile": {
          "eligibility_ms": 0.03516674041748047,
          "readiness_ms": 0.0,
          "cache_lookup_ms": 0.000250060111284256,
          "structured_provider_ms": 0.0,
          "rag_document_load_ms": 0.0,
          "retrieval_ms": 67.08116643130779,
          "official_extractor_ms": 67.08116643130779,
          "unit_normalization_ms": 0.5663339979946613,
          "field_alignment_ms": 0.5663339979946613,
          "classification_ms": 0.5663339979946613,
          "citation_validation_ms": 0.0,
          "result_persistence_ms": 0.3827079199254513,
          "total_ms": 2691.01
        },
        "top3_bottlenecks": [
          {
            "stage": "retrieval_ms",
            "ms": 67.08116643130779
          },
          {
            "stage": "official_extractor_ms",
            "ms": 67.08116643130779
          },
          {
            "stage": "unit_normalization_ms",
            "ms": 0.5663339979946613
          }
        ]
      },
      {
        "symbol": "600519",
        "report_id": 2,
        "ok": true,
        "cache_hit": false,
        "summary": {
          "fields_total": 10,
          "verified": 0,
          "normalized_match": 0,
          "likely_match": 0,
          "definition_mismatch": 3,
          "period_basis_mismatch": 1,
          "unit_mismatch": 1,
          "value_conflict": 0,
          "structured_field_missing": 4,
          "official_field_not_found": 0,
          "insufficient_evidence": 1,
          "not_applicable": 0,
          "failed": 0
        },
        "profile": {
          "eligibility_ms": 0.11529214680194855,
          "readiness_ms": 0.0,
          "cache_lookup_ms": 0.00033387914299964905,
          "structured_provider_ms": 0.0,
          "rag_document_load_ms": 0.0,
          "retrieval_ms": 46.60112550482154,
          "official_extractor_ms": 46.60112550482154,
          "unit_normalization_ms": 0.7587936706840992,
          "field_alignment_ms": 0.7587936706840992,
          "classification_ms": 0.7587936706840992,
          "citation_validation_ms": 0.0,
          "result_persistence_ms": 0.4585827700793743,
          "total_ms": 449.24
        },
        "top3_bottlenecks": [
          {
            "stage": "retrieval_ms",
            "ms": 46.60112550482154
          },
          {
            "stage": "official_extractor_ms",
            "ms": 46.60112550482154
          },
          {
            "stage": "unit_normalization_ms",
            "ms": 0.7587936706840992
          }
        ]
      },
      {
        "symbol": "300750",
        "report_id": 3,
        "ok": true,
        "cache_hit": false,
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
        "profile": {
          "eligibility_ms": 0.01229066401720047,
          "readiness_ms": 0.0,
          "cache_lookup_ms": 8.288770914077759e-05,
          "structured_provider_ms": 0.0,
          "rag_document_load_ms": 0.0,
          "retrieval_ms": 46.55141895636916,
          "official_extractor_ms": 46.55141895636916,
          "unit_normalization_ms": 0.49279211089015007,
          "field_alignment_ms": 0.49279211089015007,
          "classification_ms": 0.49279211089015007,
          "citation_validation_ms": 0.0,
          "result_persistence_ms": 0.30504073947668076,
          "total_ms": 450.32
        },
        "top3_bottlenecks": [
          {
            "stage": "retrieval_ms",
            "ms": 46.55141895636916
          },
          {
            "stage": "official_extractor_ms",
            "ms": 46.55141895636916
          },
          {
            "stage": "unit_normalization_ms",
            "ms": 0.49279211089015007
          }
        ]
      },
      {
        "symbol": "000725",
        "report_id": 4,
        "ok": true,
        "cache_hit": false,
        "summary": {
          "fields_total": 10,
          "verified": 0,
          "normalized_match": 0,
          "likely_match": 0,
          "definition_mismatch": 3,
          "period_basis_mismatch": 2,
          "unit_mismatch": 1,
          "value_conflict": 0,
          "structured_field_missing": 4,
          "official_field_not_found": 0,
          "insufficient_evidence": 0,
          "not_applicable": 0,
          "failed": 0
        },
        "profile": {
          "eligibility_ms": 0.04241708666086197,
          "readiness_ms": 0.0,
          "cache_lookup_ms": 0.00012479722499847412,
          "structured_provider_ms": 0.0,
          "rag_document_load_ms": 0.0,
          "retrieval_ms": 93.88979058712721,
          "official_extractor_ms": 93.88979058712721,
          "unit_normalization_ms": 0.5856244824826717,
          "field_alignment_ms": 0.5856244824826717,
          "classification_ms": 0.5856244824826717,
          "citation_validation_ms": 0.0,
          "result_persistence_ms": 0.39175013080239296,
          "total_ms": 503.12
        },
        "top3_bottlenecks": [
          {
            "stage": "retrieval_ms",
            "ms": 93.88979058712721
          },
          {
            "stage": "official_extractor_ms",
            "ms": 93.88979058712721
          },
          {
            "stage": "unit_normalization_ms",
            "ms": 0.5856244824826717
          }
        ]
      },
      {
        "symbol": "000001",
        "report_id": 5,
        "ok": true,
        "cache_hit": false,
        "summary": {
          "fields_total": 10,
          "verified": 2,
          "normalized_match": 0,
          "likely_match": 0,
          "definition_mismatch": 3,
          "period_basis_mismatch": 1,
          "unit_mismatch": 0,
          "value_conflict": 0,
          "structured_field_missing": 3,
          "official_field_not_found": 0,
          "insufficient_evidence": 1,
          "not_applicable": 0,
          "failed": 0
        },
        "profile": {
          "eligibility_ms": 0.027624890208244324,
          "readiness_ms": 0.0,
          "cache_lookup_ms": 0.00020908191800117493,
          "structured_provider_ms": 0.0,
          "rag_document_load_ms": 0.0,
          "retrieval_ms": 161.3411670550704,
          "official_extractor_ms": 161.3411670550704,
          "unit_normalization_ms": 0.5388339050114155,
          "field_alignment_ms": 0.5388339050114155,
          "classification_ms": 0.5388339050114155,
          "citation_validation_ms": 0.0,
          "result_persistence_ms": 0.33516669645905495,
          "total_ms": 566.53
        },
        "top3_bottlenecks": [
          {
            "stage": "retrieval_ms",
            "ms": 161.3411670550704
          },
          {
            "stage": "official_extractor_ms",
            "ms": 161.3411670550704
          },
          {
            "stage": "unit_normalization_ms",
            "ms": 0.5388339050114155
          }
        ]
      }
    ]
  },
  "warm_trace": {
    "p50_ms": 0.52,
    "p95_ms": 1.04,
    "results": [
      {
        "symbol": "601686",
        "report_id": 1,
        "ok": true,
        "cache_hit": true,
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
        "profile": {
          "eligibility_ms": 0.0,
          "readiness_ms": 0.0,
          "cache_lookup_ms": 0.27254223823547363,
          "structured_provider_ms": 0.0,
          "rag_document_load_ms": 0.0,
          "retrieval_ms": 0.0,
          "official_extractor_ms": 0.0,
          "unit_normalization_ms": 0.0,
          "field_alignment_ms": 0.0,
          "classification_ms": 0.0,
          "citation_validation_ms": 0.0,
          "result_persistence_ms": 0.0,
          "total_ms": 0.56
        },
        "top3_bottlenecks": [
          {
            "stage": "cache_lookup_ms",
            "ms": 0.27254223823547363
          },
          {
            "stage": "eligibility_ms",
            "ms": 0.0
          },
          {
            "stage": "readiness_ms",
            "ms": 0.0
          }
        ]
      },
      {
        "symbol": "600519",
        "report_id": 2,
        "ok": true,
        "cache_hit": true,
        "summary": {
          "fields_total": 10,
          "verified": 0,
          "normalized_match": 0,
          "likely_match": 0,
          "definition_mismatch": 3,
          "period_basis_mismatch": 1,
          "unit_mismatch": 1,
          "value_conflict": 0,
          "structured_field_missing": 4,
          "official_field_not_found": 0,
          "insufficient_evidence": 1,
          "not_applicable": 0,
          "failed": 0
        },
        "profile": {
          "eligibility_ms": 0.0,
          "readiness_ms": 0.0,
          "cache_lookup_ms": 0.15624985098838806,
          "structured_provider_ms": 0.0,
          "rag_document_load_ms": 0.0,
          "retrieval_ms": 0.0,
          "official_extractor_ms": 0.0,
          "unit_normalization_ms": 0.0,
          "field_alignment_ms": 0.0,
          "classification_ms": 0.0,
          "citation_validation_ms": 0.0,
          "result_persistence_ms": 0.0,
          "total_ms": 0.41
        },
        "top3_bottlenecks": [
          {
            "stage": "cache_lookup_ms",
            "ms": 0.15624985098838806
          },
          {
            "stage": "eligibility_ms",
            "ms": 0.0
          },
          {
            "stage": "readiness_ms",
            "ms": 0.0
          }
        ]
      },
      {
        "symbol": "300750",
        "report_id": 3,
        "ok": true,
        "cache_hit": true,
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
        "profile": {
          "eligibility_ms": 0.0,
          "readiness_ms": 0.0,
          "cache_lookup_ms": 0.18454110249876976,
          "structured_provider_ms": 0.0,
          "rag_document_load_ms": 0.0,
          "retrieval_ms": 0.0,
          "official_extractor_ms": 0.0,
          "unit_normalization_ms": 0.0,
          "field_alignment_ms": 0.0,
          "classification_ms": 0.0,
          "citation_validation_ms": 0.0,
          "result_persistence_ms": 0.0,
          "total_ms": 0.49
        },
        "top3_bottlenecks": [
          {
            "stage": "cache_lookup_ms",
            "ms": 0.18454110249876976
          },
          {
            "stage": "eligibility_ms",
            "ms": 0.0
          },
          {
            "stage": "readiness_ms",
            "ms": 0.0
          }
        ]
      },
      {
        "symbol": "000725",
        "report_id": 4,
        "ok": true,
        "cache_hit": true,
        "summary": {
          "fields_total": 10,
          "verified": 0,
          "normalized_match": 0,
          "likely_match": 0,
          "definition_mismatch": 3,
          "period_basis_mismatch": 2,
          "unit_mismatch": 1,
          "value_conflict": 0,
          "structured_field_missing": 4,
          "official_field_not_found": 0,
          "insufficient_evidence": 0,
          "not_applicable": 0,
          "failed": 0
        },
        "profile": {
          "eligibility_ms": 0.0,
          "readiness_ms": 0.0,
          "cache_lookup_ms": 0.2127080224454403,
          "structured_provider_ms": 0.0,
          "rag_document_load_ms": 0.0,
          "retrieval_ms": 0.0,
          "official_extractor_ms": 0.0,
          "unit_normalization_ms": 0.0,
          "field_alignment_ms": 0.0,
          "classification_ms": 0.0,
          "citation_validation_ms": 0.0,
          "result_persistence_ms": 0.0,
          "total_ms": 0.52
        },
        "top3_bottlenecks": [
          {
            "stage": "cache_lookup_ms",
            "ms": 0.2127080224454403
          },
          {
            "stage": "eligibility_ms",
            "ms": 0.0
          },
          {
            "stage": "readiness_ms",
            "ms": 0.0
          }
        ]
      },
      {
        "symbol": "000001",
        "report_id": 5,
        "ok": true,
        "cache_hit": true,
        "summary": {
          "fields_total": 10,
          "verified": 2,
          "normalized_match": 0,
          "likely_match": 0,
          "definition_mismatch": 3,
          "period_basis_mismatch": 1,
          "unit_mismatch": 0,
          "value_conflict": 0,
          "structured_field_missing": 3,
          "official_field_not_found": 0,
          "insufficient_evidence": 1,
          "not_applicable": 0,
          "failed": 0
        },
        "profile": {
          "eligibility_ms": 0.0,
          "readiness_ms": 0.0,
          "cache_lookup_ms": 0.44724997133016586,
          "structured_provider_ms": 0.0,
          "rag_document_load_ms": 0.0,
          "retrieval_ms": 0.0,
          "official_extractor_ms": 0.0,
          "unit_normalization_ms": 0.0,
          "field_alignment_ms": 0.0,
          "classification_ms": 0.0,
          "citation_validation_ms": 0.0,
          "result_persistence_ms": 0.0,
          "total_ms": 0.84
        },
        "top3_bottlenecks": [
          {
            "stage": "cache_lookup_ms",
            "ms": 0.44724997133016586
          },
          {
            "stage": "eligibility_ms",
            "ms": 0.0
          },
          {
            "stage": "readiness_ms",
            "ms": 0.0
          }
        ]
      }
    ]
  },
  "singleflight": [
    {
      "ok": true,
      "real_execution": true,
      "requests": 3,
      "report_id": 1,
      "compute_count": 1,
      "leader_count": 1,
      "reused_count": 2,
      "statuses": [
        "completed",
        "reused",
        "reused"
      ],
      "all_results_equal": true,
      "errors": []
    },
    {
      "ok": true,
      "real_execution": true,
      "requests": 3,
      "report_id": 2,
      "compute_count": 1,
      "leader_count": 1,
      "reused_count": 2,
      "statuses": [
        "completed",
        "reused",
        "reused"
      ],
      "all_results_equal": true,
      "errors": []
    },
    {
      "ok": true,
      "real_execution": true,
      "requests": 3,
      "report_id": 3,
      "compute_count": 1,
      "leader_count": 1,
      "reused_count": 2,
      "statuses": [
        "completed",
        "reused",
        "reused"
      ],
      "all_results_equal": true,
      "errors": []
    },
    {
      "ok": true,
      "real_execution": true,
      "requests": 3,
      "report_id": 4,
      "compute_count": 1,
      "leader_count": 1,
      "reused_count": 2,
      "statuses": [
        "completed",
        "reused",
        "reused"
      ],
      "all_results_equal": true,
      "errors": []
    },
    {
      "ok": true,
      "real_execution": true,
      "requests": 3,
      "report_id": 5,
      "compute_count": 1,
      "leader_count": 1,
      "reused_count": 2,
      "statuses": [
        "completed",
        "reused",
        "reused"
      ],
      "all_results_equal": true,
      "errors": []
    }
  ],
  "cancel": [
    {
      "ok": true,
      "job_id": "fa0ac969-c0d0-4a46-b38c-6416d92ff9d0",
      "created_status": "queued",
      "cancelled_status": "cancelled",
      "polluted_success_cache": false
    },
    {
      "ok": true,
      "job_id": "0008c242-0dac-40fc-a2dd-f4dccea99973",
      "created_status": "queued",
      "cancelled_status": "cancelled",
      "polluted_success_cache": false
    },
    {
      "ok": true,
      "job_id": "2423c730-b106-4c82-8719-d125ee9db874",
      "created_status": "queued",
      "cancelled_status": "cancelled",
      "polluted_success_cache": false
    },
    {
      "ok": true,
      "job_id": "5aaeb46e-ccb2-45f8-b8e5-a9e1c5dedd40",
      "created_status": "queued",
      "cancelled_status": "cancelled",
      "polluted_success_cache": false
    },
    {
      "ok": true,
      "job_id": "12c651a3-9976-43bf-bc98-7d8390410f7b",
      "created_status": "queued",
      "cancelled_status": "cancelled",
      "polluted_success_cache": false
    }
  ],
  "repository_backend": "database",
  "persistent": true
}
```
