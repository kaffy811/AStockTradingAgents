from __future__ import annotations


def test_money_unit_normalization_to_cny():
    from app.services.company_v2_financial_unit_normalizer import normalize_financial_value

    result = normalize_financial_value(12.5, "万元")
    assert result["normalized_unit"] == "CNY"
    assert result["normalized_value"] == 125000.0
    assert result["conversion_trace"] == "万元→CNY"


def test_share_unit_normalization_to_shares():
    from app.services.company_v2_financial_unit_normalizer import normalize_financial_value

    result = normalize_financial_value(1.23, "亿股")
    assert result["normalized_unit"] == "shares"
    assert result["normalized_value"] == 123000000.0


def test_eps_unit_keeps_cny_per_share():
    from app.services.company_v2_financial_unit_normalizer import normalize_financial_value

    result = normalize_financial_value(0.3, "CNY/share")
    assert result["normalized_unit"] == "CNY/share"
    assert result["normalized_value"] == 0.3


def test_unknown_unit_is_reported():
    from app.services.company_v2_financial_unit_normalizer import normalize_financial_value

    result = normalize_financial_value(10, "bogus")
    assert result["status"] == "unknown_unit"
