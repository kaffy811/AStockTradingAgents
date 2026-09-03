from __future__ import annotations


def test_registry_separates_similar_fields():
    from app.services.company_v2_financial_field_definition_registry import get_field_profile

    revenue = get_field_profile("revenue")
    main_revenue = get_field_profile("main_business_revenue")
    net_profit = get_field_profile("net_profit")
    parent_profit = get_field_profile("net_profit_parent")
    roe = get_field_profile("roe")
    roe_weighted = get_field_profile("roe_weighted")

    assert revenue["canonical_name"] == "营业收入"
    assert main_revenue["canonical_name"] == "主营业务收入"
    assert net_profit["expected_unit"] == "CNY"
    assert parent_profit["expected_unit"] == "CNY"
    assert roe["expected_unit"] == "%"
    assert roe_weighted["expected_unit"] == "%"
    assert "main_business_revenue" in revenue["incompatible_with"]
    assert "net_profit_parent" in net_profit["incompatible_with"]
    assert "roe_weighted" in roe["incompatible_with"]


def test_registry_contains_official_and_provider_labels():
    from app.services.company_v2_financial_field_definition_registry import get_field_profile

    profile = get_field_profile("equity_parent")
    assert "归属于上市公司股东的净资产" in profile["official_report_labels"]
    assert "归属于上市公司股东的所有者权益" in profile["official_report_labels"]
    assert profile["value_basis"] == "point_in_time"
