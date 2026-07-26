"""
Phase 6T-C1: live annual-history official verification gate tests.
"""
from __future__ import annotations


def test_verify_selects_annual_row_by_report_year():
    from app.services.company_v2_official_verification_service import extract_structured_fields, verify_official_fields

    debug_data = {
        "modules": {
            "profitability": {
                "history": [
                    {"period": "2024-03-31", "revenue": 10.0},
                    {"period": "2024-12-31", "revenue": 100.0, "net_profit_parent": 8.0},
                ]
            }
        }
    }
    structured = extract_structured_fields(debug_data, report_year=2024, report_type="annual", annual_required=True)
    result = verify_official_fields(
        structured,
        {"revenue": {"value": 100.0, "page": 6}, "net_profit_parent": {"value": 8.0, "page": 6}},
        report_year=2024,
        report_type="annual",
    )
    assert result["fields"]["revenue"]["status"] == "verified"
    assert result["fields"]["revenue"]["structured_period"] == "2024-12-31"
    assert result["fields"]["revenue"]["official_report_year"] == 2024


def test_verify_rejects_latest_row_if_period_mismatch():
    from app.services.company_v2_official_verification_service import (
        STRUCTURED_ANNUAL_ROW_NOT_FOUND,
        extract_structured_fields,
        verify_official_fields,
    )

    debug_data = {"modules": {"profitability": {"latest": {"period": "2026-03-31", "revenue": 999.0}}}}
    structured = extract_structured_fields(debug_data, report_year=2024, report_type="annual", annual_required=True)
    result = verify_official_fields(structured, {"revenue": {"value": 100.0}}, report_year=2024, report_type="annual")
    assert result["fields"]["revenue"]["status"] == "unverified"
    assert result["fields"]["revenue"]["reason"] == STRUCTURED_ANNUAL_ROW_NOT_FOUND
    assert result["fields"]["revenue"]["status"] != "conflict"


def test_verify_rejects_quarterly_row_for_annual_report():
    from app.services.company_v2_official_verification_service import (
        ANNUAL_PERIOD_REQUIRED,
        extract_structured_fields,
        verify_official_fields,
    )

    debug_data = {"modules": {"profitability": {"history": [{"period": "2024-03-31", "revenue": 100.0}]}}}
    structured = extract_structured_fields(debug_data, report_year=2024, report_type="annual", annual_required=True)
    result = verify_official_fields(structured, {"revenue": {"value": 100.0}}, report_year=2024, report_type="annual")
    assert result["fields"]["revenue"]["status"] == "unverified"
    assert result["fields"]["revenue"]["reason"] == ANNUAL_PERIOD_REQUIRED
    assert result["period_mismatch_count"] >= 1


def test_annual_row_missing_returns_structured_row_not_found():
    from app.services.company_v2_official_verification_service import (
        STRUCTURED_ANNUAL_ROW_NOT_FOUND,
        extract_structured_fields,
        verify_official_fields,
    )

    structured = extract_structured_fields({"modules": {"profitability": {"history": []}}}, report_year=2024, report_type="annual", annual_required=True)
    result = verify_official_fields(structured, {"revenue": {"value": 100.0}}, report_year=2024, report_type="annual")
    assert result["fields"]["revenue"]["status"] == "unverified"
    assert result["fields"]["revenue"]["reason"] in {STRUCTURED_ANNUAL_ROW_NOT_FOUND, "STRUCTURED_FIELD_MISSING"}


def test_period_mismatch_does_not_become_provider_conflict():
    from app.services.company_v2_official_verification_service import extract_structured_fields, verify_official_fields

    structured = extract_structured_fields(
        {"modules": {"profitability": {"history": [{"period": "2025-12-31", "revenue": 999.0}]}}},
        report_year=2024,
        report_type="annual",
        annual_required=True,
    )
    result = verify_official_fields(structured, {"revenue": {"value": 100.0}}, report_year=2024, report_type="annual")
    assert result["conflict_fields_count"] == 0
    assert result["provider_value_conflict_count"] == 0


def test_unit_mismatch_classified_correctly():
    from app.services.company_v2_official_verification_service import UNIT_SCALE_MISMATCH, verify_official_fields

    structured = {"revenue": {"value": 100.0, "structured_period": "2024-12-31"}}
    result = verify_official_fields(structured, {"revenue": {"value": 1_000_000.0}}, report_year=2024, report_type="annual")
    assert result["fields"]["revenue"]["status"] == "conflict"
    assert result["fields"]["revenue"]["conflict_type"] == UNIT_SCALE_MISMATCH
    assert result["unit_mismatch_count"] == 1


def test_provider_value_conflict_classified_correctly():
    from app.services.company_v2_official_verification_service import PROVIDER_VALUE_CONFLICT, verify_official_fields

    structured = {"revenue": {"value": 100.0, "structured_period": "2024-12-31"}}
    result = verify_official_fields(structured, {"revenue": {"value": 150.0, "confidence": 0.95}}, report_year=2024, report_type="annual")
    assert result["fields"]["revenue"]["status"] == "conflict"
    assert result["fields"]["revenue"]["conflict_type"] == PROVIDER_VALUE_CONFLICT
    assert result["provider_value_conflict_count"] == 1


def test_verified_field_includes_required_evidence_fields():
    from app.services.company_v2_official_verification_service import verify_official_fields

    result = verify_official_fields(
        {"revenue": {"value": 100.0, "structured_period": "2024-12-31"}},
        {"revenue": {"value": 100.0, "page": 6}},
        report_year=2024,
        report_type="annual",
    )
    field = result["fields"]["revenue"]
    assert field["official_value"] == 100.0
    assert field["structured_value"] == 100.0
    assert field["structured_period"] == "2024-12-31"
    assert field["official_report_year"] == 2024
    assert field["evidence_page"] == 6


def test_api_source_excludes_local_path_and_advice_wording():
    from pathlib import Path

    src = (Path(__file__).resolve().parents[3] / "backend/app/routers/company_v2_debug.py").read_text()
    assert "_strip_sensitive_report_payload" in src
    assert "local_path" in src
    for word in ["买入", "卖出", "目标价", "保证上涨"]:
        assert word not in src
