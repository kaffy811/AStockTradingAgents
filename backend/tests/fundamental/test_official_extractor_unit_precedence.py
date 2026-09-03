"""Phase 6T-J2: inline unit takes precedence over table-level declaration."""
from __future__ import annotations

from app.services.company_v2_official_field_extractor import extract_official_fields


def _extract(text: str, field: str):
    parsed = {"text_pages": [{"page": 1, "text": text}], "page_count": 1, "parse_status": "parsed"}
    return extract_official_fields(parsed, report_id=999)["official_fields"][field]


def test_inline_unit_beats_table_unit():
    # table says 千元 but the value itself is annotated 万元 → inline wins
    f = _extract("单位：千元 净利润 1,000 万元", "net_profit")
    assert f["unit_source"] == "inline"
    assert f["raw_unit"] == "万元"
    assert f["value"] == 10000000.0
    assert f["unit_confidence"] == 1.0


def test_table_unit_used_when_no_inline():
    f = _extract("单位：千元 净利润 1,000", "net_profit")
    assert f["unit_source"] == "table_level"
    assert f["unit_confidence"] == 0.9


def test_no_magnitude_based_guessing():
    # A huge bare number must NOT be assumed to be 元
    f = _extract("净利润 76,786,309,000", "net_profit")
    assert f["unit_source"] == "unknown"
    assert f["unit"] is None and f["raw_unit"] is None
