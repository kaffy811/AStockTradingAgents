from __future__ import annotations


def test_review_queue_accepts_conflicts_and_low_confidence():
    from app.services.company_v2_financial_fusion_review_queue import company_v2_financial_fusion_review_queue

    company_v2_financial_fusion_review_queue.clear()
    conflict = company_v2_financial_fusion_review_queue.maybe_enqueue_from_record(
        {
            "symbol": "601686",
            "report_id": 1,
            "field_name": "revenue",
            "fusion_status": "value_conflict",
            "confidence": 0.6,
            "official_page": 6,
            "official_value": 1,
            "official_excerpt": "x",
            "source_trace_json": {"official": {"source_url": "https://static.cninfo.com.cn/a.pdf"}},
        }
    )
    assert conflict["fusion_status"] == "value_conflict"
    assert len(company_v2_financial_fusion_review_queue.list()) == 1
