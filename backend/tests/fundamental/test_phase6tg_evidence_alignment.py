from __future__ import annotations


def test_definition_mismatch_is_detected():
    from app.services.company_v2_financial_evidence_alignment import align_financial_evidence

    result = align_financial_evidence(
        symbol="601686",
        report_id=1,
        report_year=2024,
        report_type="annual",
        field_name="revenue",
        provider_definition="main_business_revenue",
        provider_period="2024-12-31",
        provider_value_basis="annual_cumulative",
        provider_unit="CNY",
        official_definition="营业收入",
        official_period="2024-12-31",
        official_value_basis="annual_cumulative",
        official_unit="CNY",
    )
    assert result["status"] == "definition_mismatch"


def test_period_basis_mismatch_is_detected():
    from app.services.company_v2_financial_evidence_alignment import align_financial_evidence

    result = align_financial_evidence(
        symbol="601686",
        report_id=1,
        report_year=2024,
        report_type="annual",
        field_name="total_share",
        provider_definition="total_share",
        provider_period="2024-12-31",
        provider_value_basis="point_in_time",
        provider_unit="shares",
        official_definition="总股本",
        official_period="2024-12-12",
        official_value_basis="point_in_time",
        official_unit="shares",
    )
    assert result["status"] == "period_basis_mismatch"


def test_equal_definition_and_period_are_comparable():
    from app.services.company_v2_financial_evidence_alignment import align_financial_evidence

    result = align_financial_evidence(
        symbol="601686",
        report_id=1,
        report_year=2024,
        report_type="annual",
        field_name="net_profit",
        provider_definition="net_profit",
        provider_period="2024-12-31",
        provider_value_basis="annual_cumulative",
        provider_unit="CNY",
        official_definition="净利润",
        official_period="2024-12-31",
        official_value_basis="annual_cumulative",
        official_unit="CNY",
    )
    assert result["comparable"] is True
    assert result["status"] == "comparable"
