"""Phase 6T-J2: table-level unit context detection and scaling."""
from __future__ import annotations

from app.services.company_v2_official_field_extractor import extract_official_fields


def _extract(text: str, field: str, page: int = 1):
    parsed = {"text_pages": [{"page": page, "text": text}], "page_count": page, "parse_status": "parsed"}
    return extract_official_fields(parsed, report_id=999)["official_fields"][field]


def test_table_unit_thousand_cny_scales_value():
    text = "现金流量表补充资料 单位：千元 补充资料 本期金额 净利润 76,786,309 加：资产减值准备 8,660,164"
    f = _extract(text, "net_profit")
    assert f["raw_value"] == 76786309.0
    assert f["raw_unit"] == "千元"
    assert f["unit_scale"] == 1000.0
    assert f["value"] == 76786309000.0
    assert f["unit"] == "CNY"
    assert f["unit_source"] == "table_level"
    assert f["unit_evidence_text"] == "单位：千元"


def test_table_unit_yuan():
    f = _extract("主要会计数据 单位：元 币种：人民币 营业收入 54,822,111,649.52", "revenue")
    assert f["raw_unit"] == "元" and f["unit_scale"] == 1.0 and f["value"] == 54822111649.52
    assert f["unit_source"] == "table_level"


def test_table_unit_wan_yuan():
    f = _extract("单位：万元 净利润 1,234.56", "net_profit")
    assert f["unit_scale"] == 1e4 and f["value"] == 12345600.0


def test_table_unit_million_yuan():
    f = _extract("单位：百万元 净利润 1,234", "net_profit")
    assert f["unit_scale"] == 1e6 and f["value"] == 1234000000.0


def test_table_unit_yi_yuan():
    f = _extract("单位：亿元 净利润 12.5", "net_profit")
    assert f["unit_scale"] == 1e8 and f["value"] == 1250000000.0


def test_rmb_prefixed_unit():
    f = _extract("单位：人民币千元 净利润 100", "net_profit")
    assert f["raw_unit"] == "千元" and f["value"] == 100000.0
