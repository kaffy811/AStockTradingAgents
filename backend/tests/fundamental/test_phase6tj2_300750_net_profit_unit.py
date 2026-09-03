"""Phase 6T-J2: contract regression for the 300750 net_profit false conflict.

Uses generic thousand-CNY supplementary-cashflow-table evidence — no hardcoded
symbol/report/page branch exists in the production code; this test simply
replays the same evidence shape through the real resolver+fusion path.
"""
from __future__ import annotations

from app.services.company_v2_financial_evidence_fusion_service import _fuse_field


def _structured(value: float):
    return {
        "value": value,
        "unit": "CNY",
        "provider_definition": "net_profit",
        "provider_period": "2025-12-31",
        "value_basis": "annual_cumulative",
        "provider_name": "netProfit",
        "confidence": 0.9,
        "source_trace": {"source": "artifact_seed", "field_name": "net_profit"},
    }


def _official_result(value: float, unit: str | None, *, unit_source: str, raw_unit: str | None):
    return {
        "status": "resolved",
        "retrieval_mode": "extractor",
        "candidate": {
            "value": value,
            "unit": unit,
            "raw_unit": raw_unit,
            "unit_source": unit_source,
            "unit_confidence": 0.9 if unit_source == "table_level" else 0.0,
            "classification_hint": None if unit else "unit_context_missing",
            "definition": "净利润",
            "period": "2025-12-31",
            "value_basis": "annual_cumulative",
            "page": 200,
            "chunk_id": None,
            "excerpt": "现金流量表补充资料 单位：千元 净利润 76,786,309",
            "source_url": "https://static.cninfo.com.cn/finalpage/x.PDF",
            "score": 0.85,
        },
        "warnings": [],
    }


def test_thousand_cny_table_value_is_verified_not_conflict():
    # extractor now normalizes 76,786,309 千元 -> 76,786,309,000 CNY
    record = _fuse_field(
        symbol="300750",
        report_id=3,
        report_year=2025,
        report_type="annual",
        field_name="net_profit",
        structured=_structured(76786309000.0),
        official_result=_official_result(76786309000.0, "CNY", unit_source="table_level", raw_unit="千元"),
    )
    assert record.fusion_status == "verified"
    assert record.official_value == 76786309000.0


def test_pre_fix_shape_unknown_unit_cannot_conflict():
    # the OLD broken shape (raw value, unit unknown) must now classify as
    # unit_mismatch — value_conflict is forbidden without unit context
    record = _fuse_field(
        symbol="300750",
        report_id=3,
        report_year=2025,
        report_type="annual",
        field_name="net_profit",
        structured=_structured(76786309000.0),
        official_result=_official_result(76786309.0, None, unit_source="unknown", raw_unit=None),
    )
    assert record.fusion_status == "unit_mismatch"
    assert record.fusion_status != "value_conflict"


def test_review_queue_not_triggered_for_verified():
    from app.services.company_v2_financial_fusion_review_queue import CompanyV2FinancialFusionReviewQueue

    queue = CompanyV2FinancialFusionReviewQueue()
    record = _fuse_field(
        symbol="300750",
        report_id=3,
        report_year=2025,
        report_type="annual",
        field_name="net_profit",
        structured=_structured(76786309000.0),
        official_result=_official_result(76786309000.0, "CNY", unit_source="table_level", raw_unit="千元"),
    )
    from dataclasses import asdict

    assert queue.maybe_enqueue_from_record(asdict(record)) is None
    assert queue.list() == []
