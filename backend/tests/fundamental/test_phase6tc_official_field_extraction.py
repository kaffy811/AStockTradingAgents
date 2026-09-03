"""
Phase 6T-C: official disclosure field extraction tests.
"""
from __future__ import annotations

import pytest


def _sample_parsed(text: str):
    return {"report_id": "601686-2024", "text_pages": [{"page": 15, "text": text}]}


def test_official_field_extractor_parses_revenue_with_wanyuan():
    from app.services.company_v2_official_field_extractor import extract_official_fields

    result = extract_official_fields(_sample_parsed("营业收入：506,710.926264 万元"), report_id="r1")
    revenue = result["official_fields"]["revenue"]
    assert revenue["value"] == 5067109262.64
    assert revenue["unit"] == "CNY"
    assert revenue["source"] == "cninfo_pdf"
    assert len(revenue["evidence_excerpt"]) <= 200


def test_official_field_extractor_parses_eps():
    from app.services.company_v2_official_field_extractor import extract_official_fields

    result = extract_official_fields(_sample_parsed("基本每股收益（元/股）：0.42"), report_id="r2")
    eps = result["official_fields"]["eps_basic"]
    assert eps["value"] == 0.42
    assert eps["unit"] == "CNY/share"


def test_official_field_extractor_parses_roe_percent_as_decimal():
    from app.services.company_v2_official_field_extractor import extract_official_fields

    result = extract_official_fields(_sample_parsed("加权平均净资产收益率：12.34%"), report_id="r3")
    roe = result["official_fields"]["roe_weighted"]
    assert roe["value"] == 0.1234
    assert roe["unit"] == "%"


def test_official_field_extractor_parses_roe_table_percent_label():
    from app.services.company_v2_official_field_extractor import extract_official_fields

    result = extract_official_fields(_sample_parsed("加权平均净资产收益率（%） 6.50"), report_id="r3b")
    roe = result["official_fields"]["roe_weighted"]
    assert roe["value"] == 0.065


def test_official_field_extractor_parses_cashflow_and_assets():
    from app.services.company_v2_official_field_extractor import extract_official_fields

    text = "\n".join([
        "经营活动产生的现金流量净额：12.5 亿元",
        "资产总计：300.1 亿元",
        "归属于上市公司股东的所有者权益：100.2 亿元",
    ])
    result = extract_official_fields(_sample_parsed(text), report_id="r4")
    fields = result["official_fields"]
    assert fields["operating_cashflow"]["value"] == 1_250_000_000
    assert fields["total_assets"]["value"] == pytest.approx(30_010_000_000)
    assert fields["equity_parent"]["value"] == pytest.approx(10_020_000_000)


def test_official_field_extractor_parses_share_units():
    from app.services.company_v2_official_field_extractor import extract_official_fields

    text = "总股本：147,154.704 万股\n流通股本：14.7154704 亿股"
    result = extract_official_fields(_sample_parsed(text), report_id="r5")
    fields = result["official_fields"]
    assert fields["total_share"]["value"] == 1_471_547_040
    assert fields["float_share"]["value"] == 1_471_547_040


def test_official_field_extractor_handles_pdf_whitespace_parent_profit():
    from app.services.company_v2_official_field_extractor import extract_official_fields

    result = extract_official_fields(_sample_parsed("归属于上市公司股东的净 利润 482,101,037.78"), report_id="r5b")
    assert result["official_fields"]["net_profit_parent"]["value"] == 482101037.78


def test_official_field_extractor_skips_non_recurring_profit_for_net_profit():
    from app.services.company_v2_official_field_extractor import extract_official_fields

    text = "归属于上市公司股东的扣 除非经常性损益的净利润 320,323,351.78"
    result = extract_official_fields(_sample_parsed(text), report_id="r5c")
    assert result["official_fields"]["net_profit"] is None


def test_missing_official_field_returns_null_not_fabricated():
    from app.services.company_v2_official_field_extractor import extract_official_fields

    result = extract_official_fields(_sample_parsed("本页没有目标字段"), report_id="r6")
    assert result["official_fields"]["revenue"] is None
    assert result["official_fields"]["eps_basic"] is None


def test_official_extractor_output_has_no_restricted_advice_wording():
    from app.services.company_v2_official_field_extractor import extract_official_fields

    result = extract_official_fields(_sample_parsed("营业收入：10 万元"), report_id="r7")
    text = str(result)
    for word in ["买入", "卖出", "目标价", "保证上涨"]:
        assert word not in text
