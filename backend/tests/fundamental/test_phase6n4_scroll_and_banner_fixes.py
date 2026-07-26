"""
tests/fundamental/test_phase6n4_scroll_and_banner_fixes.py

Phase 6N-4: Company Tab Scroll Fix + DataSourceBanner Distinction

Covers:
  T01  AnchorNav: .cfan-root must NOT have overflow-y: auto (scroll container trap)
  T02  AnchorNav: .cfan-root must NOT have overflow-y: scroll
  T03  AnchorNav: .cfan-root uses overflow: clip (no scroll container, no wheel trap)
  T04  AnchorNav: mobile media query still has overflow-x: auto (horizontal chips OK)
  T05  AnchorNav: position sticky is preserved (not removed in fix)
  T06  DataSourceBanner: financialDataOk prop is defined
  T07  DataSourceBanner: market_unavailable_financial_ok type returns distinct message
  T08  DataSourceBanner: market_unavailable_financial_ok message mentions BaoStock and AkShare
  T09  DataSourceBanner: dsb-type-info CSS class or variant exists in template
  T10  CompanyFundamentalsPanel: bsFinancialOk computed checks BaoStock sections
  T11  CompanyFundamentalsPanel: DataSourceBanner receives financial-data-ok prop
  T12  CompanyFundamentalsPanel: banner shown when unavailableSections + bsFinancialOk
  T13  RAG script: _probe_db returns rag_status field (not just rag_ready bool)
  T14  RAG script: _probe_db returns rag_status="unknown" when DATABASE_URL not set
"""
from __future__ import annotations

import re
import sys
import importlib
from pathlib import Path
import pytest

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_REPO_ROOT    = Path(__file__).resolve().parents[3]

_ANCHOR_NAV = _REPO_ROOT / "frontend" / "src" / "components" / "fundamentals" / "CompanyFundamentalAnchorNav.vue"
_BANNER     = _REPO_ROOT / "frontend" / "src" / "components" / "fundamentals" / "DataSourceBanner.vue"
_CFP        = _REPO_ROOT / "frontend" / "src" / "components" / "CompanyFundamentalsPanel.vue"
_SCRIPT     = _BACKEND_ROOT / "scripts" / "report_free_data_coverage.py"


# ── T01: AnchorNav must not use overflow-y: auto ─────────────────────────────

def test_anchor_nav_no_overflow_y_auto():
    """overflow-y: auto creates a scroll container that traps wheel events — must not appear."""
    source = _ANCHOR_NAV.read_text(encoding="utf-8")
    # Find the .cfan-root style block (not mobile media query)
    # We allow overflow-x: auto in mobile but not overflow-y: auto anywhere
    lines = source.split("\n")
    in_mobile = False
    for line in lines:
        if "@media" in line and "640px" in line:
            in_mobile = True
        if in_mobile and "}" in line and "@media" not in line:
            in_mobile = False
        if not in_mobile and "overflow-y: auto" in line:
            pytest.fail(
                "CompanyFundamentalAnchorNav.vue must NOT have 'overflow-y: auto' "
                "outside mobile — it creates a scroll container that traps wheel events"
            )


# ── T02: AnchorNav must not use overflow-y: scroll ───────────────────────────

def test_anchor_nav_no_overflow_y_scroll():
    """overflow-y: scroll also creates a scroll container — must not appear in desktop styles."""
    source = _ANCHOR_NAV.read_text(encoding="utf-8")
    lines = source.split("\n")
    in_mobile = False
    for line in lines:
        if "@media" in line and "640px" in line:
            in_mobile = True
        if in_mobile and "}" in line and "@media" not in line:
            in_mobile = False
        if not in_mobile and "overflow-y: scroll" in line:
            pytest.fail("CompanyFundamentalAnchorNav.vue must NOT use 'overflow-y: scroll' outside mobile")


# ── T03: AnchorNav uses overflow: clip ────────────────────────────────────────

def test_anchor_nav_uses_overflow_clip():
    """overflow: clip must be used — it doesn't create a scroll container."""
    source = _ANCHOR_NAV.read_text(encoding="utf-8")
    assert "overflow: clip" in source, (
        "CompanyFundamentalAnchorNav.vue must use 'overflow: clip' on .cfan-root "
        "to avoid scroll-container creation while keeping sticky behaviour"
    )


# ── T04: Mobile media query still has horizontal scroll ──────────────────────

def test_anchor_nav_mobile_has_overflow_x_auto():
    """Mobile chips need overflow-x: auto for horizontal scrolling — must still be present."""
    source = _ANCHOR_NAV.read_text(encoding="utf-8")
    # Find inside @media block
    mobile_match = re.search(r'@media[^{]*640px[^{]*\{(.*?)(?=^})', source, re.DOTALL | re.MULTILINE)
    assert mobile_match, "@media (max-width: 640px) block not found"
    mobile_css = mobile_match.group(1)
    assert "overflow-x: auto" in mobile_css, "Mobile media query must keep overflow-x: auto for chip scrolling"


# ── T05: position sticky preserved ───────────────────────────────────────────

def test_anchor_nav_sticky_preserved():
    """position: sticky on .cfan-root must still be present after the fix."""
    source = _ANCHOR_NAV.read_text(encoding="utf-8")
    assert "position: sticky" in source, ".cfan-root must still have position: sticky"


# ── T06: DataSourceBanner has financialDataOk prop ───────────────────────────

def test_datasource_banner_financial_data_ok_prop():
    """DataSourceBanner must declare a financialDataOk Boolean prop."""
    source = _BANNER.read_text(encoding="utf-8")
    assert "financialDataOk" in source, "DataSourceBanner must declare financialDataOk prop"
    assert "Boolean" in source, "financialDataOk prop must be typed Boolean"


# ── T07: market_unavailable_financial_ok type returns distinct message ────────

def test_datasource_banner_market_unavailable_type_exists():
    """DataSourceBanner must handle market_unavailable_financial_ok type in typeMsg."""
    source = _BANNER.read_text(encoding="utf-8")
    assert "market_unavailable_financial_ok" in source, (
        "DataSourceBanner must define 'market_unavailable_financial_ok' banner type"
    )


# ── T08: market_unavailable message mentions BaoStock and AkShare ─────────────

def test_datasource_banner_market_unavailable_message_content():
    """The market_unavailable_financial_ok message must mention BaoStock (OK) and AkShare (limited)."""
    source = _BANNER.read_text(encoding="utf-8")
    # Find the typeMsg function body
    fn_match = re.search(r'function typeMsg\(type\)(.*?)^}', source, re.DOTALL | re.MULTILINE)
    assert fn_match, "typeMsg function not found"
    fn_body = fn_match.group(1)
    # Find the market_unavailable_financial_ok branch
    mkt_match = re.search(r"market_unavailable_financial_ok.*?return\s+'([^']+)'", fn_body, re.DOTALL)
    if not mkt_match:
        mkt_match = re.search(r'market_unavailable_financial_ok.*?return\s+"([^"]+)"', fn_body, re.DOTALL)
    assert mkt_match, "typeMsg must have a return value for market_unavailable_financial_ok"
    msg = mkt_match.group(1)
    assert "BaoStock" in msg, "market_unavailable_financial_ok message must mention BaoStock"
    assert "AkShare" in msg, "market_unavailable_financial_ok message must mention AkShare"


# ── T09: dsb-type-info marker present in template ────────────────────────────

def test_datasource_banner_info_marker_in_template():
    """DataSourceBanner template must mark market_unavailable rows with info class."""
    source = _BANNER.read_text(encoding="utf-8")
    assert "dsb-type-info" in source, (
        "DataSourceBanner must use 'dsb-type-info' CSS class marker for info-level rows "
        "(used by :has() selector to recolour the banner)"
    )


# ── T10: CompanyFundamentalsPanel has bsFinancialOk computed ─────────────────

def test_cfp_bs_financial_ok_computed():
    """CompanyFundamentalsPanel must compute bsFinancialOk from BaoStock section visibility."""
    source = _CFP.read_text(encoding="utf-8")
    assert "bsFinancialOk" in source, "CompanyFundamentalsPanel must define bsFinancialOk computed"
    # It should check BaoStock-backed sections
    assert "growth" in source and "profitability" in source and "solvency" in source, (
        "bsFinancialOk must reference BaoStock sections like growth/profitability/solvency"
    )


# ── T11: DataSourceBanner receives financial-data-ok prop ─────────────────────

def test_cfp_banner_receives_financial_data_ok():
    """CompanyFundamentalsPanel must pass :financial-data-ok to DataSourceBanner."""
    source = _CFP.read_text(encoding="utf-8")
    assert "financial-data-ok" in source or "financialDataOk" in source, (
        "CompanyFundamentalsPanel must pass financial-data-ok prop to DataSourceBanner"
    )


# ── T12: Banner shown when unavailableSections + bsFinancialOk ───────────────

def test_cfp_banner_shown_for_unavailable_sections():
    """DataSourceBanner v-if must also trigger when unavailableSections > 0 and bsFinancialOk."""
    source = _CFP.read_text(encoding="utf-8")
    # The v-if on DataSourceBanner should reference both unavailableSections and bsFinancialOk
    assert "unavailableSections" in source, "DataSourceBanner v-if must reference unavailableSections"
    assert "bsFinancialOk" in source, "DataSourceBanner v-if must reference bsFinancialOk"


# ── T13: RAG script returns rag_status field ──────────────────────────────────

def test_rag_script_returns_rag_status():
    """_probe_db in the coverage script must return a rag_status field."""
    source = _SCRIPT.read_text(encoding="utf-8")
    assert '"rag_status"' in source or "'rag_status'" in source, (
        "report_free_data_coverage.py _probe_db must return 'rag_status' field"
    )


# ── T14: rag_status is unknown when DATABASE_URL not set ─────────────────────

def test_rag_script_unknown_when_no_db_url():
    """_probe_db must return rag_status='unknown' (not rag_ready=False=0) when DB is unreachable."""
    source = _SCRIPT.read_text(encoding="utf-8")
    # Find _probe_db function
    fn_match = re.search(r'async def _probe_db.*?(?=^async def |\Z)', source, re.DOTALL | re.MULTILINE)
    assert fn_match, "_probe_db function not found"
    fn_body = fn_match.group(0)
    assert '"unknown"' in fn_body or "'unknown'" in fn_body, (
        "_probe_db must set rag_status='unknown' when DATABASE_URL is not set or DB is unreachable"
    )
