# Phase 6T-K Fusion Profile

```json
{
  "phase": "phase6tk_profile",
  "real_execution": true,
  "mock": false,
  "symbols": [
    "600519",
    "300750",
    "000725",
    "000001"
  ],
  "results": [
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
        "eligibility_ms": 0.04654191434383392,
        "readiness_ms": 0.0,
        "cache_lookup_ms": 0.00016577541828155518,
        "structured_provider_ms": 0.0,
        "rag_document_load_ms": 0.0,
        "retrieval_ms": 48.71099814772606,
        "official_extractor_ms": 48.71099814772606,
        "unit_normalization_ms": 0.5035423673689365,
        "field_alignment_ms": 0.5035423673689365,
        "classification_ms": 0.5035423673689365,
        "citation_validation_ms": 0.0,
        "result_persistence_ms": 0.4346664063632488,
        "total_ms": 13208.3
      },
      "top3_bottlenecks": [
        {
          "stage": "retrieval_ms",
          "ms": 48.71099814772606
        },
        {
          "stage": "official_extractor_ms",
          "ms": 48.71099814772606
        },
        {
          "stage": "unit_normalization_ms",
          "ms": 0.5035423673689365
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
        "eligibility_ms": 0.0577080063521862,
        "readiness_ms": 0.0,
        "cache_lookup_ms": 0.00012526288628578186,
        "structured_provider_ms": 0.0,
        "rag_document_load_ms": 0.0,
        "retrieval_ms": 66.00587535649538,
        "official_extractor_ms": 66.00587535649538,
        "unit_normalization_ms": 0.5328753031790257,
        "field_alignment_ms": 0.5328753031790257,
        "classification_ms": 0.5328753031790257,
        "citation_validation_ms": 0.0,
        "result_persistence_ms": 0.4153749905526638,
        "total_ms": 11072.53
      },
      "top3_bottlenecks": [
        {
          "stage": "retrieval_ms",
          "ms": 66.00587535649538
        },
        {
          "stage": "official_extractor_ms",
          "ms": 66.00587535649538
        },
        {
          "stage": "unit_normalization_ms",
          "ms": 0.5328753031790257
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
        "eligibility_ms": 0.06987527012825012,
        "readiness_ms": 0.0,
        "cache_lookup_ms": 0.000250060111284256,
        "structured_provider_ms": 0.0,
        "rag_document_load_ms": 0.0,
        "retrieval_ms": 88.31737283617258,
        "official_extractor_ms": 88.31737283617258,
        "unit_normalization_ms": 0.44075027108192444,
        "field_alignment_ms": 0.44075027108192444,
        "classification_ms": 0.44075027108192444,
        "citation_validation_ms": 0.0,
        "result_persistence_ms": 0.3749169409275055,
        "total_ms": 18850.32
      },
      "top3_bottlenecks": [
        {
          "stage": "retrieval_ms",
          "ms": 88.31737283617258
        },
        {
          "stage": "official_extractor_ms",
          "ms": 88.31737283617258
        },
        {
          "stage": "unit_normalization_ms",
          "ms": 0.44075027108192444
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
        "eligibility_ms": 0.046374741941690445,
        "readiness_ms": 0.0,
        "cache_lookup_ms": 0.000250060111284256,
        "structured_provider_ms": 0.0,
        "rag_document_load_ms": 0.0,
        "retrieval_ms": 159.89795746281743,
        "official_extractor_ms": 159.89795746281743,
        "unit_normalization_ms": 0.4377509467303753,
        "field_alignment_ms": 0.4377509467303753,
        "classification_ms": 0.4377509467303753,
        "citation_validation_ms": 0.0,
        "result_persistence_ms": 0.32008299604058266,
        "total_ms": 10880.11
      },
      "top3_bottlenecks": [
        {
          "stage": "retrieval_ms",
          "ms": 159.89795746281743
        },
        {
          "stage": "official_extractor_ms",
          "ms": 159.89795746281743
        },
        {
          "stage": "unit_normalization_ms",
          "ms": 0.4377509467303753
        }
      ]
    }
  ],
  "p50_latency_ms": 12140.42,
  "p95_latency_ms": 23081.83
}
```
