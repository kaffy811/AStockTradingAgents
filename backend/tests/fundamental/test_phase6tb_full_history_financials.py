"""
backend/tests/fundamental/test_phase6tb_full_history_financials.py
Phase 6T-B: Full-History Financial Data 验收测试
"""
from __future__ import annotations

import pytest


# ── History Financial Provider 测试 ─────────────────────────────────────────

def test_history_provider_import():
    """history_financial_provider 模块可正常导入。"""
    from app.datasource.history_financial_provider import (
        fetch_module_history,
        fetch_all_modules_history,
        _MODULE_BAOSTOCK_TABLE,
        _CHART_CONTRACTS,
    )
    assert "profitability" in _MODULE_BAOSTOCK_TABLE
    assert "growth" in _MODULE_BAOSTOCK_TABLE
    assert "cashflow_quality" in _MODULE_BAOSTOCK_TABLE
    assert "solvency" in _MODULE_BAOSTOCK_TABLE
    assert "operation_capability" in _MODULE_BAOSTOCK_TABLE
    assert "dupont" in _MODULE_BAOSTOCK_TABLE
    assert "profitability" in _CHART_CONTRACTS


def test_detect_period_type_annual():
    """_detect_period_type 能识别年度数据。"""
    from app.datasource.history_financial_provider import _detect_period_type
    rows = [
        {"period": "2020-12-31"},
        {"period": "2021-12-31"},
        {"period": "2022-12-31"},
    ]
    assert _detect_period_type(rows) == "annual"


def test_detect_period_type_quarterly():
    """_detect_period_type 能识别季度数据。"""
    from app.datasource.history_financial_provider import _detect_period_type
    rows = [
        {"period": "2022-03-31"},
        {"period": "2022-06-30"},
        {"period": "2022-09-30"},
        {"period": "2022-12-31"},
    ]
    assert _detect_period_type(rows) == "quarterly"


def test_all_quarters_from_year():
    """_all_quarters_from_year 从指定年份生成所有季度。"""
    from app.datasource.history_financial_provider import _all_quarters_from_year
    quarters = _all_quarters_from_year(2020)
    assert len(quarters) >= 24   # 2020 年以来至少 6 年 * 4 季度
    # 验证格式
    for year, quarter in quarters:
        assert isinstance(year, int)
        assert quarter in (1, 2, 3, 4)
    # 验证降序
    assert quarters[0][0] >= quarters[-1][0]


def test_history_coverage_computation():
    """_compute_history_coverage 正确计算覆盖情况。"""
    from app.datasource.history_financial_provider import _compute_history_coverage
    rows = [
        {"period": "2020-12-31"},
        {"period": "2021-12-31"},
        {"period": "2022-12-31"},
    ]
    coverage = _compute_history_coverage(rows, period_type="annual", start_year=2020, end_year=2022)
    assert coverage["periods_count"] == 3
    assert coverage["expected_periods_count"] == 3
    assert coverage["history_truncated"] is False
    assert coverage["start_period"] == "2020-12-31"
    assert coverage["end_period"] == "2022-12-31"


def test_history_coverage_truncated():
    """_compute_history_coverage 标记 history_truncated=True 当数据不足。"""
    from app.datasource.history_financial_provider import _compute_history_coverage
    rows = [
        {"period": "2022-12-31"},
        {"period": "2023-12-31"},
    ]
    coverage = _compute_history_coverage(rows, period_type="annual", start_year=2016, end_year=2023)
    assert coverage["history_truncated"] is True


def test_normalize_profit_row():
    """_normalize_profit_row 映射 BaoStock profit 字段。"""
    from app.datasource.history_financial_provider import _normalize_profit_row
    raw = {
        "stat_date": "2024-12-31",
        "roe_avg": "0.1234",
        "gross_margin": "0.3456",
        "net_margin": "0.0789",
        "net_profit": "500000000.0",
        "eps_ttm": "1.23",
        "mb_revenue": "1000000000.0",
        "total_share": "1000000.0",
        "liqa_share": "800000.0",
    }
    result = _normalize_profit_row(raw)
    assert result["period"] == "2024-12-31"
    assert result["roe"] == pytest.approx(0.1234)
    assert result["gross_margin"] == pytest.approx(0.3456)
    assert result["net_margin"] == pytest.approx(0.0789)
    assert result["source"] == "baostock_profit"


def test_normalize_growth_row():
    """_normalize_growth_row 映射 BaoStock growth 字段。"""
    from app.datasource.history_financial_provider import _normalize_growth_row
    raw = {
        "stat_date": "2024-12-31",
        "yoy_ni": "0.1500",
        "yoy_pni": "0.1200",
        "yoy_eps": "0.1100",
        "yoy_equity": "0.0800",
        "yoy_asset": "0.0600",
    }
    result = _normalize_growth_row(raw)
    assert result["period"] == "2024-12-31"
    # Phase 6T-E: YOYNI=净利润同比、YOYPNI=归母净利润同比；不再误标为 revenue_yoy
    assert result["net_profit_yoy"] == pytest.approx(0.15)
    assert result["net_profit_parent_yoy"] == pytest.approx(0.12)
    assert "revenue_yoy" not in result


def test_normalize_balance_row():
    """_normalize_balance_row 映射 BaoStock balance 字段。"""
    from app.datasource.history_financial_provider import _normalize_balance_row
    raw = {
        "stat_date": "2024-12-31",
        "current_ratio": "2.1",
        "quick_ratio": "1.5",
        "cash_ratio": "0.8",
        "liability_to_asset": "0.45",
        "asset_to_equity": "1.82",
    }
    result = _normalize_balance_row(raw)
    assert result["period"] == "2024-12-31"
    assert result["current_ratio"] == pytest.approx(2.1)
    assert result["debt_ratio"] == pytest.approx(0.45)
    assert result["equity_multiplier"] == pytest.approx(1.82)


def test_empty_module_result_structure():
    """_empty_module_result 返回正确结构。"""
    from app.datasource.history_financial_provider import _empty_module_result
    result = _empty_module_result("profitability", 2016, 2026)
    assert result["module_key"] == "profitability"
    assert result["data_success"] is False
    assert isinstance(result["history"], list)
    assert isinstance(result["chart_contract"], dict)
    assert "history_coverage" in result
    assert result["history_coverage"]["history_truncated"] is True


def test_chart_contracts_have_required_fields():
    """所有模块的 chart_contract 都有 preferred_chart 和 series。"""
    from app.datasource.history_financial_provider import _CHART_CONTRACTS
    for module_key, contract in _CHART_CONTRACTS.items():
        assert "preferred_chart" in contract, f"{module_key} missing preferred_chart"
        assert "series" in contract, f"{module_key} missing series"
        assert isinstance(contract["series"], list), f"{module_key} series must be list"


def test_latest_derived_from_history():
    """latest 应该从 history 中取最新一期（最后一行）。"""
    from app.datasource.history_financial_provider import (
        _normalize_profit_row,
        _detect_period_type,
    )
    rows_raw = [
        {"stat_date": "2022-12-31", "roe_avg": "0.10", "gross_margin": "0.30",
         "net_margin": "0.05", "net_profit": "400000000.0", "eps_ttm": "1.0",
         "mb_revenue": "900000000.0", "total_share": "1000000.0", "liqa_share": "800000.0"},
        {"stat_date": "2023-12-31", "roe_avg": "0.12", "gross_margin": "0.31",
         "net_margin": "0.06", "net_profit": "450000000.0", "eps_ttm": "1.1",
         "mb_revenue": "950000000.0", "total_share": "1000000.0", "liqa_share": "800000.0"},
        {"stat_date": "2024-12-31", "roe_avg": "0.13", "gross_margin": "0.33",
         "net_margin": "0.07", "net_profit": "500000000.0", "eps_ttm": "1.2",
         "mb_revenue": "1000000000.0", "total_share": "1000000.0", "liqa_share": "800000.0"},
    ]
    normalized = [_normalize_profit_row(r) for r in rows_raw]
    sorted_rows = sorted(normalized, key=lambda r: r.get("period") or "")
    latest = sorted_rows[-1] if sorted_rows else {}
    assert latest.get("period") == "2024-12-31"
    assert latest.get("roe") == pytest.approx(0.13)


def test_period_filter_annual_only():
    """annual 过滤后只保留 12-31 结尾的行。"""
    rows = [
        {"period": "2022-03-31", "roe": 0.10},
        {"period": "2022-06-30", "roe": 0.11},
        {"period": "2022-09-30", "roe": 0.12},
        {"period": "2022-12-31", "roe": 0.13},
        {"period": "2023-12-31", "roe": 0.14},
    ]
    annual = [r for r in rows if (r.get("period") or "").endswith("12-31")]
    assert len(annual) == 2
    assert all(r["period"].endswith("12-31") for r in annual)


def test_period_classifier_point_in_time():
    """单行数据识别为 point_in_time（Phase 6T-E 权威分类器语义）。"""
    from app.datasource.history_financial_provider import _detect_period_type
    rows = [{"period": "2024-12-31"}]
    assert _detect_period_type(rows) == "point_in_time"


# ── History Service 测试 ─────────────────────────────────────────────────────

def test_history_service_import():
    """company_v2_history_service 可正常导入。"""
    from app.services.company_v2_history_service import (
        build_company_history_dashboard,
        get_module_history,
    )
    assert callable(build_company_history_dashboard)
    assert callable(get_module_history)


def test_history_service_ts_code_conversion():
    """_ts_code 函数正确转换股票代码格式。"""
    from app.services.company_v2_history_service import _ts_code
    assert _ts_code("601686") == "601686.SH"
    assert _ts_code("000725") == "000725.SZ"
    assert _ts_code("600519") == "600519.SH"
    assert _ts_code("601686.SH") == "601686.SH"


@pytest.mark.asyncio
async def test_history_dashboard_structure():
    """build_company_history_dashboard 返回正确的结构（mocked BaoStock）。"""
    from unittest.mock import AsyncMock, patch
    from app.services.company_v2_history_service import build_company_history_dashboard

    mock_modules = {
        "profitability": {
            "history": [{"period": "2023-12-31", "roe": 0.12}],
            "latest": {"period": "2023-12-31", "roe": 0.12},
            "period_type": "annual",
            "chart_contract": {"preferred_chart": "multi_line", "series": []},
            "history_coverage": {"periods_count": 1, "history_truncated": False},
            "data_success": True,
            "provider": "baostock",
        }
    }

    with patch("app.services.company_v2_history_service.fetch_all_modules_history",
               new=AsyncMock(return_value=mock_modules)):
        with patch("app.services.company_v2_history_service.get_stock_basic",
                   new=AsyncMock(return_value={"list_year": 2016, "symbol": "601686"})):
            result = await build_company_history_dashboard("CN", "601686", period="annual")

    assert result["market"] == "CN"
    assert result["symbol"] == "601686"
    assert "modules" in result
    assert "stock_basic" in result
    assert "disclaimer" in result
    assert "构成投资建议" not in result["disclaimer"] or "不构成" in result["disclaimer"]


@pytest.mark.asyncio
async def test_history_dashboard_no_buy_sell_wording():
    """history dashboard 不包含买入/卖出/目标价等投资建议措辞。"""
    from unittest.mock import AsyncMock, patch
    from app.services.company_v2_history_service import build_company_history_dashboard

    with patch("app.services.company_v2_history_service.fetch_all_modules_history",
               new=AsyncMock(return_value={})):
        with patch("app.services.company_v2_history_service.get_stock_basic",
                   new=AsyncMock(return_value={"list_year": 2020})):
            result = await build_company_history_dashboard("CN", "601686")

    result_str = str(result)
    forbidden = ["买入", "卖出", "目标价", "保证上涨", "推荐买入", "强烈推荐"]
    for word in forbidden:
        assert word not in result_str, f"Found forbidden wording: {word}"


@pytest.mark.asyncio
async def test_fetch_all_modules_history_uses_single_bulk_fetch():
    """全模块 history 获取应复用一次批量抓取，避免每模块重复调用（Phase 6T-E1）。"""
    from unittest.mock import AsyncMock, patch
    from app.datasource.history_financial_provider import fetch_all_modules_history

    aggregate = {
        "profit": [
            {
                "stat_date": "2024-12-31",
                "roe_avg": "0.12",
                "gross_margin": "0.30",
                "net_margin": "0.08",
            }
        ],
        "growth": [],
        "cash_flow": [],
        "balance": [],
        "operation": [],
        "dupont": [],
        "_bulk_stats": {"provider_calls": 6, "login_batches": 1},
    }
    mock_bulk = AsyncMock(return_value=aggregate)

    with patch("app.datasource.baostock_client.baostock_client.get_financial_history_bulk", mock_bulk):
        stats: dict = {}
        result = await fetch_all_modules_history(
            "601686.SH", start_year=2024, end_year=2024, period="annual", stats_out=stats)

    mock_bulk.assert_awaited_once()
    assert result["profitability"]["data_success"] is True
    assert "growth" in result
    assert stats["provider_calls"] == 6
