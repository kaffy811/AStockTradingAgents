"""
backend/tests/fundamental/test_phase6tb_company_stock_basic.py
Phase 6T-B: Company/Stock Basic Info 验收测试
"""
from __future__ import annotations

import pytest


# ── Stock Basic Service 导入测试 ─────────────────────────────────────────────

def test_stock_basic_service_import():
    """company_v2_stock_basic_service 可正常导入。"""
    from app.services.company_v2_stock_basic_service import (
        get_stock_basic,
        get_default_start_year,
        _SEED_LIST_DATE,
        _to_ts_code,
        _extract_code,
    )
    assert callable(get_stock_basic)
    assert callable(get_default_start_year)
    assert "601686" in _SEED_LIST_DATE


def test_extract_code():
    """_extract_code 从 ts_code 或纯代码中提取6位代码。"""
    from app.services.company_v2_stock_basic_service import _extract_code
    assert _extract_code("601686.SH") == "601686"
    assert _extract_code("000725.SZ") == "000725"
    assert _extract_code("601686") == "601686"


def test_to_ts_code():
    """_to_ts_code 正确识别交易所。"""
    from app.services.company_v2_stock_basic_service import _to_ts_code
    assert _to_ts_code("601686") == "601686.SH"
    assert _to_ts_code("000725") == "000725.SZ"
    assert _to_ts_code("300001") == "300001.SZ"
    assert _to_ts_code("430001") == "430001.BJ"
    # 已有后缀时直接返回
    assert _to_ts_code("601686.SH") == "601686.SH"


# ── 上市日期 / 起始年份测试 ──────────────────────────────────────────────────

def test_get_default_start_year_from_list_date():
    """有 list_year 时使用上市年份。"""
    from app.services.company_v2_stock_basic_service import get_default_start_year
    stock_basic = {"list_year": 2016, "symbol": "601686"}
    start_year, status = get_default_start_year(stock_basic)
    assert start_year == 2016
    assert status == "from_list_date"


def test_get_default_start_year_unknown():
    """list_year 缺失时回退到近10年。"""
    from app.services.company_v2_stock_basic_service import get_default_start_year
    from datetime import date
    stock_basic = {"list_year": None}
    start_year, status = get_default_start_year(stock_basic)
    assert status == "default_10y"
    expected_year = date.today().year - 10
    assert start_year == expected_year


def test_get_default_start_year_invalid_list_year():
    """list_year 为无效值时回退到近10年。"""
    from app.services.company_v2_stock_basic_service import get_default_start_year
    stock_basic = {"list_year": 1850}  # Invalid
    start_year, status = get_default_start_year(stock_basic)
    assert status == "default_10y"


def test_seed_list_date_601686():
    """601686 的 seed list_date 为 2020-12-04（Phase 6T-E 依据 BaoStock exact 修正）。"""
    from app.services.company_v2_stock_basic_service import _SEED_LIST_DATE
    assert _SEED_LIST_DATE["601686"] == "2020-12-04"


def test_seed_list_date_600519():
    """600519 贵州茅台的 seed list_date 存在且合理。"""
    from app.services.company_v2_stock_basic_service import _SEED_LIST_DATE
    assert "600519" in _SEED_LIST_DATE
    year = int(_SEED_LIST_DATE["600519"][:4])
    assert 1990 <= year <= 2010


# ── get_stock_basic 输出结构测试 ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_stock_basic_seed_fallback():
    """BaoStock 失败时从 seed 获取 list_date。"""
    from unittest.mock import AsyncMock, patch
    from app.services.company_v2_stock_basic_service import get_stock_basic

    # Mock BaoStock 失败
    with patch("app.services.company_v2_stock_basic_service._fetch_baostock_stock_basic",
               new=AsyncMock(return_value=None)):
        with patch("app.services.company_v2_stock_basic_service._fetch_akshare_stock_info",
                   new=AsyncMock(return_value=None)):
            result = await get_stock_basic("601686")

    assert result["symbol"] == "601686"
    assert result["ts_code"] == "601686.SH"
    assert result["list_date"] == "2020-12-04"
    assert result["list_year"] == 2020
    assert result["list_date_status"] == "seed"
    assert result["source"] == "seed"


@pytest.mark.asyncio
async def test_get_stock_basic_default_fallback():
    """完全未知时 list_date 为空，list_date_status=unknown。"""
    from unittest.mock import AsyncMock, patch
    from app.services.company_v2_stock_basic_service import get_stock_basic

    with patch("app.services.company_v2_stock_basic_service._fetch_baostock_stock_basic",
               new=AsyncMock(return_value=None)):
        with patch("app.services.company_v2_stock_basic_service._fetch_akshare_stock_info",
                   new=AsyncMock(return_value=None)):
            result = await get_stock_basic("999999")  # 无 seed 的代码

    assert result["symbol"] == "999999"
    assert result["list_date"] == ""
    assert result["list_date_status"] == "unknown"


@pytest.mark.asyncio
async def test_get_stock_basic_from_baostock():
    """BaoStock 成功时使用其数据。"""
    from unittest.mock import AsyncMock, patch
    from app.services.company_v2_stock_basic_service import get_stock_basic

    mock_bs_data = {
        "symbol": "601686",
        "ts_code": "601686.SH",
        "company_name": "友发集团股份有限公司",
        "exchange": "上交所",
        "market": "CN",
        "list_date": "2016-06-17",
        "industry": "钢铁",
        "area": "天津",
        "source": "baostock",
    }
    with patch("app.services.company_v2_stock_basic_service._fetch_baostock_stock_basic",
               new=AsyncMock(return_value=mock_bs_data)):
        with patch("app.services.company_v2_stock_basic_service._fetch_akshare_stock_info",
                   new=AsyncMock(return_value=None)):
            result = await get_stock_basic("601686")

    assert result["list_date"] == "2016-06-17"
    assert result["list_year"] == 2016
    assert result["list_date_status"] == "exact"
    assert result["source"] == "baostock"
    assert result["company_name"] == "友发集团股份有限公司"


@pytest.mark.asyncio
async def test_get_stock_basic_no_sensitive_fields():
    """返回结构中不应含 token/secret/local_path 等敏感字段。"""
    from unittest.mock import AsyncMock, patch
    from app.services.company_v2_stock_basic_service import get_stock_basic

    with patch("app.services.company_v2_stock_basic_service._fetch_baostock_stock_basic",
               new=AsyncMock(return_value=None)):
        with patch("app.services.company_v2_stock_basic_service._fetch_akshare_stock_info",
                   new=AsyncMock(return_value=None)):
            result = await get_stock_basic("601686")

    sensitive_keys = {"token", "secret", "password", "local_path", "file_path", "api_key"}
    for k in sensitive_keys:
        assert k not in result, f"Sensitive field {k!r} found in result"


# ── 股本信息用于市值计算测试 ──────────────────────────────────────────────────

def test_share_capital_used_for_market_cap():
    """total_share / float_share 字段存在于 normalize_profit_row 中，用于市值计算。"""
    from app.datasource.history_financial_provider import _normalize_profit_row
    raw = {
        "stat_date": "2024-12-31",
        "roe_avg": "0.12",
        "gross_margin": "0.30",
        "net_margin": "0.06",
        "net_profit": "500000000.0",
        "eps_ttm": "1.2",
        "mb_revenue": "1000000000.0",
        "total_share": "2000000.0",     # 万股
        "liqa_share": "1800000.0",      # 流通股
    }
    result = _normalize_profit_row(raw)
    assert result.get("total_share") is not None
    assert result.get("float_share") is not None
    assert result["total_share"] == pytest.approx(2000000.0)
    assert result["float_share"] == pytest.approx(1800000.0)


# ── 公司基本信息必填字段测试 ──────────────────────────────────────────────────

def test_stock_basic_required_fields():
    """get_stock_basic 必须返回所有必填字段。"""
    import asyncio
    from unittest.mock import AsyncMock, patch
    from app.services.company_v2_stock_basic_service import get_stock_basic

    async def _run():
        with patch("app.services.company_v2_stock_basic_service._fetch_baostock_stock_basic",
                   new=AsyncMock(return_value=None)):
            with patch("app.services.company_v2_stock_basic_service._fetch_akshare_stock_info",
                       new=AsyncMock(return_value=None)):
                return await get_stock_basic("601686")

    result = asyncio.run(_run())
    required_fields = [
        "symbol", "ts_code", "company_name", "exchange", "market",
        "list_date", "list_year", "industry", "list_date_status", "source", "updated_at"
    ]
    for f in required_fields:
        assert f in result, f"Missing required field: {f}"
