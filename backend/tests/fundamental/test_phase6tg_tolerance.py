from __future__ import annotations


def test_monetary_within_tolerance():
    from app.services.company_v2_financial_evidence_tolerance import within_tolerance

    result = within_tolerance("revenue", 100.0, 100.3)
    assert result["within_tolerance"] is True


def test_monetary_outside_tolerance():
    from app.services.company_v2_financial_evidence_tolerance import within_tolerance

    result = within_tolerance("revenue", 100.0, 110.0)
    assert result["within_tolerance"] is False


def test_percentage_tolerance_uses_fractional_scale():
    from app.services.company_v2_financial_evidence_tolerance import within_tolerance

    result = within_tolerance("roe_weighted", 0.065, 0.0654)
    assert result["within_tolerance"] is True
