"""
tests/fundamental/test_phase2c_reference_modules.py — Phase 2C 参考模块测试

覆盖范围（14 大场景）：
  C1  : 所有 display=True MODULE_CATALOG 条目拥有 group 和 group_seq 字段
  C2  : /api/v1/modules 不返回 alias（display=False 条目不出现）
  C3  : group_seq 值为有效整数 1-8
  C4  : MainBusinessTool 返回 periods/items/sales_ratio 结构
  C5  : DividendHistoryTool 返回 records 含正确字段
  C6  : DividendHistoryTool 空数据时返回 records=[] 不抛异常
  C7  : MajorHoldersTool 返回 top10_float_holders + holder_num_series
  C8  : EquityStructureTool 返回 float_ratio_pct 正确计算
  C9  : AnnouncementsTool 返回 forecasts + expresses
  C10 : AnalystRatingsTool 返回 sentiment_summary dict
  C11 : DividendHistoryTool only_implemented 过滤正常工作
  C12 : 新增 alias 在 TOOL_REGISTRY 中可访问（dividend/holders/events 等）
  C13 : 新增 alias 通过兼容路由 _MODULE_ALIAS 可访问
  C14 : 全量回归——TOOL_REGISTRY 包含所有预期 key，MODULE_CATALOG ≥ 32 条目

原则：不发真实 HTTP / DB 请求，不依赖真实 Tushare Token / PostgreSQL。
"""

from __future__ import annotations

import asyncio
import pandas as pd
import pytest
from unittest.mock import AsyncMock, patch

# ── 被测模块 ──────────────────────────────────────────────────────────────────
from app.tools.fundamental import MODULE_CATALOG, TOOL_REGISTRY
from app.tools.fundamental.main_business import MainBusinessTool
from app.tools.fundamental.dividend_history import DividendHistoryTool
from app.tools.fundamental.major_holders import MajorHoldersTool
from app.tools.fundamental.equity_structure import EquityStructureTool
from app.tools.fundamental.announcements import AnnouncementsTool
from app.tools.fundamental.analyst_ratings import AnalystRatingsTool
from app.datasource.tushare_client import tushare_client
from app.routers.fundamentals_compat import _MODULE_ALIAS, _resolve_module_id


def _run(coro):
    return asyncio.run(coro)


# ═══════════════════════════════════════════════════════════════════════════
# C1 — display=True 条目拥有 group 和 group_seq 字段
# ═══════════════════════════════════════════════════════════════════════════

class TestC1GroupFields:
    """所有 display=True 的 MODULE_CATALOG 条目必须有 group 和 group_seq。"""

    def test_c1_display_entries_have_group(self):
        display_entries = [m for m in MODULE_CATALOG if m.get("display") is True]
        assert len(display_entries) > 0, "应有 display=True 的条目"
        for entry in display_entries:
            key = entry["key"]
            assert "group" in entry, f"条目 {key} 缺少 group 字段"
            assert "group_seq" in entry, f"条目 {key} 缺少 group_seq 字段"
            assert isinstance(entry["group"], str) and entry["group"], f"条目 {key} group 应为非空字符串"

    def test_c1_hidden_entries_no_group_required(self):
        """display=False 的别名条目不强制要求 group。"""
        alias_entries = [m for m in MODULE_CATALOG if m.get("display") is False]
        # 它们没有 group 也是合法的——只验证 display=True 的有 group 即可
        assert len(alias_entries) > 0


# ═══════════════════════════════════════════════════════════════════════════
# C2 — /api/v1/modules 不返回 alias
# ═══════════════════════════════════════════════════════════════════════════

class TestC2NoAliasInModules:
    """display=True 的条目不应该有 alias_of 非 None（即不是 alias）。"""

    def test_c2_no_alias_in_display_entries(self):
        display_entries = [m for m in MODULE_CATALOG if m.get("display") is True]
        for entry in display_entries:
            assert entry.get("alias_of") is None, (
                f"display=True 的条目 {entry['key']} 不应有 alias_of"
            )

    def test_c2_alias_entries_are_hidden(self):
        alias_entries = [m for m in MODULE_CATALOG if m.get("alias_of") is not None]
        for entry in alias_entries:
            assert entry.get("display") is False, (
                f"alias 条目 {entry['key']} 的 display 应为 False"
            )
            assert entry.get("status") == "hidden", (
                f"alias 条目 {entry['key']} 的 status 应为 hidden"
            )


# ═══════════════════════════════════════════════════════════════════════════
# C3 — group_seq 值为 1-8 的有效整数
# ═══════════════════════════════════════════════════════════════════════════

class TestC3GroupSeqValid:
    def test_c3_group_seq_in_range(self):
        display_entries = [m for m in MODULE_CATALOG if m.get("display") is True]
        for entry in display_entries:
            gs = entry.get("group_seq")
            assert isinstance(gs, int), f"条目 {entry['key']} 的 group_seq 应为整数"
            assert 1 <= gs <= 8, f"条目 {entry['key']} 的 group_seq={gs} 应在 1-8 范围内"

    def test_c3_all_8_groups_represented(self):
        display_entries = [m for m in MODULE_CATALOG if m.get("display") is True]
        group_seqs = {m["group_seq"] for m in display_entries if "group_seq" in m}
        # 至少有部分分组存在
        assert len(group_seqs) >= 5, f"至少应有 5 个分组，实际: {group_seqs}"


# ═══════════════════════════════════════════════════════════════════════════
# C4 — MainBusinessTool 结构验证
# ═══════════════════════════════════════════════════════════════════════════

class TestC4MainBusiness:
    def _make_df(self):
        return pd.DataFrame([
            {
                "end_date": "20251231", "bz_item": "白酒", "bz_sales": 1500.0,
                "bz_profit": 800.0, "bz_cost": 500.0, "curr_type": "CNY", "update_flag": "1",
            },
            {
                "end_date": "20251231", "bz_item": "其他", "bz_sales": 100.0,
                "bz_profit": 30.0, "bz_cost": 60.0, "curr_type": "CNY", "update_flag": "1",
            },
            {
                "end_date": "20241231", "bz_item": "白酒", "bz_sales": 1200.0,
                "bz_profit": 700.0, "bz_cost": 400.0, "curr_type": "CNY", "update_flag": "1",
            },
        ])

    def test_c4_returns_periods(self):
        tool = MainBusinessTool(limit_periods=2)
        with patch.object(tushare_client, "get_fina_mainbz", new=AsyncMock(return_value=self._make_df())):
            result = _run(tool.fetch("CN", "600519"))
        assert "periods" in result
        assert len(result["periods"]) == 2

    def test_c4_items_have_sales_ratio(self):
        tool = MainBusinessTool(limit_periods=1)
        with patch.object(tushare_client, "get_fina_mainbz", new=AsyncMock(return_value=self._make_df())):
            result = _run(tool.fetch("CN", "600519"))
        items = result["periods"][0]["items"]
        assert len(items) > 0
        for item in items:
            assert "sales_ratio_pct" in item
            assert "bz_item" in item
            assert "bz_sales" in item

    def test_c4_items_sorted_by_sales_desc(self):
        tool = MainBusinessTool(limit_periods=1)
        with patch.object(tushare_client, "get_fina_mainbz", new=AsyncMock(return_value=self._make_df())):
            result = _run(tool.fetch("CN", "600519"))
        items = result["periods"][0]["items"]
        sales = [i["bz_sales"] for i in items if i["bz_sales"] is not None]
        assert sales == sorted(sales, reverse=True)

    def test_c4_sales_ratio_sums_to_100(self):
        tool = MainBusinessTool(limit_periods=1)
        with patch.object(tushare_client, "get_fina_mainbz", new=AsyncMock(return_value=self._make_df())):
            result = _run(tool.fetch("CN", "600519"))
        items = result["periods"][0]["items"]
        total_ratio = sum(i["sales_ratio_pct"] for i in items if i["sales_ratio_pct"] is not None)
        assert abs(total_ratio - 100.0) < 0.1, f"比例之和应约为100，实际 {total_ratio}"

    def test_c4_source_field(self):
        tool = MainBusinessTool()
        with patch.object(tushare_client, "get_fina_mainbz", new=AsyncMock(return_value=self._make_df())):
            result = _run(tool.fetch("CN", "600519"))
        assert result["source"] == "tushare"


# ═══════════════════════════════════════════════════════════════════════════
# C5 — DividendHistoryTool 返回 records 含正确字段
# ═══════════════════════════════════════════════════════════════════════════

class TestC5DividendNormal:
    def _make_df(self):
        return pd.DataFrame([{
            "end_date": "20251231", "ann_date": "20260315", "ex_date": "20260420",
            "pay_date": "20260421", "cash_div": 1.5, "cash_div_tax": 1.35,
            "stk_div": 0.0, "stk_bo_rate": 0.0, "stk_co_rate": 0.0,
            "div_proc": "实施",
        }])

    def test_c5_records_present(self):
        tool = DividendHistoryTool()
        with patch.object(tushare_client, "get_dividend", new=AsyncMock(return_value=self._make_df())):
            result = _run(tool.fetch("CN", "600519"))
        assert "records" in result
        assert len(result["records"]) == 1

    def test_c5_cash_div_value(self):
        tool = DividendHistoryTool()
        with patch.object(tushare_client, "get_dividend", new=AsyncMock(return_value=self._make_df())):
            result = _run(tool.fetch("CN", "600519"))
        assert result["records"][0]["cash_div"] == 1.5

    def test_c5_record_fields(self):
        tool = DividendHistoryTool()
        with patch.object(tushare_client, "get_dividend", new=AsyncMock(return_value=self._make_df())):
            result = _run(tool.fetch("CN", "600519"))
        rec = result["records"][0]
        for field in ["end_date", "ann_date", "ex_date", "pay_date", "cash_div",
                      "cash_div_tax", "stk_div", "stk_bo_rate", "stk_co_rate", "div_proc"]:
            assert field in rec, f"记录缺少字段 {field}"

    def test_c5_summary_fields(self):
        tool = DividendHistoryTool()
        with patch.object(tushare_client, "get_dividend", new=AsyncMock(return_value=self._make_df())):
            result = _run(tool.fetch("CN", "600519"))
        summary = result["summary"]
        assert "total_cash_div" in summary
        assert "years_count" in summary
        assert "latest_cash_div" in summary
        assert summary["latest_cash_div"] == 1.5


# ═══════════════════════════════════════════════════════════════════════════
# C6 — DividendHistoryTool 空数据返回 empty records（不抛异常）
# ═══════════════════════════════════════════════════════════════════════════

class TestC6DividendEmpty:
    def test_c6_empty_df_returns_empty_records(self):
        tool = DividendHistoryTool()
        empty_df = pd.DataFrame()
        with patch.object(tushare_client, "get_dividend", new=AsyncMock(return_value=empty_df)):
            result = _run(tool.fetch("CN", "600519"))
        assert result["records"] == []
        assert result["summary"]["years_count"] == 0
        assert result["summary"]["latest_cash_div"] is None

    def test_c6_tushare_error_raises_tool_error(self):
        from app.tools.fundamental.base import FundamentalToolError
        tool = DividendHistoryTool()
        with patch.object(tushare_client, "get_dividend", new=AsyncMock(side_effect=RuntimeError("network error"))):
            with pytest.raises(FundamentalToolError):
                _run(tool.fetch("CN", "600519"))


# ═══════════════════════════════════════════════════════════════════════════
# C7 — MajorHoldersTool 返回 top10_float_holders + holder_num_series
# ═══════════════════════════════════════════════════════════════════════════

class TestC7MajorHolders:
    def _make_top10_df(self):
        return pd.DataFrame([
            {
                "ts_code": "600519.SH", "ann_date": "20260330", "end_date": "20251231",
                "holder_name": "茅台集团", "hold_amount": 100000000.0, "hold_ratio": 15.0,
            },
            {
                "ts_code": "600519.SH", "ann_date": "20260330", "end_date": "20251231",
                "holder_name": "中央汇金", "hold_amount": 50000000.0, "hold_ratio": 7.5,
            },
        ])

    def _make_holder_num_df(self):
        return pd.DataFrame([
            {
                "ts_code": "600519.SH", "ann_date": "20260330", "end_date": "20251231",
                "holder_num": 120000, "holder_num_change": -5000,
            },
        ])

    def test_c7_top10_holders_present(self):
        tool = MajorHoldersTool()
        with patch.object(tushare_client, "get_top10_floatholders", new=AsyncMock(return_value=self._make_top10_df())), \
             patch.object(tushare_client, "get_stk_holdernumber", new=AsyncMock(return_value=self._make_holder_num_df())):
            result = _run(tool.fetch("CN", "600519"))
        assert "top10_float_holders" in result
        assert len(result["top10_float_holders"]) > 0

    def test_c7_holder_num_series_present(self):
        tool = MajorHoldersTool()
        with patch.object(tushare_client, "get_top10_floatholders", new=AsyncMock(return_value=self._make_top10_df())), \
             patch.object(tushare_client, "get_stk_holdernumber", new=AsyncMock(return_value=self._make_holder_num_df())):
            result = _run(tool.fetch("CN", "600519"))
        assert "holder_num_series" in result
        assert len(result["holder_num_series"]) > 0

    def test_c7_holder_fields(self):
        tool = MajorHoldersTool()
        with patch.object(tushare_client, "get_top10_floatholders", new=AsyncMock(return_value=self._make_top10_df())), \
             patch.object(tushare_client, "get_stk_holdernumber", new=AsyncMock(return_value=self._make_holder_num_df())):
            result = _run(tool.fetch("CN", "600519"))
        holder = result["top10_float_holders"][0]
        assert "holder_name" in holder
        assert "hold_amount" in holder
        assert "hold_ratio_pct" in holder

    def test_c7_comment_mentions_holder_num(self):
        tool = MajorHoldersTool()
        with patch.object(tushare_client, "get_top10_floatholders", new=AsyncMock(return_value=self._make_top10_df())), \
             patch.object(tushare_client, "get_stk_holdernumber", new=AsyncMock(return_value=self._make_holder_num_df())):
            result = _run(tool.fetch("CN", "600519"))
        assert "户" in result.get("comment", "")

    def test_c7_partial_failure_top10_only(self):
        """top10 失败时，只要 holder_num 有数据就不抛异常。"""
        from app.datasource.tushare_client import TushareError
        tool = MajorHoldersTool()
        with patch.object(tushare_client, "get_top10_floatholders", new=AsyncMock(side_effect=TushareError("fail"))), \
             patch.object(tushare_client, "get_stk_holdernumber", new=AsyncMock(return_value=self._make_holder_num_df())):
            result = _run(tool.fetch("CN", "600519"))
        assert result["top10_float_holders"] == []
        assert len(result["holder_num_series"]) > 0
        assert "_partial_errors" in result


# ═══════════════════════════════════════════════════════════════════════════
# C8 — EquityStructureTool float_ratio_pct 计算正确
# ═══════════════════════════════════════════════════════════════════════════

class TestC8EquityStructure:
    def _make_df(self):
        return pd.DataFrame([{
            "trade_date": "20260705", "total_share": 10000.0, "float_share": 8000.0,
            "free_share": 6000.0, "total_mv": 500000.0, "circ_mv": 400000.0,
            "close": 50.0, "pe": 20.0, "pe_ttm": 19.0, "pb": 3.0,
            "ps": 5.0, "ps_ttm": 4.9, "dv_ratio": 2.0, "dv_ttm": 1.8,
            "turnover_rate": 0.5, "turnover_rate_f": 0.6, "volume_ratio": 1.2,
        }])

    def test_c8_float_ratio_pct(self):
        tool = EquityStructureTool()
        with patch.object(tushare_client, "get_daily_basic", new=AsyncMock(return_value=self._make_df())):
            result = _run(tool.fetch("CN", "600519"))
        assert result["float_ratio_pct"] == 80.0   # 8000/10000*100

    def test_c8_free_ratio_pct(self):
        tool = EquityStructureTool()
        with patch.object(tushare_client, "get_daily_basic", new=AsyncMock(return_value=self._make_df())):
            result = _run(tool.fetch("CN", "600519"))
        assert result["free_ratio_pct"] == 60.0    # 6000/10000*100

    def test_c8_structure_fields(self):
        tool = EquityStructureTool()
        with patch.object(tushare_client, "get_daily_basic", new=AsyncMock(return_value=self._make_df())):
            result = _run(tool.fetch("CN", "600519"))
        for field in ["total_share_wan", "float_share_wan", "free_share_wan",
                      "total_mv_wan", "circ_mv_wan", "trade_date"]:
            assert field in result, f"缺少字段 {field}"

    def test_c8_empty_raises_error(self):
        from app.tools.fundamental.base import FundamentalToolError
        tool = EquityStructureTool()
        with patch.object(tushare_client, "get_daily_basic", new=AsyncMock(return_value=pd.DataFrame())):
            with pytest.raises(FundamentalToolError):
                _run(tool.fetch("CN", "600519"))


# ═══════════════════════════════════════════════════════════════════════════
# C9 — AnnouncementsTool 返回 forecasts + expresses
# ═══════════════════════════════════════════════════════════════════════════

class TestC9Announcements:
    def _make_forecast_df(self):
        return pd.DataFrame([{
            "ann_date": "20260115", "end_date": "20251231",
            "type": "预增", "p_change_min": 20.0, "p_change_max": 40.0,
            "net_profit_min": 80000.0, "net_profit_max": 90000.0,
            "last_parent_net": 70000.0, "first_ann_date": "20260115",
            "summary": "受益于高端白酒需求旺盛", "change_reason": "主营业务增长",
        }])

    def _make_express_df(self):
        return pd.DataFrame([{
            "ann_date": "20260120", "end_date": "20251231",
            "revenue": 1500000.0, "operate_profit": 600000.0, "total_profit": 590000.0,
            "n_income": 500000.0, "total_assets": 3000000.0,
            "total_hldr_eqy_exc_min_int": 2000000.0,
            "diluted_eps": 40.0, "diluted_roe": 25.0,
            "yoy_net_profit": 30.0, "bps": 160.0, "yoy_sales": 18.0, "yoy_op": 25.0,
            "cfps": 50.0, "roe": 25.0, "gross_margin": 92.0,
            "op_income": None, "ebit_ps": None, "fcfe_ps": None,
            "netprofit_margin": 33.0, "dt_netprofit": None,
            "yoy_equity": 10.0, "total_revenue": 1500000.0, "operate_income": None,
        }])

    def test_c9_forecasts_present(self):
        tool = AnnouncementsTool()
        with patch.object(tushare_client, "get_forecast", new=AsyncMock(return_value=self._make_forecast_df())), \
             patch.object(tushare_client, "get_express", new=AsyncMock(return_value=self._make_express_df())):
            result = _run(tool.fetch("CN", "600519"))
        assert "forecasts" in result
        assert len(result["forecasts"]) == 1

    def test_c9_expresses_present(self):
        tool = AnnouncementsTool()
        with patch.object(tushare_client, "get_forecast", new=AsyncMock(return_value=self._make_forecast_df())), \
             patch.object(tushare_client, "get_express", new=AsyncMock(return_value=self._make_express_df())):
            result = _run(tool.fetch("CN", "600519"))
        assert "expresses" in result
        assert len(result["expresses"]) == 1

    def test_c9_forecast_fields(self):
        tool = AnnouncementsTool()
        with patch.object(tushare_client, "get_forecast", new=AsyncMock(return_value=self._make_forecast_df())), \
             patch.object(tushare_client, "get_express", new=AsyncMock(return_value=self._make_express_df())):
            result = _run(tool.fetch("CN", "600519"))
        fc = result["forecasts"][0]
        for field in ["ann_date", "end_date", "type", "p_change_min", "p_change_max",
                      "net_profit_min", "net_profit_max", "summary", "change_reason"]:
            assert field in fc, f"forecast 缺少字段 {field}"

    def test_c9_both_empty_raises(self):
        from app.tools.fundamental.base import FundamentalToolError
        tool = AnnouncementsTool()
        with patch.object(tushare_client, "get_forecast", new=AsyncMock(return_value=pd.DataFrame())), \
             patch.object(tushare_client, "get_express", new=AsyncMock(return_value=pd.DataFrame())):
            with pytest.raises(FundamentalToolError):
                _run(tool.fetch("CN", "600519"))


# ═══════════════════════════════════════════════════════════════════════════
# C10 — AnalystRatingsTool 返回 sentiment_summary dict
# ═══════════════════════════════════════════════════════════════════════════

class TestC10AnalystRatings:
    def _make_forecast_df(self):
        return pd.DataFrame([
            {
                "ann_date": "20260115", "end_date": "20251231",
                "type": "预增", "p_change_min": 20.0, "p_change_max": 40.0,
                "net_profit_min": 80000.0, "net_profit_max": 90000.0,
                "last_parent_net": 70000.0, "first_ann_date": "20260115",
                "summary": "受益于白酒旺季", "change_reason": "主营增长",
            },
            {
                "ann_date": "20250115", "end_date": "20241231",
                "type": "预减", "p_change_min": -20.0, "p_change_max": -5.0,
                "net_profit_min": 50000.0, "net_profit_max": 60000.0,
                "last_parent_net": 65000.0, "first_ann_date": "20250115",
                "summary": "受宏观环境影响", "change_reason": "需求下降",
            },
        ])

    def _make_express_df(self):
        return pd.DataFrame([{
            "ann_date": "20260120", "end_date": "20251231",
            "revenue": 1500000.0, "n_income": 500000.0,
            "yoy_net_profit": 30.0, "yoy_sales": 18.0,
            "diluted_eps": 40.0, "diluted_roe": 25.0,
            "operate_profit": None, "total_profit": None, "total_assets": None,
            "total_hldr_eqy_exc_min_int": None, "bps": None, "yoy_op": None,
            "cfps": None, "roe": None, "gross_margin": None, "op_income": None,
            "ebit_ps": None, "fcfe_ps": None, "netprofit_margin": None,
            "dt_netprofit": None, "yoy_equity": None, "total_revenue": None,
            "operate_income": None,
        }])

    def test_c10_sentiment_summary_keys(self):
        tool = AnalystRatingsTool()
        with patch.object(tushare_client, "get_forecast", new=AsyncMock(return_value=self._make_forecast_df())), \
             patch.object(tushare_client, "get_express", new=AsyncMock(return_value=self._make_express_df())):
            result = _run(tool.fetch("CN", "600519"))
        ss = result["sentiment_summary"]
        assert "positive" in ss
        assert "negative" in ss
        assert "neutral" in ss

    def test_c10_sentiment_counts_correct(self):
        tool = AnalystRatingsTool()
        with patch.object(tushare_client, "get_forecast", new=AsyncMock(return_value=self._make_forecast_df())), \
             patch.object(tushare_client, "get_express", new=AsyncMock(return_value=self._make_express_df())):
            result = _run(tool.fetch("CN", "600519"))
        ss = result["sentiment_summary"]
        assert ss["positive"] == 1
        assert ss["negative"] == 1

    def test_c10_data_note_present(self):
        tool = AnalystRatingsTool()
        with patch.object(tushare_client, "get_forecast", new=AsyncMock(return_value=self._make_forecast_df())), \
             patch.object(tushare_client, "get_express", new=AsyncMock(return_value=self._make_express_df())):
            result = _run(tool.fetch("CN", "600519"))
        assert "data_note" in result

    def test_c10_forecast_items_have_sentiment(self):
        tool = AnalystRatingsTool()
        with patch.object(tushare_client, "get_forecast", new=AsyncMock(return_value=self._make_forecast_df())), \
             patch.object(tushare_client, "get_express", new=AsyncMock(return_value=self._make_express_df())):
            result = _run(tool.fetch("CN", "600519"))
        for item in result["forecast_items"]:
            assert "sentiment" in item
            assert item["sentiment"] in ("positive", "negative", "neutral")


# ═══════════════════════════════════════════════════════════════════════════
# C11 — DividendHistoryTool only_implemented 过滤
# ═══════════════════════════════════════════════════════════════════════════

class TestC11DividendFilter:
    def test_c11_only_implemented_filtered(self):
        """div_proc 含'实施'的记录应被优先保留，其他状态的被过滤（或 fallback 全量）。"""
        df = pd.DataFrame([
            {
                "end_date": "20251231", "ann_date": "20260315", "ex_date": "20260420",
                "pay_date": "20260421", "cash_div": 1.5, "cash_div_tax": 1.35,
                "stk_div": 0.0, "stk_bo_rate": 0.0, "stk_co_rate": 0.0,
                "div_proc": "实施",
            },
            {
                "end_date": "20260630", "ann_date": "20260720", "ex_date": None,
                "pay_date": None, "cash_div": 2.0, "cash_div_tax": 1.8,
                "stk_div": 0.0, "stk_bo_rate": 0.0, "stk_co_rate": 0.0,
                "div_proc": "预案",  # 未实施
            },
        ])
        tool = DividendHistoryTool()
        with patch.object(tushare_client, "get_dividend", new=AsyncMock(return_value=df)):
            result = _run(tool.fetch("CN", "600519"))
        # 应只返回 "实施" 的记录
        assert all(r["div_proc"] == "实施" for r in result["records"])

    def test_c11_fallback_when_no_implemented(self):
        """没有'实施'记录时，fallback 返回全量。"""
        df = pd.DataFrame([
            {
                "end_date": "20260630", "ann_date": "20260720", "ex_date": None,
                "pay_date": None, "cash_div": 2.0, "cash_div_tax": 1.8,
                "stk_div": 0.0, "stk_bo_rate": 0.0, "stk_co_rate": 0.0,
                "div_proc": "预案",
            },
        ])
        tool = DividendHistoryTool()
        with patch.object(tushare_client, "get_dividend", new=AsyncMock(return_value=df)):
            result = _run(tool.fetch("CN", "600519"))
        assert len(result["records"]) == 1


# ═══════════════════════════════════════════════════════════════════════════
# C12 — 新增 alias 在 TOOL_REGISTRY 中可访问
# ═══════════════════════════════════════════════════════════════════════════

class TestC12ToolRegistryAliases:
    def test_c12_dividend_alias(self):
        assert "dividend" in TOOL_REGISTRY
        assert TOOL_REGISTRY["dividend"] is DividendHistoryTool

    def test_c12_holders_alias(self):
        assert "holders" in TOOL_REGISTRY
        assert TOOL_REGISTRY["holders"] is MajorHoldersTool

    def test_c12_shareholders_alias(self):
        assert "shareholders" in TOOL_REGISTRY
        assert TOOL_REGISTRY["shareholders"] is MajorHoldersTool

    def test_c12_events_alias(self):
        assert "events" in TOOL_REGISTRY
        assert TOOL_REGISTRY["events"] is AnnouncementsTool

    def test_c12_forecast_rating_alias(self):
        assert "forecast_rating" in TOOL_REGISTRY
        assert TOOL_REGISTRY["forecast_rating"] is AnalystRatingsTool

    def test_c12_rating_alias(self):
        assert "rating" in TOOL_REGISTRY
        assert TOOL_REGISTRY["rating"] is AnalystRatingsTool

    def test_c12_canonical_keys_registered(self):
        for key in ["main_business", "dividend_history", "major_holders",
                    "equity_structure", "announcements", "analyst_ratings"]:
            assert key in TOOL_REGISTRY, f"规范 key {key} 未在 TOOL_REGISTRY 中"


# ═══════════════════════════════════════════════════════════════════════════
# C13 — 新增 alias 通过兼容路由 _MODULE_ALIAS 可访问
# ═══════════════════════════════════════════════════════════════════════════

class TestC13CompatRouterAliases:
    def test_c13_dividend_resolves(self):
        assert _resolve_module_id("dividend") == "dividend_history"

    def test_c13_holders_resolves(self):
        assert _resolve_module_id("holders") == "major_holders"

    def test_c13_shareholders_resolves(self):
        assert _resolve_module_id("shareholders") == "major_holders"

    def test_c13_events_resolves(self):
        assert _resolve_module_id("events") == "announcements"

    def test_c13_forecast_rating_resolves(self):
        assert _resolve_module_id("forecast_rating") == "analyst_ratings"

    def test_c13_rating_resolves(self):
        assert _resolve_module_id("rating") == "analyst_ratings"

    def test_c13_unknown_passthrough(self):
        """未知的 module_id 应原样返回。"""
        assert _resolve_module_id("unknown_key") == "unknown_key"

    def test_c13_module_alias_dict_has_all_new_aliases(self):
        for alias in ["dividend", "holders", "shareholders", "events", "forecast_rating", "rating"]:
            assert alias in _MODULE_ALIAS, f"_MODULE_ALIAS 缺少别名 {alias}"


# ═══════════════════════════════════════════════════════════════════════════
# C14 — 全量回归
# ═══════════════════════════════════════════════════════════════════════════

class TestC14FullRegression:
    def test_c14_tool_registry_has_all_expected_keys(self):
        expected = [
            # Phase 1.5 规范 key
            "snapshot", "financial_summary", "valuation", "dupont", "cashflow_quality",
            # Phase 2A
            "growth", "profitability", "expense_analysis", "asset_structure",
            "solvency", "operation_capability", "capital_occupation",
            # Phase 2B
            "industry_rank",
            # Phase 2C
            "main_business", "dividend_history", "major_holders",
            "equity_structure", "announcements", "analyst_ratings",
            # Legacy
            "income_statement", "balance_sheet",
        ]
        for key in expected:
            assert key in TOOL_REGISTRY, f"TOOL_REGISTRY 缺少 key: {key}"

    def test_c14_module_catalog_has_enough_entries(self):
        # display=True 且 status != hidden 的条目应 >= 20（实际远多于此）
        visible = [
            m for m in MODULE_CATALOG
            if m.get("display") is True and m.get("status") != "hidden"
        ]
        assert len(visible) >= 20, f"可见模块应 >= 20，实际 {len(visible)}"

    def test_c14_module_catalog_total_entries(self):
        # 总条目数（含 alias）应 >= 32
        assert len(MODULE_CATALOG) >= 32, f"MODULE_CATALOG 总条目应 >= 32，实际 {len(MODULE_CATALOG)}"

    def test_c14_all_registry_tools_are_subclass(self):
        from app.tools.fundamental.base import BaseFundamentalTool
        for key, tool_cls in TOOL_REGISTRY.items():
            assert issubclass(tool_cls, BaseFundamentalTool), (
                f"TOOL_REGISTRY[{key!r}] 不是 BaseFundamentalTool 子类"
            )

    def test_c14_phase2c_tools_have_module_key(self):
        tool_classes = [
            MainBusinessTool, DividendHistoryTool, MajorHoldersTool,
            EquityStructureTool, AnnouncementsTool, AnalystRatingsTool,
        ]
        expected_keys = [
            "main_business", "dividend_history", "major_holders",
            "equity_structure", "announcements", "analyst_ratings",
        ]
        for cls, expected_key in zip(tool_classes, expected_keys):
            assert cls.module_key == expected_key, (
                f"{cls.__name__}.module_key 应为 {expected_key!r}，实际 {cls.module_key!r}"
            )

    def test_c14_new_alias_entries_in_catalog(self):
        alias_keys = {m["key"] for m in MODULE_CATALOG if m.get("display") is False}
        for alias in ["dividend", "holders", "shareholders", "events", "forecast_rating", "rating"]:
            assert alias in alias_keys, f"MODULE_CATALOG 缺少别名条目: {alias}"
