"""Phase 6T-J2: unit declarations are table-scoped — no cross-table/page leakage."""
from __future__ import annotations

from app.services.company_v2_official_field_extractor import extract_official_fields


def _fields(pages):
    parsed = {"text_pages": pages, "page_count": len(pages), "parse_status": "parsed"}
    return extract_official_fields(parsed, report_id=999)["official_fields"]


def test_adjacent_tables_different_units_nearest_wins():
    # Two tables on one page: the SECOND declaration governs the second table.
    text = "利润表 单位：千元 营业收入 1,000 现金流量表 单位：万元 净利润 2,000"
    f = _fields([{"page": 1, "text": text}])
    assert f["revenue"]["raw_unit"] == "千元" and f["revenue"]["value"] == 1000000.0
    assert f["net_profit"]["raw_unit"] == "万元" and f["net_profit"]["value"] == 20000000.0


def test_next_page_table_does_not_inherit_previous_unit():
    pages = [
        {"page": 1, "text": "现金流量表补充资料 单位：千元 净利润 76,786,309"},
        {"page": 2, "text": "另一张表 营业收入 5,000"},  # no unit declaration on page 2
    ]
    f = _fields(pages)
    assert f["net_profit"]["raw_unit"] == "千元"
    # page-2 revenue must NOT inherit 千元 from page 1 → unknown
    assert f["revenue"]["unit_source"] == "unknown"
    assert f["revenue"]["raw_unit"] is None
    assert f["revenue"]["unit"] is None
    assert f["revenue"]["value"] == 5000.0  # raw, unscaled
    assert f["revenue"]["classification_hint"] == "unit_context_missing"


def test_same_page_two_tables_field_after_second_decl():
    text = "表一 单位：亿元 资产总计 3.5 表二 单位：千元 净利润 100"
    f = _fields([{"page": 1, "text": text}])
    assert f["total_assets"]["raw_unit"] == "亿元" and f["total_assets"]["value"] == 350000000.0
    assert f["net_profit"]["raw_unit"] == "千元" and f["net_profit"]["value"] == 100000.0
