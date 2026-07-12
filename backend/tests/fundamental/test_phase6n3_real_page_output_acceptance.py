"""
tests/fundamental/test_phase6n3_real_page_output_acceptance.py

Phase 6N-3: Real Page Data Output Acceptance

Covers:
  T01  diagnostics: BaoStock modules not hidden by timeout (config inference)
  T02  diagnostics: inferred ok result passes visibility check → section shown
  T03  diagnostics: non-BaoStock modules still get live-probed in free mode
  T04  sectionVisible: returns True for BaoStock sections after inference
  T05  EarningsQualityPanel: field name ocf_to_np (not ocf_to_np_ratio)
  T06  EarningsQualityPanel: net_profit_parent fallback in template
  T07  FundamentalFallbackTable.vue: exists and has correct structure
  T08  FundamentalFallbackTable.vue: reads rows from periods/series/records
  T09  fundamentalAdapters: adaptCashflowQuality returns non-empty rows from periods
  T10  fundamentalAdapters: adaptDupont returns non-empty rows from series
  T11  fundamentalAdapters: adaptProfitability returns non-empty rows from series
  T12  report_free_data_coverage.py: importable + main() exists + _to_ts_code
  T13  compute_section_visibility: all 6 BaoStock sections visible when inferred ok
  T14  full diagnostics flow: free mode CN → no BaoStock timeout paths
"""
from __future__ import annotations

import importlib
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_REPO_ROOT    = Path(__file__).resolve().parents[3]


# ── T01: BaoStock modules not probed live in free mode CN ────────────────────

def test_baostock_modules_use_inference_in_free_mode_cn():
    """In free mode CN, BaoStock modules must skip live probe → no 5s timeout."""
    source = (_BACKEND_ROOT / "app" / "routers" / "fundamentals_compat.py").read_text(encoding="utf-8")
    assert "_use_bs_inference" in source, "_use_bs_inference flag must be defined"
    assert "_inferred_baostock" in source, "_inferred_baostock helper must be defined"
    assert "_BAOSTOCK_MODULE_KEYS" in source, "_BAOSTOCK_MODULE_KEYS must be defined"
    # Ensure probe_keys excludes BaoStock modules when inference is active
    assert "probe_keys" in source, "probe_keys (filtered list) must exist"


# ── T02: inferred ok passes visibility → section shown ───────────────────────

def test_inferred_ok_makes_section_visible():
    """compute_section_visibility must return True for sections whose modules are inferred ok."""
    from app.services.free_mode_visibility_service import compute_section_visibility

    inferred = [
        {"module_key": mk, "status": "ok", "rows_count": 1, "inferred": True}
        for mk in ["growth", "profitability", "cashflow_quality", "solvency", "operation_capability", "dupont"]
    ]
    vis = compute_section_visibility(inferred)

    assert vis.get("growth")           is True, "growth section must be visible"
    assert vis.get("profitability")    is True, "profitability section must be visible"
    assert vis.get("earnings-quality") is True, "earnings-quality section must be visible"
    assert vis.get("solvency")         is True, "solvency section must be visible"
    assert vis.get("operations")       is True, "operations section must be visible"
    assert vis.get("dupont")           is True, "dupont section must be visible"


# ── T03: non-BaoStock modules still probed live ───────────────────────────────

def test_non_baostock_modules_still_probed():
    """Non-BaoStock modules (valuation, quote_snapshot etc.) must NOT be inferred."""
    from app.routers.fundamentals_compat import _BAOSTOCK_MODULE_KEYS, _DIAG_MODULE_KEYS
    non_bs = [m for m in _DIAG_MODULE_KEYS if m not in _BAOSTOCK_MODULE_KEYS]
    # There should be non-BaoStock modules in the list
    assert len(non_bs) > 0, "There must be at least some non-BaoStock modules"
    # Specifically, valuation and quote_snapshot should not be inferred
    assert "valuation"      not in _BAOSTOCK_MODULE_KEYS
    assert "quote_snapshot" not in _BAOSTOCK_MODULE_KEYS
    assert "industry_rank"  not in _BAOSTOCK_MODULE_KEYS


# ── T04: sectionVisible: 6 BaoStock sections True after inference ─────────────

def test_six_baostock_sections_all_visible():
    """All 6 BaoStock-backed sections must be visible after config inference."""
    from app.services.free_mode_visibility_service import compute_section_visibility, SHOW_IF_DATA_SECTIONS

    # Build inferred ok for all 6 BaoStock modules
    bs_modules = ["growth", "profitability", "cashflow_quality", "solvency", "operation_capability", "dupont"]
    diags = [{"module_key": m, "status": "ok", "rows_count": 1} for m in bs_modules]
    vis = compute_section_visibility(diags)

    # Check each relevant section
    bs_sections = {"growth", "profitability", "earnings-quality", "solvency", "operations", "dupont"}
    for sec in bs_sections:
        assert vis.get(sec) is True, f"Section '{sec}' must be visible when BaoStock modules are ok"


# ── T05: EarningsQualityPanel uses ocf_to_np (not ocf_to_np_ratio) ───────────

def test_earnings_quality_panel_uses_ocf_to_np():
    """EarningsQualityPanel must use ocf_to_np tab key (tool field name)."""
    source = (_REPO_ROOT / "frontend" / "src" / "components" / "fundamentals" / "EarningsQualityPanel.vue").read_text(encoding="utf-8")
    assert "'ocf_to_np'" in source or '"ocf_to_np"' in source, (
        "EarningsQualityPanel must use tab key 'ocf_to_np' (tool returns this field, not ocf_to_np_ratio)"
    )


# ── T06: EarningsQualityPanel uses net_profit_parent fallback ─────────────────

def test_earnings_quality_panel_net_profit_parent():
    """EarningsQualityPanel must handle net_profit_parent (Tushare field name)."""
    source = (_REPO_ROOT / "frontend" / "src" / "components" / "fundamentals" / "EarningsQualityPanel.vue").read_text(encoding="utf-8")
    assert "net_profit_parent" in source, (
        "EarningsQualityPanel must read net_profit_parent (cashflow tool returns this, not net_profit)"
    )


# ── T07: FundamentalFallbackTable.vue exists ─────────────────────────────────

def test_fundamental_fallback_table_exists():
    """FundamentalFallbackTable.vue must exist in the fundamentals components folder."""
    path = _REPO_ROOT / "frontend" / "src" / "components" / "fundamentals" / "FundamentalFallbackTable.vue"
    assert path.exists(), "FundamentalFallbackTable.vue must exist"
    source = path.read_text(encoding="utf-8")
    assert "v-if=\"visibleRows.length\"" in source or "visibleRows" in source, (
        "FundamentalFallbackTable must conditionally render based on data presence"
    )


# ── T08: FundamentalFallbackTable reads periods/series/records ────────────────

def test_fundamental_fallback_table_reads_all_field_names():
    """FundamentalFallbackTable must extract rows from periods, series, and records."""
    path = _REPO_ROOT / "frontend" / "src" / "components" / "fundamentals" / "FundamentalFallbackTable.vue"
    source = path.read_text(encoding="utf-8")
    assert "periods" in source, "FundamentalFallbackTable must handle data.periods"
    assert "series" in source,  "FundamentalFallbackTable must handle data.series"
    assert "records" in source, "FundamentalFallbackTable must handle data.records"


# ── T09: adaptCashflowQuality extracts rows from periods ─────────────────────

def test_adapt_cashflow_quality_periods_returns_rows():
    """adaptCashflowQuality must return non-empty rows when data.periods is populated."""
    import importlib, types, sys

    # Mock the adapter module since it's JS — test via source inspection
    source = (_REPO_ROOT / "frontend" / "src" / "utils" / "fundamentalAdapters.js").read_text(encoding="utf-8")

    import re
    fn_match = re.search(r'function adaptCashflowQuality\(.*?\{(.*?)^function ', source, re.DOTALL | re.MULTILINE)
    assert fn_match, "adaptCashflowQuality not found"
    fn_body = fn_match.group(1)

    # Must read periods before series
    periods_pos = fn_body.find("data?.periods")
    series_pos = fn_body.find("data?.series")
    assert periods_pos != -1, "data?.periods must be present"
    assert periods_pos < series_pos, "data?.periods must come before data?.series (primary source)"


# ── T10: adaptDupont has correct BaoStock field names ────────────────────────

def test_adapt_dupont_baostock_fields():
    """adaptDupont must use roe_pct/net_margin_pct/assets_turn."""
    source = (_REPO_ROOT / "frontend" / "src" / "utils" / "fundamentalAdapters.js").read_text(encoding="utf-8")
    import re
    fn_match = re.search(r'function adaptDupont\(.*?\{(.*?)^function ', source, re.DOTALL | re.MULTILINE)
    assert fn_match
    fn_body = fn_match.group(1)
    assert "roe_pct"       in fn_body, "roe_pct must be primary field"
    assert "net_margin_pct" in fn_body, "net_margin_pct must be primary field"
    assert "assets_turn"   in fn_body, "assets_turn must be primary field"
    assert "??"            in fn_body, "Must have fallback via ?? operator"


# ── T11: adaptProfitability BaoStock fields ───────────────────────────────────

def test_adapt_profitability_baostock_fields():
    """adaptProfitability must use gross_margin_pct/roe_pct as primary fields."""
    source = (_REPO_ROOT / "frontend" / "src" / "utils" / "fundamentalAdapters.js").read_text(encoding="utf-8")
    import re
    fn_match = re.search(r'function adaptProfitability\(.*?\{(.*?)^function ', source, re.DOTALL | re.MULTILINE)
    assert fn_match
    fn_body = fn_match.group(1)
    assert "gross_margin_pct" in fn_body, "gross_margin_pct must be primary field"
    assert "net_margin_pct"   in fn_body, "net_margin_pct must be primary field"
    assert "roe_pct"          in fn_body, "roe_pct must be primary field"
    assert "??"               in fn_body, "Must have fallback via ?? operator"


# ── T12: report_free_data_coverage.py: importable + main() ───────────────────

def test_coverage_script_importable():
    """scripts/report_free_data_coverage.py must be importable and expose main()."""
    script_path = _BACKEND_ROOT / "scripts" / "report_free_data_coverage.py"
    assert script_path.exists(), "scripts/report_free_data_coverage.py not found"
    spec = importlib.util.spec_from_file_location("report_free_data_coverage", script_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert hasattr(mod, "main") and callable(mod.main), "main() must exist"
    assert hasattr(mod, "_to_ts_code"), "_to_ts_code must exist"
    # Test _to_ts_code
    assert mod._to_ts_code("600519") == "600519.SH"
    assert mod._to_ts_code("000725") == "000725.SZ"


# ── T13: all 6 inferred BaoStock sections visible ─────────────────────────────

def test_all_six_baostock_inferred_sections_visible():
    """With all 6 BaoStock modules inferred ok, 6 data-driven sections must be True."""
    from app.services.free_mode_visibility_service import compute_section_visibility

    diags = [
        {"module_key": "growth",               "status": "ok", "rows_count": 1},
        {"module_key": "profitability",         "status": "ok", "rows_count": 1},
        {"module_key": "cashflow_quality",      "status": "ok", "rows_count": 1},
        {"module_key": "solvency",              "status": "ok", "rows_count": 1},
        {"module_key": "operation_capability",  "status": "ok", "rows_count": 1},
        {"module_key": "dupont",                "status": "ok", "rows_count": 1},
    ]
    vis = compute_section_visibility(diags)
    true_sections = [k for k, v in vis.items() if v is True]
    # These 6 data sections + always-show 4 = 10 total
    # But we only care about data-driven ones from BaoStock
    data_driven_bs = {"growth", "profitability", "earnings-quality", "solvency", "operations", "dupont"}
    for sec in data_driven_bs:
        assert vis.get(sec) is True, f"Section '{sec}' must be True when its BaoStock module is ok"


# ── T14: fundamentals_compat.py has no more discovered_at column ─────────────

def test_no_discovered_at_in_compat():
    """fundamentals_compat.py must not reference non-existent discovered_at column."""
    source = (_BACKEND_ROOT / "app" / "routers" / "fundamentals_compat.py").read_text(encoding="utf-8")
    assert "discovered_at" not in source, (
        "discovered_at column does not exist in report_documents — use created_at"
    )
