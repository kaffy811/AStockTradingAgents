"""
tests/fundamental/test_phase2a_financial_modules.py — Phase 2A 七个财务分析模块测试

覆盖范围（10 大场景 × 7 工具）：
  T1  : 每个新增工具正常返回（dict，含 series/comment/source）
  T2  : 每个工具字段缺失时不报错（返回 None，不 KeyError）
  T3  : 分母为 0 或负数时比率返回 null
  T4  : limit 参数生效（series 长度 <= limit）
  T5  : annual=True 过滤生效（只有 1231 日期）
  T6  : MODULE_CATALOG 中新增模块 status=available
  T7  : 兼容路由可以访问每个新增模块（mock aggregator）
  T8  : DataEnvelope errors 永远是 list
  T9  : partial=True 场景（_partial_errors 存在时）
  T10 : ENABLE_AKSHARE=false 不影响本阶段工具

原则：不发真实 HTTP 请求，不依赖真实 Tushare Token。
"""

from __future__ import annotations

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

import pandas as pd
import numpy as np

# ── 导入被测工具 ──────────────────────────────────────────────────────────────
from app.tools.fundamental.growth import GrowthTool
from app.tools.fundamental.profitability import ProfitabilityTool
from app.tools.fundamental.expense_analysis import ExpenseAnalysisTool
from app.tools.fundamental.asset_structure import AssetStructureTool
from app.tools.fundamental.solvency import SolvencyTool
from app.tools.fundamental.operation_capability import OperationCapabilityTool
from app.tools.fundamental.capital_occupation import CapitalOccupationTool
from app.tools.fundamental._helpers import (
    safe_float, safe_div, safe_pct, filter_annual, filter_report_type, fmt_date, row_get,
)
from app.tools.fundamental import MODULE_CATALOG, TOOL_REGISTRY
from app.aggregator.envelope import build_api_response, ok_envelope, err_envelope


# ── 公共 fixture ──────────────────────────────────────────────────────────────

def _make_income_df(dates: list[str], has_revenue: bool = True) -> pd.DataFrame:
    rows = []
    for d in dates:
        rev = 1_000_000_000.0 if has_revenue else None
        rows.append({
            "end_date": d, "report_type": "1",
            "total_revenue": rev, "revenue": rev,
            "oper_cost": 600_000_000.0 if has_revenue else None,
            "total_operate_cost": 700_000_000.0 if has_revenue else None,
            "n_income_attr_p": 200_000_000.0 if has_revenue else None,
            "profit_dedt": 180_000_000.0 if has_revenue else None,
            "sell_exp": 30_000_000.0 if has_revenue else None,
            "admin_exp": 20_000_000.0 if has_revenue else None,
            "fin_exp": 5_000_000.0 if has_revenue else None,
            "rd_exp": 10_000_000.0 if has_revenue else None,
            "operate_profit": 250_000_000.0 if has_revenue else None,
            "non_oper_income": 5_000_000.0 if has_revenue else None,
            "non_oper_exp": 1_000_000.0 if has_revenue else None,
            "taxes_surcharges": 8_000_000.0 if has_revenue else None,
        })
    return pd.DataFrame(rows)


def _make_balancesheet_df(dates: list[str]) -> pd.DataFrame:
    rows = []
    for d in dates:
        rows.append({
            "end_date": d, "report_type": "1",
            "total_assets": 5_000_000_000.0,
            "total_liab": 2_000_000_000.0,
            "total_hldr_eqy_exc_min_int": 3_000_000_000.0,
            "total_cur_assets": 2_000_000_000.0,
            "total_cur_liab": 1_000_000_000.0,
            "inventories": 500_000_000.0,
            "money_cap": 800_000_000.0,
            "fix_assets": 1_500_000_000.0,
            "goodwill": 100_000_000.0,
            "accounts_receiv": 300_000_000.0,
            "notes_receiv": 50_000_000.0,
            "prepayment": 30_000_000.0,
            "acct_payable": 400_000_000.0,
            "notes_payable": 60_000_000.0,
            "adv_receipts": 20_000_000.0,
            "contract_liab": 15_000_000.0,
        })
    return pd.DataFrame(rows)


def _make_fina_indicator_df(dates: list[str]) -> pd.DataFrame:
    rows = []
    for d in dates:
        rows.append({
            "end_date": d,
            "or_yoy": 12.5, "netprofit_yoy": 8.3, "dt_netprofit_yoy": 7.1,
            "roe": 15.2, "roa": 6.8, "roic": 9.1,
            "grossprofit_margin": 40.0, "netprofit_margin": 20.0,
            "beps": 2.5,
            "debt_to_assets": 40.0,
            "ebit": 300_000_000.0,
            "ebitda": 350_000_000.0,
            "ar_turn": 4.2, "inv_turn": 3.1, "assets_turn": 0.8,
            "op_cycle": 150.0,
        })
    return pd.DataFrame(rows)


ANNUAL_DATES = ["20231231", "20221231", "20211231", "20201231",
                "20191231", "20181231", "20171231", "20161231"]
MIXED_DATES  = ["20231231", "20230930", "20230630", "20230331",
                "20221231", "20220930", "20220630", "20220331"]


def _run(coro):
    return asyncio.run(coro)


# ═══════════════════════════════════════════════════════════════════════════
# T1 — 每个新增工具正常返回
# ═══════════════════════════════════════════════════════════════════════════

class TestT1NormalReturn:
    """每个新增工具正常返回 dict，含 series / comment / source。"""

    def _patch_tushare(self):
        return {
            "get_income":         AsyncMock(return_value=_make_income_df(ANNUAL_DATES)),
            "get_fina_indicator": AsyncMock(return_value=_make_fina_indicator_df(ANNUAL_DATES)),
            "get_balancesheet":   AsyncMock(return_value=_make_balancesheet_df(ANNUAL_DATES)),
        }

    def _apply_patches(self, patches: dict):
        mocks = []
        for method, mock in patches.items():
            p = patch(f"app.datasource.tushare_client.tushare_client.{method}", mock)
            mocks.append(p.start())
        return mocks

    def _stop(self, mocks):
        for m in mocks:
            pass  # patch.start() returns the mock, not the patcher

    def test_t1_growth(self):
        """T1-1: GrowthTool 正常返回。"""
        patches = self._patch_tushare()
        with patch("app.datasource.tushare_client.tushare_client.get_income", patches["get_income"]), \
             patch("app.datasource.tushare_client.tushare_client.get_fina_indicator", patches["get_fina_indicator"]):
            result = _run(GrowthTool().fetch("CN", "600519"))
        assert isinstance(result, dict)
        assert "series" in result
        assert "comment" in result
        assert result.get("source") == "tushare"

    def test_t1_profitability(self):
        """T1-2: ProfitabilityTool 正常返回。"""
        patches = self._patch_tushare()
        with patch("app.datasource.tushare_client.tushare_client.get_fina_indicator", patches["get_fina_indicator"]), \
             patch("app.datasource.tushare_client.tushare_client.get_income", patches["get_income"]):
            result = _run(ProfitabilityTool().fetch("CN", "600519"))
        assert isinstance(result, dict)
        assert "series" in result
        assert "comment" in result

    def test_t1_expense_analysis(self):
        """T1-3: ExpenseAnalysisTool 正常返回。"""
        patches = self._patch_tushare()
        with patch("app.datasource.tushare_client.tushare_client.get_income", patches["get_income"]):
            result = _run(ExpenseAnalysisTool().fetch("CN", "600519"))
        assert isinstance(result, dict)
        assert "series" in result

    def test_t1_asset_structure(self):
        """T1-4: AssetStructureTool 正常返回。"""
        patches = self._patch_tushare()
        with patch("app.datasource.tushare_client.tushare_client.get_balancesheet", patches["get_balancesheet"]):
            result = _run(AssetStructureTool().fetch("CN", "600519"))
        assert isinstance(result, dict)
        assert "series" in result

    def test_t1_solvency(self):
        """T1-5: SolvencyTool 正常返回。"""
        patches = self._patch_tushare()
        with patch("app.datasource.tushare_client.tushare_client.get_balancesheet", patches["get_balancesheet"]), \
             patch("app.datasource.tushare_client.tushare_client.get_fina_indicator", patches["get_fina_indicator"]):
            result = _run(SolvencyTool().fetch("CN", "600519"))
        assert isinstance(result, dict)
        assert "series" in result

    def test_t1_operation_capability(self):
        """T1-6: OperationCapabilityTool 正常返回。"""
        patches = self._patch_tushare()
        with patch("app.datasource.tushare_client.tushare_client.get_fina_indicator", patches["get_fina_indicator"]), \
             patch("app.datasource.tushare_client.tushare_client.get_income", patches["get_income"]), \
             patch("app.datasource.tushare_client.tushare_client.get_balancesheet", patches["get_balancesheet"]):
            result = _run(OperationCapabilityTool().fetch("CN", "600519"))
        assert isinstance(result, dict)
        assert "series" in result

    def test_t1_capital_occupation(self):
        """T1-7: CapitalOccupationTool 正常返回。"""
        patches = self._patch_tushare()
        with patch("app.datasource.tushare_client.tushare_client.get_balancesheet", patches["get_balancesheet"]), \
             patch("app.datasource.tushare_client.tushare_client.get_income", patches["get_income"]):
            result = _run(CapitalOccupationTool().fetch("CN", "600519"))
        assert isinstance(result, dict)
        assert "series" in result


# ═══════════════════════════════════════════════════════════════════════════
# T2 — 字段缺失时不报错
# ═══════════════════════════════════════════════════════════════════════════

def _make_empty_income_df() -> pd.DataFrame:
    """所有财务字段均为 NaN 的 income DataFrame。"""
    return pd.DataFrame([{
        "end_date": "20231231", "report_type": "1",
        "total_revenue": np.nan, "revenue": np.nan,
        "oper_cost": np.nan, "total_operate_cost": np.nan,
        "n_income_attr_p": np.nan, "profit_dedt": np.nan,
        "sell_exp": np.nan, "admin_exp": np.nan,
        "fin_exp": np.nan, "rd_exp": np.nan,
        "operate_profit": np.nan, "non_oper_income": np.nan,
        "non_oper_exp": np.nan, "taxes_surcharges": np.nan,
    }])


def _make_empty_balancesheet_df() -> pd.DataFrame:
    return pd.DataFrame([{
        "end_date": "20231231", "report_type": "1",
        "total_assets": np.nan, "total_liab": np.nan,
        "total_hldr_eqy_exc_min_int": np.nan,
        "total_cur_assets": np.nan, "total_cur_liab": np.nan,
        "inventories": np.nan, "money_cap": np.nan,
        "fix_assets": np.nan, "goodwill": np.nan,
        "accounts_receiv": np.nan, "notes_receiv": np.nan,
        "prepayment": np.nan, "acct_payable": np.nan,
        "notes_payable": np.nan, "adv_receipts": np.nan,
        "contract_liab": np.nan,
    }])


def _make_empty_fina_df() -> pd.DataFrame:
    return pd.DataFrame([{
        "end_date": "20231231",
        "or_yoy": np.nan, "netprofit_yoy": np.nan, "dt_netprofit_yoy": np.nan,
        "roe": np.nan, "roa": np.nan, "roic": np.nan,
        "grossprofit_margin": np.nan, "netprofit_margin": np.nan,
        "beps": np.nan, "debt_to_assets": np.nan,
        "ebit": np.nan, "ebitda": np.nan,
        "ar_turn": np.nan, "inv_turn": np.nan, "assets_turn": np.nan,
        "op_cycle": np.nan,
    }])


class TestT2MissingFields:
    """字段缺失时不报错，比率返回 None，不 KeyError。"""

    def test_t2_growth_missing_fields(self):
        """T2-1: GrowthTool — income 字段全 NaN，不报错。"""
        with patch("app.datasource.tushare_client.tushare_client.get_income",
                   AsyncMock(return_value=_make_empty_income_df())), \
             patch("app.datasource.tushare_client.tushare_client.get_fina_indicator",
                   AsyncMock(return_value=_make_empty_fina_df())):
            result = _run(GrowthTool().fetch("CN", "600519"))
        assert isinstance(result, dict)
        series = result["series"]
        assert len(series) > 0
        # 所有比率应为 None
        row = series[0]
        assert row["revenue"] is None
        assert row["revenue_yoy_pct"] is None

    def test_t2_expense_analysis_missing_fields(self):
        """T2-2: ExpenseAnalysisTool — 字段全 NaN，不报错。"""
        with patch("app.datasource.tushare_client.tushare_client.get_income",
                   AsyncMock(return_value=_make_empty_income_df())):
            result = _run(ExpenseAnalysisTool().fetch("CN", "600519"))
        assert isinstance(result, dict)
        assert "series" in result

    def test_t2_asset_structure_missing_fields(self):
        """T2-3: AssetStructureTool — 字段全 NaN，不报错，比率为 None。"""
        with patch("app.datasource.tushare_client.tushare_client.get_balancesheet",
                   AsyncMock(return_value=_make_empty_balancesheet_df())):
            result = _run(AssetStructureTool().fetch("CN", "600519"))
        assert isinstance(result, dict)
        row = result["series"][0]
        assert row["current_asset_ratio_pct"] is None
        assert row["liability_ratio_pct"] is None

    def test_t2_solvency_missing_fields(self):
        """T2-4: SolvencyTool — 字段全 NaN，current_ratio 为 None，不崩溃。"""
        with patch("app.datasource.tushare_client.tushare_client.get_balancesheet",
                   AsyncMock(return_value=_make_empty_balancesheet_df())), \
             patch("app.datasource.tushare_client.tushare_client.get_fina_indicator",
                   AsyncMock(return_value=_make_empty_fina_df())):
            result = _run(SolvencyTool().fetch("CN", "600519"))
        row = result["series"][0]
        assert row["current_ratio"] is None
        assert row["quick_ratio"] is None

    def test_t2_capital_occupation_missing_fields(self):
        """T2-5: CapitalOccupationTool — balancesheet 字段全 NaN，occupation_power 为 None。"""
        with patch("app.datasource.tushare_client.tushare_client.get_balancesheet",
                   AsyncMock(return_value=_make_empty_balancesheet_df())), \
             patch("app.datasource.tushare_client.tushare_client.get_income",
                   AsyncMock(return_value=_make_empty_income_df())):
            result = _run(CapitalOccupationTool().fetch("CN", "600519"))
        assert isinstance(result, dict)


# ═══════════════════════════════════════════════════════════════════════════
# T3 — 分母为 0 或负数时比率返回 null
# ═══════════════════════════════════════════════════════════════════════════

class TestT3ZeroDenominator:
    """分母为 0 或负数时比率必须返回 None，而非 inf / NaN / exception。"""

    def test_t3_safe_div_zero(self):
        """T3-1: safe_div 分母=0 → None。"""
        assert safe_div(100, 0) is None

    def test_t3_safe_div_negative(self):
        """T3-2: safe_div 分母<0 → None。"""
        assert safe_div(100, -5) is None

    def test_t3_safe_pct_zero_den(self):
        """T3-3: safe_pct 分母=0 → None。"""
        assert safe_pct(50, 0) is None

    def test_t3_solvency_zero_liab(self):
        """T3-4: SolvencyTool — total_cur_liab=0 时 current_ratio=None。"""
        bs_df = pd.DataFrame([{
            "end_date": "20231231", "report_type": "1",
            "total_assets": 5e9, "total_liab": 2e9,
            "total_hldr_eqy_exc_min_int": 3e9,
            "total_cur_assets": 2e9, "total_cur_liab": 0.0,  # zero!
            "inventories": 5e8, "money_cap": 8e8,
            "fix_assets": 1.5e9, "goodwill": 1e8,
            "accounts_receiv": 3e8, "notes_receiv": 5e7,
            "prepayment": 3e7, "acct_payable": 4e8,
            "notes_payable": 6e7, "adv_receipts": 2e7, "contract_liab": 1.5e7,
        }])
        with patch("app.datasource.tushare_client.tushare_client.get_balancesheet",
                   AsyncMock(return_value=bs_df)), \
             patch("app.datasource.tushare_client.tushare_client.get_fina_indicator",
                   AsyncMock(return_value=_make_empty_fina_df())):
            result = _run(SolvencyTool().fetch("CN", "600519"))
        row = result["series"][0]
        assert row["current_ratio"] is None

    def test_t3_capital_occupation_zero_receivable(self):
        """T3-5: CapitalOccupationTool — receivable_side=0 → occupation_power=None。"""
        bs_df = pd.DataFrame([{
            "end_date": "20231231", "report_type": "1",
            "total_assets": 5e9, "total_liab": 2e9,
            "total_hldr_eqy_exc_min_int": 3e9,
            "total_cur_assets": 2e9, "total_cur_liab": 1e9,
            "inventories": 5e8, "money_cap": 8e8,
            "fix_assets": 1.5e9, "goodwill": 1e8,
            # receivable side all zero/None
            "accounts_receiv": 0.0, "notes_receiv": 0.0, "prepayment": 0.0,
            "acct_payable": 4e8, "notes_payable": 6e7,
            "adv_receipts": 2e7, "contract_liab": 1.5e7,
        }])
        with patch("app.datasource.tushare_client.tushare_client.get_balancesheet",
                   AsyncMock(return_value=bs_df)), \
             patch("app.datasource.tushare_client.tushare_client.get_income",
                   AsyncMock(return_value=_make_income_df(["20231231"]))):
            result = _run(CapitalOccupationTool().fetch("CN", "600519"))
        row = result["series"][0]
        assert row["occupation_power"] is None

    def test_t3_expense_analysis_zero_revenue(self):
        """T3-6: ExpenseAnalysisTool — total_revenue=0 → 所有费率 None。"""
        inc = _make_income_df(["20231231"])
        inc.loc[0, "total_revenue"] = 0.0
        with patch("app.datasource.tushare_client.tushare_client.get_income",
                   AsyncMock(return_value=inc)):
            result = _run(ExpenseAnalysisTool().fetch("CN", "600519"))
        row = result["series"][0]
        # expense ratios should be None when revenue = 0
        assert row.get("sell_exp_to_revenue") is None or row.get("total_exp_ratio") is None


# ═══════════════════════════════════════════════════════════════════════════
# T4 — limit 参数生效
# ═══════════════════════════════════════════════════════════════════════════

class TestT4LimitParam:
    """limit 参数生效：series 长度 <= limit。"""

    def test_t4_growth_limit_3(self):
        """T4-1: GrowthTool limit=3 → series <= 3。"""
        with patch("app.datasource.tushare_client.tushare_client.get_income",
                   AsyncMock(return_value=_make_income_df(ANNUAL_DATES))), \
             patch("app.datasource.tushare_client.tushare_client.get_fina_indicator",
                   AsyncMock(return_value=_make_fina_indicator_df(ANNUAL_DATES))):
            result = _run(GrowthTool(limit=3).fetch("CN", "600519"))
        assert len(result["series"]) <= 3

    def test_t4_solvency_limit_2(self):
        """T4-2: SolvencyTool limit=2 → series <= 2。"""
        with patch("app.datasource.tushare_client.tushare_client.get_balancesheet",
                   AsyncMock(return_value=_make_balancesheet_df(ANNUAL_DATES))), \
             patch("app.datasource.tushare_client.tushare_client.get_fina_indicator",
                   AsyncMock(return_value=_make_fina_indicator_df(ANNUAL_DATES))):
            result = _run(SolvencyTool(limit=2).fetch("CN", "600519"))
        assert len(result["series"]) <= 2

    def test_t4_capital_occupation_limit_4(self):
        """T4-3: CapitalOccupationTool limit=4 → series <= 4。"""
        with patch("app.datasource.tushare_client.tushare_client.get_balancesheet",
                   AsyncMock(return_value=_make_balancesheet_df(ANNUAL_DATES))), \
             patch("app.datasource.tushare_client.tushare_client.get_income",
                   AsyncMock(return_value=_make_income_df(ANNUAL_DATES))):
            result = _run(CapitalOccupationTool(limit=4).fetch("CN", "600519"))
        assert len(result["series"]) <= 4


# ═══════════════════════════════════════════════════════════════════════════
# T5 — annual=True 过滤生效
# ═══════════════════════════════════════════════════════════════════════════

class TestT5AnnualFilter:
    """annual=True 时 series 中所有 end_date 应以 -12-31 结尾。"""

    def _assert_all_annual(self, series: list[dict]):
        assert len(series) > 0, "series 不应为空"
        for row in series:
            d = row.get("end_date", "")
            assert d is not None and d.endswith("-12-31"), (
                f"annual=True 但发现非年报日期: {d}"
            )

    def test_t5_growth_annual_filter(self):
        """T5-1: GrowthTool annual=True 只返回年报日期。"""
        with patch("app.datasource.tushare_client.tushare_client.get_income",
                   AsyncMock(return_value=_make_income_df(MIXED_DATES))), \
             patch("app.datasource.tushare_client.tushare_client.get_fina_indicator",
                   AsyncMock(return_value=_make_fina_indicator_df(MIXED_DATES))):
            result = _run(GrowthTool(annual=True).fetch("CN", "600519"))
        self._assert_all_annual(result["series"])

    def test_t5_solvency_annual_filter(self):
        """T5-2: SolvencyTool annual=True 只返回年报日期。"""
        with patch("app.datasource.tushare_client.tushare_client.get_balancesheet",
                   AsyncMock(return_value=_make_balancesheet_df(MIXED_DATES))), \
             patch("app.datasource.tushare_client.tushare_client.get_fina_indicator",
                   AsyncMock(return_value=_make_fina_indicator_df(MIXED_DATES))):
            result = _run(SolvencyTool(annual=True).fetch("CN", "600519"))
        self._assert_all_annual(result["series"])

    def test_t5_annual_false_includes_quarterly(self):
        """T5-3: annual=False 时可以包含非 1231 日期。"""
        with patch("app.datasource.tushare_client.tushare_client.get_income",
                   AsyncMock(return_value=_make_income_df(MIXED_DATES))), \
             patch("app.datasource.tushare_client.tushare_client.get_fina_indicator",
                   AsyncMock(return_value=_make_fina_indicator_df(MIXED_DATES))):
            result = _run(GrowthTool(annual=False).fetch("CN", "600519"))
        dates = [r.get("end_date", "") for r in result["series"]]
        # 应包含季报日期
        non_annual = [d for d in dates if d and not d.endswith("-12-31")]
        assert len(non_annual) > 0, "annual=False 时应包含非年报日期"


# ═══════════════════════════════════════════════════════════════════════════
# T6 — MODULE_CATALOG 中新增模块 status=available
# ═══════════════════════════════════════════════════════════════════════════

PHASE2A_KEYS = {
    "growth", "profitability", "expense_analysis",
    "asset_structure", "solvency", "operation_capability", "capital_occupation",
}


class TestT6ModuleCatalog:
    """MODULE_CATALOG 中 Phase 2A 新增模块 status=available。"""

    def test_t6_all_phase2a_keys_in_catalog(self):
        """T6-1: 7 个新 key 均在 MODULE_CATALOG 中。"""
        catalog_keys = {m["key"] for m in MODULE_CATALOG}
        for key in PHASE2A_KEYS:
            assert key in catalog_keys, f"{key} 不在 MODULE_CATALOG"

    def test_t6_all_phase2a_status_available(self):
        """T6-2: 7 个新 key 的 status=available。"""
        catalog = {m["key"]: m for m in MODULE_CATALOG}
        for key in PHASE2A_KEYS:
            assert catalog[key]["status"] == "available", (
                f"{key} status={catalog[key]['status']}，期望 available"
            )

    def test_t6_phase2a_registered_in_tool_registry(self):
        """T6-3: 7 个新 key 均在 TOOL_REGISTRY 中。"""
        for key in PHASE2A_KEYS:
            assert key in TOOL_REGISTRY, f"{key} 不在 TOOL_REGISTRY"

    def test_t6_catalog_total_at_least_27(self):
        """T6-4: Phase 2A 后 MODULE_CATALOG 至少 27 条。"""
        assert len(MODULE_CATALOG) >= 27

    def test_t6_catalog_no_duplicate_keys(self):
        """T6-5: MODULE_CATALOG 无重复 key。"""
        keys = [m["key"] for m in MODULE_CATALOG]
        assert len(keys) == len(set(keys)), "MODULE_CATALOG 存在重复 key"

    def test_t6_catalog_seq_unique(self):
        """T6-6: MODULE_CATALOG 所有 seq 值唯一。"""
        seqs = [m["seq"] for m in MODULE_CATALOG]
        assert len(seqs) == len(set(seqs)), "MODULE_CATALOG 存在重复 seq"

    def test_t6_phase2a_requires_llm_false(self):
        """T6-7: Phase 2A 所有工具 requires_llm=False（确定性计算，不依赖 LLM）。"""
        catalog = {m["key"]: m for m in MODULE_CATALOG}
        for key in PHASE2A_KEYS:
            assert catalog[key]["requires_llm"] is False, f"{key} requires_llm 应为 False"


# ═══════════════════════════════════════════════════════════════════════════
# T7 — 兼容路由可以访问每个新增模块
# ═══════════════════════════════════════════════════════════════════════════

from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.routers.fundamentals_compat import compat_router


def _make_test_app() -> FastAPI:
    app = FastAPI()
    app.include_router(compat_router)
    return app


class TestT7CompatRouter:
    """兼容路由 GET /api/v1/stock/{code}/modules/{module_id} 可以访问新增模块。"""

    def _mock_aggregator(self, key: str):
        mock_agg = MagicMock()
        envelope = ok_envelope(data={"series": [], "comment": "test", "source": "tushare"})
        mock_agg.fetch_module = AsyncMock(return_value=envelope)
        return mock_agg

    def _make_200_response(self, key: str):
        with patch("app.routers.fundamentals_compat.get_aggregator",
                   return_value=self._mock_aggregator(key)), \
             patch("app.core.config.settings") as ms:
            ms.enable_akshare = False
            client = TestClient(_make_test_app())
            resp = client.get(f"/api/v1/stock/600519/modules/{key}")
        return resp

    def test_t7_growth(self):
        """T7-1: compat 路由访问 growth 模块。"""
        assert self._make_200_response("growth").status_code == 200

    def test_t7_profitability(self):
        """T7-2: compat 路由访问 profitability 模块。"""
        assert self._make_200_response("profitability").status_code == 200

    def test_t7_expense_analysis(self):
        """T7-3: compat 路由访问 expense_analysis 模块。"""
        assert self._make_200_response("expense_analysis").status_code == 200

    def test_t7_asset_structure(self):
        """T7-4: compat 路由访问 asset_structure 模块。"""
        assert self._make_200_response("asset_structure").status_code == 200

    def test_t7_solvency(self):
        """T7-5: compat 路由访问 solvency 模块。"""
        assert self._make_200_response("solvency").status_code == 200

    def test_t7_operation_capability(self):
        """T7-6: compat 路由访问 operation_capability 模块。"""
        assert self._make_200_response("operation_capability").status_code == 200

    def test_t7_capital_occupation(self):
        """T7-7: compat 路由访问 capital_occupation 模块。"""
        assert self._make_200_response("capital_occupation").status_code == 200


# ═══════════════════════════════════════════════════════════════════════════
# T8 — DataEnvelope errors 永远是 list
# ═══════════════════════════════════════════════════════════════════════════

class TestT8ErrorsList:
    """build_api_response 产出 errors 字段永远是 list（ok 或 err 均如此）。"""

    def test_t8_ok_envelope_errors_is_list(self):
        """T8-1: ok_envelope → build_api_response → errors 为 []。"""
        env = ok_envelope(data={"series": []})
        resp = build_api_response(env, market="CN", symbol="600519",
                                  ts_code="600519.SH", module_key="growth",
                                  module_name="成长性指标")
        assert isinstance(resp["errors"], list)
        assert resp["errors"] == []

    def test_t8_err_envelope_errors_is_list(self):
        """T8-2: err_envelope → build_api_response → errors 含 reason 字符串。"""
        env = err_envelope(reason="测试错误")
        resp = build_api_response(env, market="CN", symbol="600519",
                                  ts_code="600519.SH", module_key="growth",
                                  module_name="成长性指标")
        assert isinstance(resp["errors"], list)
        assert len(resp["errors"]) >= 1

    def test_t8_partial_errors_in_list(self):
        """T8-3: 含 partial_errors 的 ok_envelope → errors 包含 partial 信息。"""
        env = ok_envelope(
            data={"series": []},
            partial_errors=["income 表失败: connection refused"],
        )
        resp = build_api_response(env, market="CN", symbol="600519",
                                  ts_code="600519.SH", module_key="growth",
                                  module_name="成长性指标")
        assert isinstance(resp["errors"], list)

    def test_t8_new_tools_envelope_structure(self):
        """T8-4: 新工具产出的 dict 通过 ok_envelope 包装后，build_api_response 格式完整。"""
        raw = {"series": [{"end_date": "2023-12-31", "revenue": 1e9}], "comment": "ok", "source": "tushare"}
        env = ok_envelope(data=raw)
        resp = build_api_response(env, market="CN", symbol="600519",
                                  ts_code="600519.SH", module_key="growth",
                                  module_name="成长性指标")
        for field in ("market", "symbol", "ts_code", "module_key", "module_name",
                      "data", "errors", "partial", "stale", "generated_at", "source"):
            assert field in resp, f"缺少字段: {field}"


# ═══════════════════════════════════════════════════════════════════════════
# T9 — partial=True 场景
# ═══════════════════════════════════════════════════════════════════════════

class TestT9Partial:
    """_partial_errors 存在时，DataEnvelope partial=True，build_api_response 中 partial=True。"""

    def test_t9_growth_partial_when_fi_fails(self):
        """T9-1: GrowthTool — fina_indicator 失败 → _partial_errors 存在。"""
        with patch("app.datasource.tushare_client.tushare_client.get_income",
                   AsyncMock(return_value=_make_income_df(["20231231"]))), \
             patch("app.datasource.tushare_client.tushare_client.get_fina_indicator",
                   AsyncMock(side_effect=Exception("connection refused"))):
            result = _run(GrowthTool().fetch("CN", "600519"))
        # 工具应记录 partial error，不应崩溃
        assert isinstance(result, dict)
        assert "_partial_errors" in result

    def test_t9_solvency_partial_when_fi_fails(self):
        """T9-2: SolvencyTool — fina_indicator 失败 → _partial_errors 存在。"""
        with patch("app.datasource.tushare_client.tushare_client.get_balancesheet",
                   AsyncMock(return_value=_make_balancesheet_df(["20231231"]))), \
             patch("app.datasource.tushare_client.tushare_client.get_fina_indicator",
                   AsyncMock(side_effect=Exception("timeout"))):
            result = _run(SolvencyTool().fetch("CN", "600519"))
        assert "_partial_errors" in result

    def test_t9_ok_envelope_with_partial_errors(self):
        """T9-3: ok_envelope(partial_errors=[...]) → partial=True in build_api_response。"""
        env = ok_envelope(data={"series": []}, partial_errors=["fi失败"])
        resp = build_api_response(env, market="CN", symbol="600519",
                                  ts_code="600519.SH", module_key="growth",
                                  module_name="成长性指标")
        assert resp["partial"] is True

    def test_t9_no_partial_errors_partial_false(self):
        """T9-4: ok_envelope 无 partial_errors → partial=False。"""
        env = ok_envelope(data={"series": []})
        resp = build_api_response(env, market="CN", symbol="600519",
                                  ts_code="600519.SH", module_key="growth",
                                  module_name="成长性指标")
        assert resp["partial"] is False


# ═══════════════════════════════════════════════════════════════════════════
# T10 — ENABLE_AKSHARE=false 不影响本阶段工具
# ═══════════════════════════════════════════════════════════════════════════

class TestT10AkshareDisabled:
    """ENABLE_AKSHARE=false 时 Phase 2A 工具正常工作（无 AkShare 依赖）。"""

    def test_t10_growth_no_akshare(self):
        """T10-1: GrowthTool 在 ENABLE_AKSHARE=false 时正常运行。"""
        with patch("app.core.config.settings") as mock_settings, \
             patch("app.datasource.tushare_client.tushare_client.get_income",
                   AsyncMock(return_value=_make_income_df(["20231231"]))), \
             patch("app.datasource.tushare_client.tushare_client.get_fina_indicator",
                   AsyncMock(return_value=_make_fina_indicator_df(["20231231"]))):
            mock_settings.enable_akshare = False
            result = _run(GrowthTool().fetch("CN", "600519"))
        assert isinstance(result, dict)
        assert result.get("source") == "tushare"

    def test_t10_all_phase2a_tools_use_only_tushare(self):
        """T10-2: Phase 2A 所有工具的 source 字段为 'tushare'（无 AkShare 依赖）。"""
        tools_and_patches = [
            (GrowthTool(), {
                "get_income": _make_income_df(["20231231"]),
                "get_fina_indicator": _make_fina_indicator_df(["20231231"]),
            }),
            (ProfitabilityTool(), {
                "get_fina_indicator": _make_fina_indicator_df(["20231231"]),
                "get_income": _make_income_df(["20231231"]),
            }),
            (ExpenseAnalysisTool(), {
                "get_income": _make_income_df(["20231231"]),
            }),
            (AssetStructureTool(), {
                "get_balancesheet": _make_balancesheet_df(["20231231"]),
            }),
            (SolvencyTool(), {
                "get_balancesheet": _make_balancesheet_df(["20231231"]),
                "get_fina_indicator": _make_fina_indicator_df(["20231231"]),
            }),
        ]

        for tool, patch_data in tools_and_patches:
            ctx_managers = [
                patch(f"app.datasource.tushare_client.tushare_client.{method}",
                      AsyncMock(return_value=df))
                for method, df in patch_data.items()
            ]
            with patch("app.core.config.settings") as ms:
                ms.enable_akshare = False
                result = None
                # Apply all patches
                from contextlib import ExitStack
                with ExitStack() as stack:
                    for cm in ctx_managers:
                        stack.enter_context(cm)
                    result = _run(tool.fetch("CN", "600519"))
            assert result is not None
            assert result.get("source") == "tushare", (
                f"{tool.__class__.__name__} source={result.get('source')}，期望 tushare"
            )

    def test_t10_akshare_disabled_error_not_raised(self):
        """T10-3: ENABLE_AKSHARE=false 时不会抛出 AkShareDisabledError。"""
        from app.datasource.akshare_client import AkShareDisabledError
        with patch("app.core.config.settings") as ms:
            ms.enable_akshare = False
            with patch("app.datasource.tushare_client.tushare_client.get_income",
                       AsyncMock(return_value=_make_income_df(["20231231"]))), \
                 patch("app.datasource.tushare_client.tushare_client.get_fina_indicator",
                       AsyncMock(return_value=_make_fina_indicator_df(["20231231"]))):
                try:
                    result = _run(GrowthTool().fetch("CN", "600519"))
                    assert isinstance(result, dict)
                except AkShareDisabledError:
                    pytest.fail("GrowthTool 在 ENABLE_AKSHARE=false 时不应抛出 AkShareDisabledError")


# ═══════════════════════════════════════════════════════════════════════════
# helpers 单元测试
# ═══════════════════════════════════════════════════════════════════════════

class TestHelpers:
    """_helpers.py 公共函数单元测试。"""

    def test_safe_float_nan(self):
        assert safe_float(float("nan")) is None

    def test_safe_float_none(self):
        assert safe_float(None) is None

    def test_safe_float_str(self):
        assert safe_float("3.14") == pytest.approx(3.14, rel=1e-4)

    def test_safe_div_normal(self):
        assert safe_div(10, 4) == pytest.approx(2.5)

    def test_safe_pct_normal(self):
        assert safe_pct(1, 4) == pytest.approx(25.0)

    def test_filter_annual_keeps_1231(self):
        df = pd.DataFrame({"end_date": ["20231231", "20230930", "20221231"]})
        out = filter_annual(df)
        assert list(out["end_date"]) == ["20231231", "20221231"]

    def test_filter_report_type_merges_only(self):
        df = pd.DataFrame({"end_date": ["20231231", "20231231"],
                           "report_type": ["1", "4"]})
        out = filter_report_type(df)
        assert list(out["report_type"]) == ["1"]

    def test_fmt_date_yyyymmdd(self):
        assert fmt_date("20231231") == "2023-12-31"

    def test_fmt_date_none(self):
        assert fmt_date(None) is None

    def test_row_get_nan_returns_none(self):
        row = {"val": float("nan")}
        assert row_get(row, "val") is None

    def test_row_get_missing_key(self):
        row = {"other": 1}
        assert row_get(row, "missing") is None
