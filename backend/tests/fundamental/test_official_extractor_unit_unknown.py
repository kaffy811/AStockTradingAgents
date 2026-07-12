"""Phase 6T-J2: unknown unit is surfaced honestly — never defaulted to 元."""
from __future__ import annotations

from app.services.company_v2_official_field_extractor import extract_official_fields


def _extract(text: str, field: str):
    parsed = {"text_pages": [{"page": 1, "text": text}], "page_count": 1, "parse_status": "parsed"}
    return extract_official_fields(parsed, report_id=999)["official_fields"][field]


def test_unknown_unit_contract():
    f = _extract("净利润 76,786,309", "net_profit")
    assert f["raw_unit"] is None
    assert f["unit"] is None
    assert f["unit_scale"] is None
    assert f["unit_source"] == "unknown"
    assert f["unit_confidence"] == 0.0
    assert f["classification_hint"] == "unit_context_missing"
    assert f["value"] == 76786309.0  # raw only, unscaled


def test_intrinsic_unit_fields_not_affected():
    eps = _extract("基本每股收益（元/股） 60.51", "eps_basic")
    assert eps["unit"] == "CNY/share" and eps["unit_source"] == "intrinsic"
    roe = _extract("加权平均净资产收益率（%） 34.66", "roe_weighted")
    assert roe["unit"] == "%"


def test_comma_and_fullwidth_comma_values():
    f = _extract("单位：千元 净利润 1，234,567", "net_profit")
    assert f["raw_value"] == 1234567.0 and f["value"] == 1234567000.0
