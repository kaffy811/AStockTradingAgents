from __future__ import annotations


def test_resolved_false_positive_does_not_recur_for_verified_unit_fix():
    from app.services.company_v2_financial_fusion_review_queue import CompanyV2FinancialFusionReviewQueue

    queue = CompanyV2FinancialFusionReviewQueue()
    item = queue.maybe_enqueue_from_record({
        "symbol": "300750",
        "report_id": 3,
        "field_name": "net_profit",
        "fusion_status": "verified",
        "provider_value": 76786309000,
        "official_value": 76786309000,
        "official_page": 200,
        "source_trace_json": {"official": {"raw_unit": "千元", "unit_source": "table_level"}},
    })
    assert item is None
    assert queue.list() == []
