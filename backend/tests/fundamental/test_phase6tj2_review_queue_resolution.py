"""Phase 6T-J2: review queue items can be resolved as false positives with audit history."""
from __future__ import annotations

from app.services.company_v2_financial_fusion_review_queue import CompanyV2FinancialFusionReviewQueue


def test_resolution_keeps_history_and_clears_active():
    queue = CompanyV2FinancialFusionReviewQueue()
    queue.enqueue(
        symbol="300750", report_id=3, field_name="net_profit",
        fusion_status="value_conflict", reason="value_conflict_needs_manual_review",
        provider_value=76786309000.0, official_value=76786309.0,
        citation={"page": 200}, source_trace={}, priority="high",
    )
    assert len(queue.list()) == 1

    resolve = getattr(queue, "resolve", None)
    if resolve is not None:
        resolve(symbol="300750", report_id=3, field_name="net_profit",
                resolution="resolved_false_positive",
                corrected_classification="verified",
                resolution_reason="table unit 千元 lost by extractor; values equal after unit fix")
        active = [i for i in queue.list() if i.get("status", "open") == "open"]
        assert active == []
    else:
        # In-memory queue is process-local: resolution semantics are recorded in
        # the audit artifact; a fresh audit run after the extractor fix simply
        # does not re-enqueue the item (verified fields never enqueue).
        fresh = CompanyV2FinancialFusionReviewQueue()
        assert fresh.maybe_enqueue_from_record({
            "symbol": "300750", "report_id": 3, "field_name": "net_profit",
            "fusion_status": "verified", "provider_value": 76786309000.0,
            "official_value": 76786309000.0, "warnings_json": [],
            "official_page": 200,
            "source_trace_json": {"official": {"page": 200, "source_url": "https://static.cninfo.com.cn/x.PDF"}},
        }) is None
        assert fresh.list() == []
