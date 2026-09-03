"""
Phase 6T-C: structured-vs-official verification and accuracy audit tests.
"""
from __future__ import annotations


def test_verification_passes_within_amount_tolerance():
    from app.services.company_v2_official_verification_service import verify_official_fields

    structured = {"revenue": {"value": 100.0}}
    official = {"revenue": {"value": 100.5, "page": 15}}
    result = verify_official_fields(structured, official)
    assert result["fields"]["revenue"]["status"] == "verified"
    assert result["verified_fields_count"] >= 1


def test_verification_conflict_outside_tolerance():
    from app.services.company_v2_official_verification_service import verify_official_fields

    structured = {"revenue": {"value": 100.0}}
    official = {"revenue": {"value": 120.0, "page": 15}}
    result = verify_official_fields(structured, official)
    assert result["status"] == "conflict"
    assert result["fields"]["revenue"]["status"] == "conflict"


def test_missing_official_field_is_unverified():
    from app.services.company_v2_official_verification_service import verify_official_fields

    result = verify_official_fields({"revenue": {"value": 100.0}}, {"revenue": None})
    assert result["fields"]["revenue"]["status"] == "unverified"


def test_eps_tolerance_accepts_small_abs_diff():
    from app.services.company_v2_official_verification_service import verify_official_fields

    result = verify_official_fields({"eps_basic": {"value": 0.421}}, {"eps_basic": {"value": 0.42}})
    assert result["fields"]["eps_basic"]["status"] == "verified"


def test_roe_tolerance_uses_percentage_points():
    from app.services.company_v2_official_verification_service import verify_official_fields

    result = verify_official_fields({"roe": {"value": 0.120}}, {"roe_weighted": {"value": 0.124}})
    assert result["fields"]["roe"]["status"] == "verified"


def test_share_tolerance_is_strict():
    from app.services.company_v2_official_verification_service import verify_official_fields

    result = verify_official_fields({"total_share": {"value": 1000}}, {"total_share": {"value": 1002}})
    assert result["fields"]["total_share"]["status"] == "conflict"


def test_extract_structured_fields_from_modules():
    from app.services.company_v2_official_verification_service import extract_structured_fields

    debug_data = {
        "modules": {
            "growth": {"normalized": {"fields": {"revenue": {"value": 123}}}},
            "profitability": {"normalized": {"fields": {"roe": {"value": 0.1}}}},
        }
    }
    fields = extract_structured_fields(debug_data)
    assert fields["revenue"]["value"] == 123
    assert fields["roe"]["value"] == 0.1


def test_extract_structured_fields_reads_latest_rows_when_fields_missing():
    from app.services.company_v2_official_verification_service import extract_structured_fields

    debug_data = {
        "modules": {
            "profitability": {
                "normalized": {
                    "fields": {"roe": {"value": 0.1}},
                    "rows": [{"revenue": 1000.0, "net_profit_parent": 120.0}],
                }
            }
        }
    }
    fields = extract_structured_fields(debug_data)
    assert fields["revenue"]["value"] == 1000.0
    assert fields["net_profit_parent"]["value"] == 120.0


def test_extract_structured_fields_prefers_matching_report_year():
    from app.services.company_v2_official_verification_service import extract_structured_fields

    debug_data = {
        "modules": {
            "profitability": {
                "normalized": {
                    "rows": [
                        {"period": "2026-03-31", "revenue": 1000.0},
                        {"period": "2024-12-31", "revenue": 888.0},
                    ]
                }
            }
        }
    }
    fields = extract_structured_fields(debug_data, report_year=2024)
    assert fields["revenue"]["value"] == 888.0


def test_accuracy_audit_upgrades_field_to_official_verified():
    from app.services.company_v2_accuracy_audit_service import audit_envelope

    envelope = {
        "module_key": "growth",
        "normalized": {
            "fields": {
                "revenue": {"value": 100.0, "provider": "baostock", "computed": False},
            }
        },
        "official_verification": {
            "fields": {
                "revenue": {"status": "verified", "official_value": 100.0, "structured_value": 100.0},
            }
        },
    }
    result = audit_envelope(envelope, official_verification=envelope["official_verification"])
    assert result["field_verdicts"]["revenue"] == "official_disclosure_verified"
    assert "revenue" in result["official_disclosure_fields"]


def test_accuracy_audit_marks_conflict():
    from app.services.company_v2_accuracy_audit_service import audit_envelope

    envelope = {
        "module_key": "growth",
        "normalized": {"fields": {"revenue": {"value": 100.0, "provider": "baostock"}}},
    }
    verification = {"status": "conflict", "fields": {"revenue": {"status": "conflict"}}}
    result = audit_envelope(envelope, official_verification=verification)
    assert result["field_verdicts"]["revenue"] == "official_disclosure_conflict"
    assert result["source_conflicts"]


def test_verification_output_has_no_restricted_advice_wording():
    from app.services.company_v2_official_verification_service import verify_official_fields

    result = verify_official_fields({"revenue": {"value": 100}}, {"revenue": {"value": 100}})
    text = str(result)
    for word in ["买入", "卖出", "目标价", "保证上涨"]:
        assert word not in text
