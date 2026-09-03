from __future__ import annotations


def test_stage_progress_is_monotonic_and_user_safe():
    from app.services.company_v2_financial_fusion_job_service import STAGE_PROGRESS

    stages = [
        "eligibility",
        "readiness",
        "cache_lookup",
        "structured_data_load",
        "rag_retrieval",
        "official_evidence_extract",
        "unit_normalization",
        "field_alignment",
        "classification",
        "citation_validation",
        "result_persistence",
        "completed",
    ]
    values = [STAGE_PROGRESS[stage] for stage in stages]
    assert values == sorted(values)
    assert STAGE_PROGRESS["completed"] == 1.0
