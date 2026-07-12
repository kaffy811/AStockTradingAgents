"""
tests/test_phase6_zero_cost_data_mode.py — Phase 6A 零成本公开数据源模式验证

涵盖：
  1. data_mode=free 跳过 Tushare
  2. data_mode=free + 无 BaoStock/AkShare → err_envelope
  3. BaoStock _to_bs_code 代码转换
  4. analyst_ratings / announcements 标记为 standard_only
  5. get_available_modules("free") 排除 standard_only
  6. get_available_modules("standard") 包含全部 display 模块
  7. DataEnvelope 契约：BaoStock 空返回 → partial=True
  8. source.actual = "baostock" when BaoStock 成功
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ═══════════════════════════════════════════════════════════════════════════════
# 辅助 fixtures
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.fixture
def mock_settings_free():
    """模拟 data_mode=free, enable_baostock=True, enable_akshare=True"""
    with patch("app.core.config.settings") as m:
        m.data_mode = "free"
        m.enable_baostock = True
        m.enable_akshare = True
        yield m


@pytest.fixture
def mock_settings_free_no_sources():
    """模拟 data_mode=free, BaoStock/AkShare 均关闭"""
    with patch("app.core.config.settings") as m:
        m.data_mode = "free"
        m.enable_baostock = False
        m.enable_akshare = False
        yield m


@pytest.fixture
def mock_settings_standard():
    """模拟标准模式"""
    with patch("app.core.config.settings") as m:
        m.data_mode = "standard"
        m.enable_baostock = False
        m.enable_akshare = False
        yield m


# ═══════════════════════════════════════════════════════════════════════════════
# 测试 1: data_mode=free 跳过 Tushare（fetch_baostock 被调用）
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_free_mode_skips_tushare(mock_settings_free):
    """
    data_mode=free 时，fetch_with_fallback 不调用 fetch()（Tushare）。
    BaoStock 成功时直接返回 ok_envelope。
    """
    from app.tools.fundamental.profitability import ProfitabilityTool

    tool = ProfitabilityTool(limit=2, annual=True)

    fake_bs_data = {
        "symbol": "600519", "ts_code": "600519.SH", "annual": True,
        "series": [{"end_date": "2024-12-31", "roe_pct": 30.0, "gross_margin_pct": 50.0}],
        "comment": "test", "source": "baostock",
    }

    with patch.object(tool, "fetch", side_effect=AssertionError("不应调用 Tushare")) as mock_fetch, \
         patch.object(tool, "fetch_baostock", new=AsyncMock(return_value=fake_bs_data)) as mock_bs:
        envelope = await tool.fetch_with_fallback("CN", "600519")

    mock_fetch.assert_not_called()
    mock_bs.assert_awaited_once()
    assert envelope["ok"] is True
    assert envelope["data"]["source"] == "baostock"


# ═══════════════════════════════════════════════════════════════════════════════
# 测试 2: data_mode=free + 无可用源 → err_envelope
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_free_mode_no_sources_returns_err_envelope(mock_settings_free_no_sources):
    """
    data_mode=free 且 BaoStock/AkShare 均关闭时，返回 err_envelope 而非抛异常。
    """
    from app.tools.fundamental.profitability import ProfitabilityTool

    tool = ProfitabilityTool(limit=2)
    envelope = await tool.fetch_with_fallback("CN", "600519")

    assert envelope["ok"] is False
    assert envelope["data"] is None
    assert "free" in envelope["reason"].lower() or "baostock" in envelope["reason"].lower()


# ═══════════════════════════════════════════════════════════════════════════════
# 测试 3: BaoStock _to_bs_code 代码转换
# ═══════════════════════════════════════════════════════════════════════════════

def test_to_bs_code_sh():
    from app.datasource.baostock_client import _to_bs_code
    assert _to_bs_code("600519.SH") == "sh.600519"


def test_to_bs_code_sz():
    from app.datasource.baostock_client import _to_bs_code
    assert _to_bs_code("000725.SZ") == "sz.000725"


def test_to_bs_code_no_dot_sh():
    from app.datasource.baostock_client import _to_bs_code
    # 无点号 → 按首位猜交易所
    assert _to_bs_code("600519") == "sh.600519"


def test_to_bs_code_no_dot_sz():
    from app.datasource.baostock_client import _to_bs_code
    assert _to_bs_code("000725") == "sz.000725"


# ═══════════════════════════════════════════════════════════════════════════════
# 测试 4: analyst_ratings / announcements 标记为 standard_only
# ═══════════════════════════════════════════════════════════════════════════════

def test_analyst_ratings_is_standard_only():
    from app.tools.fundamental import MODULE_CATALOG
    catalog = {m["key"]: m for m in MODULE_CATALOG}
    assert catalog["analyst_ratings"]["data_mode"] == "standard_only"


def test_announcements_is_standard_only():
    from app.tools.fundamental import MODULE_CATALOG
    catalog = {m["key"]: m for m in MODULE_CATALOG}
    assert catalog["announcements"]["data_mode"] == "standard_only"


# ═══════════════════════════════════════════════════════════════════════════════
# 测试 5: get_available_modules("free") 排除 standard_only
# ═══════════════════════════════════════════════════════════════════════════════

def test_get_available_modules_free_excludes_standard_only():
    from app.tools.fundamental import get_available_modules
    modules = get_available_modules("free")
    keys = [m["key"] for m in modules]
    assert "analyst_ratings" not in keys
    assert "announcements" not in keys


def test_get_available_modules_free_includes_free_ok():
    from app.tools.fundamental import get_available_modules
    modules = get_available_modules("free")
    keys = [m["key"] for m in modules]
    # 这些模块在 free 模式应可用
    assert "profitability" in keys
    assert "growth" in keys
    assert "solvency" in keys


# ═══════════════════════════════════════════════════════════════════════════════
# 测试 6: get_available_modules("standard") 包含全部 display 模块
# ═══════════════════════════════════════════════════════════════════════════════

def test_get_available_modules_standard_includes_all():
    from app.tools.fundamental import MODULE_CATALOG, get_available_modules
    std_modules = get_available_modules("standard")
    std_keys = {m["key"] for m in std_modules}

    # standard_only 模块必须在 standard 中
    assert "analyst_ratings" in std_keys
    assert "announcements" in std_keys

    # standard 模块数量 >= free 模块数量
    free_modules = get_available_modules("free")
    assert len(std_modules) >= len(free_modules)


# ═══════════════════════════════════════════════════════════════════════════════
# 测试 7: BaoStock 返回空 → partial=True（DataEnvelope 契约）
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_baostock_empty_returns_partial(mock_settings_free):
    """
    BaoStock 返回空（RuntimeError），AkShare 也未实现
    → err_envelope 满足 DataEnvelope 契约：ok=False, data=None
    """
    from app.tools.fundamental.profitability import ProfitabilityTool

    tool = ProfitabilityTool(limit=2)

    with patch.object(tool, "fetch_baostock", new=AsyncMock(side_effect=RuntimeError("BaoStock 无数据"))), \
         patch.object(tool, "fetch_akshare", new=AsyncMock(side_effect=NotImplementedError)):
        envelope = await tool.fetch_with_fallback("CN", "600519")

    # DataEnvelope 契约：ok=False, data=None (partial implied)
    assert envelope["ok"] is False
    assert envelope["data"] is None
    assert envelope["reason"] is not None


# ═══════════════════════════════════════════════════════════════════════════════
# 测试 8: source.actual = "baostock" when BaoStock 成功
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_baostock_success_source_actual(mock_settings_free):
    """
    BaoStock 成功时，data["source"] = "baostock"，
    build_api_response 中 source.actual = "baostock"。
    """
    from app.tools.fundamental.profitability import ProfitabilityTool
    from app.aggregator.envelope import build_api_response

    tool = ProfitabilityTool(limit=2)
    fake_data = {
        "symbol": "600519", "ts_code": "600519.SH", "annual": True,
        "series": [{"end_date": "2024-12-31", "roe_pct": 30.0}],
        "comment": "ok", "source": "baostock",
    }

    with patch.object(tool, "fetch_baostock", new=AsyncMock(return_value=fake_data)):
        envelope = await tool.fetch_with_fallback("CN", "600519")

    assert envelope["ok"] is True
    response = build_api_response(
        envelope,
        market="CN", symbol="600519", ts_code="600519.SH",
        module_key="profitability", module_name="盈利质量",
    )
    assert response["source"]["actual"] == "baostock"


# ═══════════════════════════════════════════════════════════════════════════════
# 测试 9: free mode fallback AkShare when BaoStock disabled
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_free_mode_falls_back_to_akshare():
    """
    data_mode=free, enable_baostock=False, enable_akshare=True
    → 直接走 AkShare fallback
    """
    from app.tools.fundamental.cashflow_quality import CashflowQualityTool

    tool = CashflowQualityTool()
    fake_data = {
        "symbol": "600519", "ts_code": "600519.SH",
        "periods": [{"end_date": "2024-12-31", "ocf": 1e10}],
        "source": "akshare_fallback",
    }

    with patch("app.core.config.settings") as ms:
        ms.data_mode = "free"
        ms.enable_baostock = False
        ms.enable_akshare = True
        with patch.object(tool, "fetch_akshare", new=AsyncMock(return_value=fake_data)) as mock_ak, \
             patch.object(tool, "fetch", side_effect=AssertionError("不应调用 Tushare")):
            envelope = await tool.fetch_with_fallback("CN", "600519")

    mock_ak.assert_awaited_once()
    assert envelope["ok"] is True
    assert envelope["stale"] is True  # AkShare fallback 标记 stale


# ═══════════════════════════════════════════════════════════════════════════════
# 测试 10: standard mode 行为不变（Tushare first）
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_standard_mode_calls_tushare_first(mock_settings_standard):
    """
    data_mode=standard 时，fetch_with_fallback 仍然先调用 fetch()（Tushare）。
    """
    from app.tools.fundamental.profitability import ProfitabilityTool

    tool = ProfitabilityTool(limit=2)
    fake_data = {
        "symbol": "600519", "ts_code": "600519.SH", "annual": True,
        "series": [], "comment": "", "source": "tushare",
    }

    with patch.object(tool, "fetch", new=AsyncMock(return_value=fake_data)) as mock_ts, \
         patch.object(tool, "fetch_baostock", side_effect=AssertionError("不应调用 BaoStock")):
        envelope = await tool.fetch_with_fallback("CN", "600519")

    mock_ts.assert_awaited_once()
    assert envelope["ok"] is True
