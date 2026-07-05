"""
tests/fundamental/test_phase2d_api_contract.py — Phase 2D API 契约测试

契约测试列表：
C1:  所有 available/legacy 模块都有 render_type
C2:  所有 available/legacy 模块都有 field_labels (dict，可为空仅对 legacy)
C3:  所有 available/legacy 模块都有 unit_hints (dict，可为空仅对 legacy)
C4:  所有 available/legacy 模块都有 description (非空字符串)
C5:  /api/v1/modules 不返回 alias（alias_of 为 None 或不存在）
C6:  /api/v1/modules group_seq 有效 (1-8)
C7:  MODULE_CATALOG display=True 条目 seq 单调递增
C8:  每个 available 模块 example JSON 符合顶层字段集合
C9:  frontend/mock 与 docs/api_examples 文件存在且结构一致
C10: build_api_response 返回 meta 字段
C11: build_api_response errors 永远是 list
C12: build_api_response meta 永远存在（包括 module_meta=None 时）
C13: planned 模块 render_type=placeholder
C14: analyst_ratings 描述不含"机构买入"/"确定评级"/"投资建议"/"研究报告"等误导词
C15: MODULE_CATALOG display=True 条目总数 >= 27
C16: 每个 available 模块有 data_freshness 字段（合法值）
C17: 每个 available 模块有 disclaimer_type 字段（合法值）
C18: build_api_response with module_meta 返回正确的 group 和 group_seq
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# ── Path setup ────────────────────────────────────────────────────────────────
ROOT = Path(__file__).parent.parent.parent.parent  # repo root
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

from app.tools.fundamental import MODULE_CATALOG, TOOL_REGISTRY
from app.aggregator.envelope import build_api_response, ok_envelope, err_envelope

# ── Constants ─────────────────────────────────────────────────────────────────

API_EXAMPLES_DIR = ROOT / "docs" / "api_examples"
FRONTEND_MOCK_DIR = ROOT / "frontend" / "mock" / "fundamentals"

VALID_RENDER_TYPES = {
    "metric_cards", "chart_table", "table", "timeline",
    "mixed", "ai_card", "placeholder",
}
VALID_CHART_TYPES = {
    "line", "bar", "stacked_bar", "area", "pie",
    "donut", "radar", "timeline", "none",
}
VALID_DATA_FRESHNESS = {"realtime", "daily", "quarterly", "annual", "static"}
VALID_DISCLAIMER_TYPES = {
    "data_only", "ai_generated", "not_investment_advice", "estimated", "third_party_optional",
}

# Modules with status=available or status=legacy (not planned, not hidden)
_AVAILABLE_MODULES = [
    m for m in MODULE_CATALOG
    if m.get("display") and m.get("status") in ("available", "legacy")
]

_PLANNED_MODULES = [
    m for m in MODULE_CATALOG
    if m.get("display") and m.get("status") == "planned"
]

_ALL_DISPLAY_MODULES = [
    m for m in MODULE_CATALOG
    if m.get("display") and m.get("status") != "hidden"
]

_EXPECTED_ENVELOPE_KEYS = {
    "market", "symbol", "ts_code", "module_key", "module_name",
    "group", "group_seq", "data", "errors", "partial", "stale",
    "generated_at", "source", "meta",
}

_EXPECTED_META_KEYS = {"render_type", "chart_type", "unit_hints", "field_labels", "empty_state"}

# ── C1: available/legacy 模块都有 render_type ──────────────────────────────────

def test_C1_available_modules_have_render_type():
    """C1: All available/legacy modules must have a valid render_type."""
    for m in _AVAILABLE_MODULES:
        rt = m.get("render_type")
        assert rt is not None, f"{m['key']}: missing render_type"
        assert rt in VALID_RENDER_TYPES, f"{m['key']}: invalid render_type={rt!r}"


# ── C2: available/legacy 模块都有 field_labels ────────────────────────────────

def test_C2_available_modules_have_field_labels():
    """C2: All available/legacy modules must have field_labels as a dict."""
    for m in _AVAILABLE_MODULES:
        fl = m.get("field_labels")
        assert fl is not None, f"{m['key']}: missing field_labels"
        assert isinstance(fl, dict), f"{m['key']}: field_labels must be dict, got {type(fl)}"


# ── C3: available/legacy 模块都有 unit_hints ──────────────────────────────────

def test_C3_available_modules_have_unit_hints():
    """C3: All available/legacy modules must have unit_hints as a dict."""
    for m in _AVAILABLE_MODULES:
        uh = m.get("unit_hints")
        assert uh is not None, f"{m['key']}: missing unit_hints"
        assert isinstance(uh, dict), f"{m['key']}: unit_hints must be dict, got {type(uh)}"


# ── C4: available/legacy 模块都有 description ─────────────────────────────────

def test_C4_available_modules_have_description():
    """C4: All available/legacy modules must have a non-empty description string."""
    for m in _AVAILABLE_MODULES:
        desc = m.get("description")
        assert desc, f"{m['key']}: missing or empty description"
        assert isinstance(desc, str), f"{m['key']}: description must be str"
        assert len(desc.strip()) > 0, f"{m['key']}: description is blank"


# ── C5: display=True 条目 alias_of 必须为 None ────────────────────────────────

def test_C5_display_modules_have_no_alias():
    """C5: All display=True modules must not be aliases (alias_of must be None)."""
    for m in _ALL_DISPLAY_MODULES:
        alias = m.get("alias_of")
        assert alias is None, f"{m['key']}: display=True but alias_of={alias!r}"


# ── C6: group_seq 在 1-8 范围内 ───────────────────────────────────────────────

def test_C6_group_seq_valid_range():
    """C6: All display=True modules must have group_seq in [1, 8]."""
    for m in _ALL_DISPLAY_MODULES:
        gs = m.get("group_seq")
        assert gs is not None, f"{m['key']}: missing group_seq"
        assert isinstance(gs, int), f"{m['key']}: group_seq must be int"
        assert 1 <= gs <= 8, f"{m['key']}: group_seq={gs} out of range [1, 8]"


# ── C7: display=True 条目 seq 单调递增 ───────────────────────────────────────

def test_C7_display_module_seq_monotonic():
    """C7: display=True modules must have strictly increasing seq values."""
    seqs = [m["seq"] for m in _ALL_DISPLAY_MODULES]
    for i in range(len(seqs) - 1):
        assert seqs[i] < seqs[i + 1], (
            f"seq not monotonically increasing at index {i}: "
            f"{seqs[i]} >= {seqs[i+1]} (keys: "
            f"{_ALL_DISPLAY_MODULES[i]['key']} vs {_ALL_DISPLAY_MODULES[i+1]['key']})"
        )


# ── C8: 每个 available 模块 example JSON 符合顶层字段集合 ──────────────────────

def test_C8_example_json_top_level_keys():
    """C8: Each available module must have an example JSON with correct top-level keys."""
    available_keys = [m["key"] for m in _AVAILABLE_MODULES]
    for key in available_keys:
        json_file = API_EXAMPLES_DIR / f"{key}.json"
        assert json_file.exists(), f"Missing example JSON: {json_file}"

        data = json.loads(json_file.read_text(encoding="utf-8"))
        missing = _EXPECTED_ENVELOPE_KEYS - set(data.keys())
        assert not missing, f"{key}.json: missing top-level keys: {missing}"

        # Check meta sub-keys
        meta = data.get("meta", {})
        missing_meta = _EXPECTED_META_KEYS - set(meta.keys())
        assert not missing_meta, f"{key}.json: meta missing keys: {missing_meta}"

        # Check module_key matches
        assert data["module_key"] == key, (
            f"{key}.json: module_key={data['module_key']!r} but expected {key!r}"
        )

        # errors must be list
        assert isinstance(data["errors"], list), f"{key}.json: errors must be list"


# ── C9: frontend/mock 与 docs/api_examples 文件存在且结构一致 ─────────────────

def test_C9_frontend_mock_files_exist():
    """C9: frontend/mock/fundamentals/ must have JSON for all available modules."""
    available_keys = [m["key"] for m in _AVAILABLE_MODULES]
    for key in available_keys:
        mock_file = FRONTEND_MOCK_DIR / f"{key}.json"
        assert mock_file.exists(), f"Missing frontend mock: {mock_file}"

    # Also check modules.json and overview.json exist
    assert (FRONTEND_MOCK_DIR / "modules.json").exists(), "Missing frontend/mock/fundamentals/modules.json"
    assert (FRONTEND_MOCK_DIR / "overview.json").exists(), "Missing frontend/mock/fundamentals/overview.json"

    # Check modules.json structure
    modules_data = json.loads((FRONTEND_MOCK_DIR / "modules.json").read_text(encoding="utf-8"))
    assert isinstance(modules_data, list), "modules.json must be a list"
    assert len(modules_data) >= 27, f"modules.json has only {len(modules_data)} entries"

    # Check overview.json structure
    overview_data = json.loads((FRONTEND_MOCK_DIR / "overview.json").read_text(encoding="utf-8"))
    assert "snapshot" in overview_data, "overview.json missing 'snapshot' key"
    assert "financial_summary" in overview_data, "overview.json missing 'financial_summary' key"


# ── C10: build_api_response 返回 meta 字段 ─────────────────────────────────────

def test_C10_build_api_response_returns_meta():
    """C10: build_api_response must return a 'meta' field."""
    envelope = ok_envelope({"foo": "bar"})
    response = build_api_response(
        envelope,
        market="CN",
        symbol="600519",
        ts_code="600519.SH",
        module_key="snapshot",
        module_name="基础信息与行情",
    )
    assert "meta" in response, "build_api_response must return 'meta' field"
    meta = response["meta"]
    assert isinstance(meta, dict), "meta must be a dict"
    for key in _EXPECTED_META_KEYS:
        assert key in meta, f"meta missing key: {key}"


# ── C11: build_api_response errors 永远是 list ─────────────────────────────────

def test_C11_build_api_response_errors_always_list():
    """C11: build_api_response errors field must always be a list, never null."""
    # Success case
    envelope_ok = ok_envelope({"value": 1})
    resp_ok = build_api_response(
        envelope_ok, market="CN", symbol="600519", ts_code="600519.SH",
        module_key="snapshot", module_name="基础信息与行情",
    )
    assert isinstance(resp_ok["errors"], list)
    assert resp_ok["errors"] == []

    # Failure case
    envelope_err = err_envelope("Some error occurred")
    resp_err = build_api_response(
        envelope_err, market="CN", symbol="600519", ts_code="600519.SH",
        module_key="snapshot", module_name="基础信息与行情",
    )
    assert isinstance(resp_err["errors"], list)
    assert len(resp_err["errors"]) == 1
    assert "Some error occurred" in resp_err["errors"][0]


# ── C12: build_api_response meta 永远存在（包括 module_meta=None） ────────────

def test_C12_build_api_response_meta_always_present():
    """C12: meta field must be present even when module_meta=None."""
    envelope = ok_envelope({})
    # With module_meta=None (default)
    resp = build_api_response(
        envelope, market="CN", symbol="600519", ts_code="600519.SH",
        module_key="unknown_key", module_name="未知",
    )
    assert "meta" in resp
    meta = resp["meta"]
    assert meta["render_type"] == "placeholder"
    assert meta["chart_type"] == "none"
    assert isinstance(meta["unit_hints"], dict)
    assert isinstance(meta["field_labels"], dict)
    assert meta["empty_state"] == "暂无数据"

    # With group/group_seq defaults
    assert resp["group"] == ""
    assert resp["group_seq"] == 0


# ── C13: planned 模块 render_type=placeholder ─────────────────────────────────

def test_C13_planned_modules_use_placeholder():
    """C13: Planned modules must have render_type='placeholder' (ai_analysis uses 'ai_card' by design)."""
    # ai_analysis has render_type='ai_card' intentionally as a future slot marker
    EXCLUDED_KEYS = {"ai_analysis"}
    for m in _PLANNED_MODULES:
        if m["key"] in EXCLUDED_KEYS:
            continue
        rt = m.get("render_type")
        assert rt == "placeholder", (
            f"Planned module '{m['key']}' should have render_type='placeholder', got {rt!r}"
        )


# ── C14: analyst_ratings 描述不含误导性词汇 ───────────────────────────────────

def test_C14_analyst_ratings_no_misleading_words():
    """C14: analyst_ratings description must not affirm investment advice.

    The description may contain negations like "不代表投资建议" (disclaims advice)
    but must NOT contain affirmations like "代表投资建议" or "是投资建议".
    It must NOT be labeled as institutional analyst ratings.
    """
    # Words that would be misleading affirmations (NOT disclaimers)
    # Note: "不代表投资建议" is OK (disclaimer); "是投资建议" would NOT be OK
    BANNED_AFFIRMATIONS = ["机构买入", "确定评级", "研究报告评级", "买入推荐", "增持推荐", "是投资建议"]
    analyst_modules = [m for m in MODULE_CATALOG if m["key"] == "analyst_ratings"]
    assert analyst_modules, "analyst_ratings module not found in MODULE_CATALOG"
    m = analyst_modules[0]

    desc = m.get("description", "")
    for word in BANNED_AFFIRMATIONS:
        assert word not in desc, (
            f"analyst_ratings description contains misleading affirmation '{word}': {desc!r}"
        )

    # The description should contain a disclaimer-like word (good sign)
    # Either "非机构" or "不代表" should appear
    has_disclaimer = "非机构" in desc or "不代表" in desc
    assert has_disclaimer, (
        f"analyst_ratings description should contain a disclaimer phrase "
        f"('非机构' or '不代表'), but got: {desc!r}"
    )

    # Also check the name_zh doesn't contain misleading terms
    name = m.get("name_zh", "")
    for word in ["机构评级", "机构买入"]:
        assert word not in name, (
            f"analyst_ratings name_zh contains banned word '{word}': {name!r}"
        )


# ── C15: MODULE_CATALOG display=True 条目总数 >= 27 ──────────────────────────

def test_C15_module_catalog_display_count():
    """C15: MODULE_CATALOG must have at least 27 display=True entries."""
    count = len(_ALL_DISPLAY_MODULES)
    assert count >= 27, (
        f"MODULE_CATALOG has only {count} display=True entries (expected >= 27)"
    )


# ── C16: 每个 available 模块有合法的 data_freshness ──────────────────────────

def test_C16_available_modules_have_valid_data_freshness():
    """C16: All available/legacy modules must have a valid data_freshness value."""
    for m in _AVAILABLE_MODULES:
        df = m.get("data_freshness")
        assert df is not None, f"{m['key']}: missing data_freshness"
        assert df in VALID_DATA_FRESHNESS, (
            f"{m['key']}: invalid data_freshness={df!r}, must be one of {VALID_DATA_FRESHNESS}"
        )


# ── C17: 每个 available 模块有合法的 disclaimer_type ─────────────────────────

def test_C17_available_modules_have_valid_disclaimer_type():
    """C17: All available/legacy modules must have a valid disclaimer_type value."""
    for m in _AVAILABLE_MODULES:
        dt = m.get("disclaimer_type")
        assert dt is not None, f"{m['key']}: missing disclaimer_type"
        assert dt in VALID_DISCLAIMER_TYPES, (
            f"{m['key']}: invalid disclaimer_type={dt!r}, must be one of {VALID_DISCLAIMER_TYPES}"
        )


# ── C18: build_api_response with module_meta 返回正确的 group 和 group_seq ─────

def test_C18_build_api_response_with_module_meta():
    """C18: build_api_response with module_meta must return correct group/group_seq/meta."""
    module_meta = {
        "group": "财务分析",
        "group_seq": 2,
        "render_type": "chart_table",
        "chart_type": "line",
        "unit_hints": {"pe_ttm": "倍"},
        "field_labels": {"pe_ttm": "PE(TTM)"},
    }
    envelope = ok_envelope({"series": []})
    response = build_api_response(
        envelope,
        market="CN",
        symbol="600519",
        ts_code="600519.SH",
        module_key="valuation",
        module_name="估值分位",
        module_meta=module_meta,
    )
    assert response["group"] == "财务分析"
    assert response["group_seq"] == 2
    meta = response["meta"]
    assert meta["render_type"] == "chart_table"
    assert meta["chart_type"] == "line"
    assert meta["unit_hints"] == {"pe_ttm": "倍"}
    assert meta["field_labels"] == {"pe_ttm": "PE(TTM)"}
    assert meta["empty_state"] == "暂无数据"
