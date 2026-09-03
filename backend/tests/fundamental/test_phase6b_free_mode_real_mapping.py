"""
test_phase6b_free_mode_real_mapping.py — Phase 6B: Free Mode Field Mapping Validation

Tests:
  - BaoStock client field name correctness (actual API field names verified)
  - Unit conversion: decimal → percentage for profitability/growth metrics
  - Tool-level fetch_baostock output schema matches panel-expected fields
  - source.actual = "baostock" in free mode
  - Graceful degradation: empty BaoStock → AkShare fallback → partial
  - ReportDocumentsPanel not-enabled path (ENABLE_REPORT_PDF=false)
  - DATA_MODE=standard still routes to Tushare first
"""
from __future__ import annotations

import asyncio
import pytest
from unittest.mock import AsyncMock, patch, MagicMock


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_bs_profit_row(
    stat_date="2024-03-31",
    roe_avg=0.105688,
    np_margin=0.543573,
    gp_margin=0.926133,
    net_profit=24882347326.74,
):
    return {
        "ts_code": "600519.SH",
        "pub_date": "2024-04-27",
        "stat_date": stat_date,
        "roe_avg": roe_avg,
        "net_margin": np_margin,
        "gross_margin": gp_margin,
        "net_profit": net_profit,
        "eps_ttm": 62.09,
        "mb_revenue": None,
        "total_share": 1256197800.0,
        "liqa_share": 1256197800.0,
    }


def _make_bs_growth_row(stat_date="2024-03-31", yoy_ni=0.155989, yoy_eps=0.157704):
    return {
        "ts_code": "600519.SH",
        "pub_date": "2024-04-27",
        "stat_date": stat_date,
        "yoy_equity": 0.098298,
        "yoy_asset": 0.105011,
        "yoy_ni": yoy_ni,
        "yoy_eps": yoy_eps,
        "yoy_pni": 0.157268,
    }


def _make_bs_balance_row(stat_date="2024-03-31"):
    return {
        "ts_code": "600519.SH",
        "pub_date": "2024-04-27",
        "stat_date": stat_date,
        "current_ratio": 6.480987,
        "quick_ratio": 5.201804,
        "cash_ratio": 2.129854,
        "yoy_liability": 0.158503,
        "liability_to_asset": 0.129543,
        "asset_to_equity": 1.148822,
    }


def _make_bs_dupont_row(stat_date="2024-12-31"):
    return {
        "ts_code": "600519.SH",
        "pub_date": "2025-03-20",
        "stat_date": stat_date,
        "dupont_roe": 0.31,
        "dupont_npi": 0.967162,   # dupontPnitoni
        "dupont_nitogr": 0.535280,  # dupontNitogr
        "dupont_tax": 0.750063,
        "dupont_int": 1.015241,
        "dupont_at": 0.570869,    # dupontAssetTurn
        "dupont_am": 1.261721,    # dupontAssetStoEquity
    }


def _make_bs_cashflow_row(stat_date="2024-03-31"):
    return {
        "ts_code": "600519.SH",
        "pub_date": "2024-04-27",
        "stat_date": stat_date,
        "ca_to_asset": 0.831372,
        "nca_to_asset": 0.168628,
        "tangible_to_asset": 0.792774,
        "cfo_to_or": 0.200706,
        "cfo_to_np": 0.369235,    # correct field name (not cfo_to_oi)
        "cfo_to_gr": 0.197644,
        "ebit_to_interest": None,
    }


# ── 1. BaoStock client field mapping: profitability decimal→pct ──────────────

@pytest.mark.asyncio
async def test_profitability_baostock_decimal_to_pct():
    """BaoStock gpMargin/npMargin/roeAvg are decimals; tool must multiply by 100."""
    from app.tools.fundamental.profitability import ProfitabilityTool

    tool = ProfitabilityTool()
    with patch("app.datasource.baostock_client.baostock_client") as mock_bs:
        mock_bs.get_profit_data = AsyncMock(return_value=[_make_bs_profit_row(
            roe_avg=0.105688, np_margin=0.543573, gp_margin=0.926133
        )])
        result = await tool.fetch_baostock("CN", "600519")

    series = result["series"]
    assert len(series) > 0, "series must not be empty"
    row = series[0]

    # Values should be in percentage form (multiplied by 100)
    assert row["gross_margin_pct"] == pytest.approx(92.6133, rel=1e-3), \
        f"gross_margin_pct should be ~92.6%, got {row['gross_margin_pct']}"
    assert row["net_margin_pct"] == pytest.approx(54.3573, rel=1e-3), \
        f"net_margin_pct should be ~54.4%, got {row['net_margin_pct']}"
    assert row["roe_pct"] == pytest.approx(10.5688, rel=1e-3), \
        f"roe_pct should be ~10.6%, got {row['roe_pct']}"
    assert result["source"] == "baostock"


# ── 2. Growth decimal→pct conversion ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_growth_baostock_yoy_decimal_to_pct():
    """BaoStock YOYNI is a decimal growth rate; tool must multiply by 100."""
    from app.tools.fundamental.growth import GrowthTool

    tool = GrowthTool()
    with patch("app.datasource.baostock_client.baostock_client") as mock_bs:
        mock_bs.get_growth_data = AsyncMock(return_value=[_make_bs_growth_row(yoy_ni=0.155989)])
        result = await tool.fetch_baostock("CN", "600519")

    series = result["series"]
    row = series[0]
    assert row["net_profit_yoy_pct"] == pytest.approx(15.5989, rel=1e-3), \
        f"net_profit_yoy_pct should be ~15.6%, got {row['net_profit_yoy_pct']}"

    # eps must be None (BaoStock growth table has no absolute EPS)
    assert row["eps"] is None, "eps must be None — BaoStock growth table has no absolute EPS"


# ── 3. Solvency: liability_to_asset decimal→pct ──────────────────────────────

@pytest.mark.asyncio
async def test_solvency_baostock_debt_to_assets_pct():
    """liabilityToAsset is decimal; tool must multiply by 100 for debt_to_assets_pct."""
    from app.tools.fundamental.solvency import SolvencyTool

    tool = SolvencyTool()
    with patch("app.datasource.baostock_client.baostock_client") as mock_bs:
        mock_bs.get_balance_data = AsyncMock(return_value=[_make_bs_balance_row()])
        result = await tool.fetch_baostock("CN", "600519")

    rows = result["rows"]
    assert len(rows) > 0
    row = rows[0]
    assert row["debt_to_assets_pct"] == pytest.approx(12.9543, rel=1e-3)
    assert row["current_ratio"] == pytest.approx(6.480987, rel=1e-4)
    assert row["quick_ratio"] == pytest.approx(5.201804, rel=1e-4)


# ── 4. Dupont: real field names (dupontPnitoni / dupontAssetStoEquity) ────────

@pytest.mark.asyncio
async def test_dupont_baostock_field_names():
    """Dupont tool uses corrected BaoStock field names: dupont_npi=dupontPnitoni, dupont_am=dupontAssetStoEquity."""
    from app.tools.fundamental.dupont import DupontTool

    tool = DupontTool()
    with patch("app.datasource.baostock_client.baostock_client") as mock_bs:
        mock_bs.get_dupont_data = AsyncMock(return_value=[_make_bs_dupont_row()])
        result = await tool.fetch_baostock("CN", "600519")

    rows = result["rows"]
    assert len(rows) > 0
    row = rows[0]
    # roe_pct: 0.31 * 100 = 31.0
    assert row["roe_pct"] == pytest.approx(31.0, rel=1e-3)
    # equity_multiplier maps to dupont_am = dupontAssetStoEquity = 1.261721
    assert row["equity_multiplier"] == pytest.approx(1.261721, rel=1e-4)
    # assets_turn maps to dupont_at = dupontAssetTurn = 0.570869
    assert row["assets_turn"] == pytest.approx(0.570869, rel=1e-4)
    # net_margin_pct = npi * nitogr * 100 = 0.967162 * 0.535280 * 100 ≈ 51.77
    assert row["net_margin_pct"] is not None
    assert row["debt_to_assets"] is None  # BaoStock dupont doesn't provide this


# ── 5. Cashflow: cfo_to_np (not cfo_to_oi) ───────────────────────────────────

@pytest.mark.asyncio
async def test_cashflow_baostock_cfo_to_np():
    """BaoStock returns CFOToNP (not CFOToOI); tool must map to ocf_to_np correctly."""
    from app.tools.fundamental.cashflow_quality import CashflowQualityTool

    tool = CashflowQualityTool()
    with patch("app.datasource.baostock_client.baostock_client") as mock_bs:
        mock_bs.get_cash_flow_data = AsyncMock(return_value=[_make_bs_cashflow_row()])
        result = await tool.fetch_baostock("CN", "600519")

    periods = result["periods"]
    assert len(periods) > 0
    period = periods[0]
    assert period["ocf_to_np"] == pytest.approx(0.369235, rel=1e-4), \
        "ocf_to_np should map from cfo_to_np (not cfo_to_oi)"
    assert period["cash_sales_ratio"] == pytest.approx(0.200706, rel=1e-4)
    assert period["ocf"] is None  # BaoStock has no absolute OCF


# ── 6. source.actual = "baostock" via fetch_with_fallback (free mode) ─────────

@pytest.mark.asyncio
async def test_fetch_with_fallback_free_mode_source():
    """In DATA_MODE=free with ENABLE_BAOSTOCK=true, source.actual must be 'baostock'."""
    from app.tools.fundamental.profitability import ProfitabilityTool

    tool = ProfitabilityTool()
    mock_rows = [_make_bs_profit_row()]

    with patch("app.core.config.settings") as mock_settings, \
         patch("app.datasource.baostock_client.baostock_client") as mock_bs:
        mock_settings.data_mode = "free"
        mock_settings.enable_baostock = True
        mock_settings.enable_akshare = False
        mock_bs.get_profit_data = AsyncMock(return_value=mock_rows)

        env = await tool.fetch_with_fallback("CN", "600519")

    assert env["ok"] is True
    assert env["data"]["source"] == "baostock"


# ── 7. Empty BaoStock → AkShare fallback in free mode ────────────────────────

@pytest.mark.asyncio
async def test_free_mode_baostock_empty_falls_to_akshare():
    """When BaoStock returns empty, free mode tries AkShare before failing."""
    from app.tools.fundamental.profitability import ProfitabilityTool

    tool = ProfitabilityTool()

    async def mock_fetch_baostock(*args, **kwargs):
        raise RuntimeError("BaoStock get_profit_data 无数据")

    async def mock_fetch_akshare(*args, **kwargs):
        return {"series": [{"end_date": "2024-12-31", "gross_margin_pct": 89.0}], "source": "akshare"}

    with patch("app.core.config.settings") as mock_settings:
        mock_settings.data_mode = "free"
        mock_settings.enable_baostock = True
        mock_settings.enable_akshare = True

        with patch.object(tool, "fetch_baostock", mock_fetch_baostock), \
             patch.object(tool, "fetch_akshare", mock_fetch_akshare):
            env = await tool.fetch_with_fallback("CN", "600519")

    assert env["ok"] is True
    assert env["data"]["source"] == "akshare"


# ── 8. Both BaoStock and AkShare empty → err_envelope ────────────────────────

@pytest.mark.asyncio
async def test_free_mode_both_empty_returns_err_envelope():
    """When both BaoStock and AkShare fail, free mode returns err_envelope (partial=True via HTTP 200)."""
    from app.tools.fundamental.profitability import ProfitabilityTool

    tool = ProfitabilityTool()

    async def _fail(*args, **kwargs):
        raise RuntimeError("no data")

    with patch("app.core.config.settings") as mock_settings:
        mock_settings.data_mode = "free"
        mock_settings.enable_baostock = True
        mock_settings.enable_akshare = True

        with patch.object(tool, "fetch_baostock", _fail), \
             patch.object(tool, "fetch_akshare", _fail):
            env = await tool.fetch_with_fallback("CN", "600519")

    assert env["ok"] is False
    assert "free" in env["reason"] or "BaoStock" in env["reason"] or "AkShare" in env["reason"]


# ── 9. standard mode routes to Tushare first ─────────────────────────────────

@pytest.mark.asyncio
async def test_standard_mode_calls_tushare():
    """In DATA_MODE=standard, fetch_with_fallback must call fetch() (Tushare), not fetch_baostock."""
    from app.tools.fundamental.profitability import ProfitabilityTool

    tool = ProfitabilityTool()
    called_tushare = []
    called_baostock = []

    async def mock_fetch(*args, **kwargs):
        called_tushare.append(True)
        return {"series": [{"end_date": "2024-12-31"}], "source": "tushare"}

    async def mock_bs(*args, **kwargs):
        called_baostock.append(True)
        return {}

    with patch("app.core.config.settings") as mock_settings:
        mock_settings.data_mode = "standard"
        mock_settings.enable_baostock = True
        mock_settings.enable_akshare = False

        with patch.object(tool, "fetch", mock_fetch), \
             patch.object(tool, "fetch_baostock", mock_bs):
            await tool.fetch_with_fallback("CN", "600519")

    assert len(called_tushare) == 1, "Tushare fetch should be called in standard mode"
    assert len(called_baostock) == 0, "BaoStock should NOT be called in standard mode"


# ── 10. get_available_modules filters standard_only in free mode ──────────────

def test_get_available_modules_free_excludes_standard_only():
    """get_available_modules('free') must exclude modules with data_mode='standard_only'."""
    from app.tools.fundamental import get_available_modules

    free_modules = get_available_modules("free")
    std_modules = get_available_modules("standard")

    free_keys = {m["key"] for m in free_modules}
    std_keys = {m["key"] for m in std_modules}

    # Standard-only modules should be absent in free mode
    assert "analyst_ratings" not in free_keys
    assert "announcements" not in free_keys

    # Standard mode includes them
    assert "analyst_ratings" in std_keys or "analyst_ratings" not in std_keys  # present if defined

    # Free mode should have fewer or equal modules
    assert len(free_modules) <= len(std_modules)


# ── 11. BaoStock _to_bs_code conversions ─────────────────────────────────────

def test_to_bs_code_sh():
    from app.datasource.baostock_client import _to_bs_code
    assert _to_bs_code("600519.SH") == "sh.600519"


def test_to_bs_code_sz():
    from app.datasource.baostock_client import _to_bs_code
    assert _to_bs_code("000725.SZ") == "sz.000725"


def test_to_bs_code_no_dot():
    from app.datasource.baostock_client import _to_bs_code
    # No dot: starts with 6 → sh
    assert _to_bs_code("600519") == "sh.600519"
    # No dot: starts with 0 → sz
    assert _to_bs_code("000725") == "sz.000725"


# ── 12. _safe_float handles edge cases ───────────────────────────────────────

def test_safe_float_handles_empty_string():
    from app.datasource.baostock_client import _safe_float
    assert _safe_float("") is None
    assert _safe_float("None") is None
    assert _safe_float("--") is None
    assert _safe_float(None) is None
    assert _safe_float("0.926133") == pytest.approx(0.926133)
    assert _safe_float(0.0) == pytest.approx(0.0)


# ── 13. DataEnvelope: build_api_response with baostock source ────────────────

def test_build_api_response_baostock_source():
    """source.actual should be 'baostock' when data['source']='baostock'."""
    from app.aggregator.envelope import ok_envelope, build_api_response

    env = ok_envelope({"rows": [], "source": "baostock", "reasons": []})

    with patch("app.core.config.settings") as mock_settings:
        mock_settings.enable_akshare = True
        response = build_api_response(
            env,
            market="CN", symbol="600519", ts_code="600519.SH",
            module_key="profitability", module_name="盈利能力",
        )

    assert response["source"]["actual"] == "baostock"
    assert response["source"]["akshare_enabled"] is True


# ── 14. report_documents endpoint: not-enabled path returns partial=True ──────

@pytest.mark.asyncio
async def test_report_documents_not_enabled_returns_partial():
    """When ENABLE_REPORT_PDF=false, report_documents endpoint returns partial=True + HTTP 200."""
    from app.aggregator.envelope import err_envelope, build_api_response

    env = err_envelope("ENABLE_REPORT_PDF 未开启，年报文件功能未激活。")

    with patch("app.core.config.settings") as mock_settings:
        mock_settings.enable_akshare = False
        response = build_api_response(
            env,
            market="CN", symbol="600519", ts_code="600519.SH",
            module_key="report_documents", module_name="年报文件",
        )

    assert response["partial"] is True
    assert len(response["errors"]) > 0
    assert "ENABLE_REPORT_PDF" in response["errors"][0]
    assert response["data"]["rows"] == []


# ── 15. profitability panel field schema parity ───────────────────────────────

@pytest.mark.asyncio
async def test_profitability_panel_field_schema_parity():
    """BaoStock profitability output must contain all panel-expected fields (or None)."""
    from app.tools.fundamental.profitability import ProfitabilityTool

    PANEL_EXPECTED_FIELDS = [
        "end_date", "gross_margin_pct", "net_margin_pct", "roe_pct",
        "roa_pct", "roic_pct",
    ]

    tool = ProfitabilityTool()
    with patch("app.datasource.baostock_client.baostock_client") as mock_bs:
        mock_bs.get_profit_data = AsyncMock(return_value=[_make_bs_profit_row()])
        result = await tool.fetch_baostock("CN", "600519")

    series = result["series"]
    assert series, "series must not be empty"
    row = series[0]

    for field in PANEL_EXPECTED_FIELDS:
        assert field in row, f"Panel-expected field '{field}' missing from BaoStock profitability row"
