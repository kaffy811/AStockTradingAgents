from __future__ import annotations


def test_profile_requires_stage_breakdown_and_top_bottlenecks():
    profile = {
        "eligibility_ms": 1,
        "readiness_ms": 2,
        "cache_lookup_ms": 3,
        "structured_provider_ms": 4,
        "rag_document_load_ms": 5,
        "retrieval_ms": 6,
        "official_extractor_ms": 7,
        "unit_normalization_ms": 8,
        "field_alignment_ms": 9,
        "classification_ms": 10,
        "citation_validation_ms": 11,
        "result_persistence_ms": 12,
        "total_ms": 78,
    }
    required = [
        "eligibility_ms", "readiness_ms", "cache_lookup_ms", "structured_provider_ms",
        "rag_document_load_ms", "retrieval_ms", "official_extractor_ms",
        "unit_normalization_ms", "field_alignment_ms", "classification_ms",
        "citation_validation_ms", "result_persistence_ms", "total_ms",
    ]
    assert all(key in profile for key in required)
    top3 = sorted((item for item in profile.items() if item[0] != "total_ms"), key=lambda item: item[1], reverse=True)[:3]
    assert [name for name, _ in top3] == ["result_persistence_ms", "citation_validation_ms", "classification_ms"]
