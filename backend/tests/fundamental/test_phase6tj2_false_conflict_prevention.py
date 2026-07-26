"""Phase 6T-J2: hard guard — value_conflict requires full unit context."""
from __future__ import annotations

from app.services.company_v2_financial_evidence_fusion_service import _fuse_field


def _structured():
    return {
        "value": 1000000.0,
        "unit": "CNY",
        "provider_definition": "net_profit",
        "provider_period": "2025-12-31",
        "value_basis": "annual_cumulative",
        "provider_name": "netProfit",
        "confidence": 0.9,
        "source_trace": {"source": "artifact_seed", "field_name": "net_profit"},
    }


def _official(value, unit, *, unit_source, hint=None, score=0.9):
    return {
        "status": "resolved",
        "retrieval_mode": "extractor",
        "candidate": {
            "value": value, "unit": unit, "unit_source": unit_source,
            "classification_hint": hint,
            "definition": "净利润", "period": "2025-12-31",
            "value_basis": "annual_cumulative", "page": 10, "chunk_id": None,
            "excerpt": "净利润 …", "source_url": "", "score": score,
        },
        "warnings": [],
    }


def test_unknown_unit_source_blocks_conflict():
    r = _fuse_field(symbol="600519", report_id=2, report_year=2025, report_type="annual",
                    field_name="net_profit", structured=_structured(),
                    official_result=_official(999.0, None, unit_source="unknown", hint="unit_context_missing"))
    assert r.fusion_status == "unit_mismatch"


def test_missing_unit_with_value_blocks_conflict():
    r = _fuse_field(symbol="600519", report_id=2, report_year=2025, report_type="annual",
                    field_name="net_profit", structured=_structured(),
                    official_result=_official(999.0, None, unit_source=None))
    assert r.fusion_status != "value_conflict"


def test_known_unit_over_tolerance_still_conflicts():
    # full unit context + same definition/period + beyond tolerance → genuine conflict allowed
    r = _fuse_field(symbol="600519", report_id=2, report_year=2025, report_type="annual",
                    field_name="net_profit", structured=_structured(),
                    official_result=_official(2000000.0, "CNY", unit_source="table_level"))
    assert r.fusion_status == "value_conflict"


def test_known_unit_within_tolerance_verified():
    r = _fuse_field(symbol="600519", report_id=2, report_year=2025, report_type="annual",
                    field_name="net_profit", structured=_structured(),
                    official_result=_official(1000000.0, "CNY", unit_source="inline"))
    assert r.fusion_status == "verified"
