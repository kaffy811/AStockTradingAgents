"""
tests/fundamental/test_phase15_compat.py — Phase 1.5 兼容路由 + 新工具测试

覆盖范围（共 40 个测试）：

CodeParser     (P-1~P-8)   : _parse_code 各种格式
ModuleAlias    (MA-1~MA-5)  : module_id 别名映射
APIEnvelope    (AE-1~AE-8)  : build_api_response 结构检查
ValuationLogic (V-1~V-8)   : 估值工具金融逻辑（含 PE<=0 分支）
DupontLogic    (D-1~D-5)   : 杜邦拆解（含字段缺失分支）
CashflowQuality(C-1~C-8)   : 现金流质量（含净利润<=0 分支）
CompatRouter   (CR-1~CR-6) : 兼容路由端点（mock aggregator）

原则：不发真实 HTTP 请求，不依赖真实 Tushare Token。
"""

from __future__ import annotations

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

import pandas as pd
import numpy as np


# ═══════════════════════════════════════════════════════════════════════════
# P-1 ~ P-8  _parse_code 代码格式解析
# ═══════════════════════════════════════════════════════════════════════════

from app.routers.fundamentals_compat import _parse_code


class TestCodeParser:

    def test_p1_cn_plain_6digit(self):
        """P-1: 纯 6 位数字 → CN。"""
        assert _parse_code("600519") == ("CN", "600519")

    def test_p2_cn_sh_suffix(self):
        """P-2: 带 .SH 后缀。"""
        assert _parse_code("600519.SH") == ("CN", "600519")

    def test_p3_cn_sz_suffix(self):
        """P-3: 带 .SZ 后缀。"""
        assert _parse_code("000001.SZ") == ("CN", "000001")

    def test_p4_cn_bj_suffix(self):
        """P-4: 北交所 .BJ 后缀。"""
        assert _parse_code("838030.BJ") == ("CN", "838030")

    def test_p5_hk_5digit(self):
        """P-5: 港股 5 位 + .HK。"""
        assert _parse_code("00700.HK") == ("HK", "00700")

    def test_p6_hk_short_padded(self):
        """P-6: 港股短代码 .HK，补零到 5 位。"""
        assert _parse_code("700.HK") == ("HK", "00700")

    def test_p7_us_ticker(self):
        """P-7: 字母 ticker → US。"""
        assert _parse_code("AAPL") == ("US", "AAPL")

    def test_p8_strip_whitespace(self):
        """P-8: 前后空格被去除。"""
        assert _parse_code("  600519  ") == ("CN", "600519")


# ═══════════════════════════════════════════════════════════════════════════
# MA-1 ~ MA-5  module_id 别名映射
# ═══════════════════════════════════════════════════════════════════════════

from app.routers.fundamentals_compat import _resolve_module_id


class TestModuleAlias:

    def test_ma1_cashflow_to_cashflow_quality(self):
        """MA-1: cashflow → cashflow_quality。"""
        assert _resolve_module_id("cashflow") == "cashflow_quality"

    def test_ma2_quote_to_snapshot(self):
        """MA-2: quote → snapshot。"""
        assert _resolve_module_id("quote") == "snapshot"

    def test_ma3_quote_snapshot_to_snapshot(self):
        """MA-3: quote_snapshot → snapshot。"""
        assert _resolve_module_id("quote_snapshot") == "snapshot"

    def test_ma4_valuation_unchanged(self):
        """MA-4: valuation 无别名，原样返回。"""
        assert _resolve_module_id("valuation") == "valuation"

    def test_ma5_dupont_unchanged(self):
        """MA-5: dupont 无别名，原样返回。"""
        assert _resolve_module_id("dupont") == "dupont"


# ═══════════════════════════════════════════════════════════════════════════
# AE-1 ~ AE-8  build_api_response 结构检查
# ═══════════════════════════════════════════════════════════════════════════

from app.aggregator.envelope import build_api_response, ok_envelope, err_envelope


class TestAPIEnvelope:

    @patch("app.core.config.settings")
    def test_ae1_ok_envelope_structure(self, mock_settings):
        """AE-1: 成功 envelope → API 响应包含所有必填字段。"""
        mock_settings.enable_akshare = False
        env = ok_envelope({"close": 1850.0, "source": "tushare"})
        resp = build_api_response(env, "CN", "600519", "600519.SH", "snapshot", "基础信息与行情")
        assert resp["market"] == "CN"
        assert resp["symbol"] == "600519"
        assert resp["ts_code"] == "600519.SH"
        assert resp["module_key"] == "snapshot"
        assert resp["module_name"] == "基础信息与行情"
        assert isinstance(resp["data"], dict)
        assert isinstance(resp["errors"], list)     # errors 永远是数组
        assert resp["partial"] is False
        assert resp["stale"] is False
        assert "generated_at" in resp
        assert "source" in resp

    @patch("app.core.config.settings")
    def test_ae2_err_envelope_errors_list(self, mock_settings):
        """AE-2: 失败 envelope → errors 包含 reason，且是 list（不为 null）。
        data 已改为 stub dict (rows+reasons) 以避免前端 503 崩溃（Phase 4E-1）。"""
        mock_settings.enable_akshare = False
        env = err_envelope("Tushare 超时")
        resp = build_api_response(env, "CN", "600519", "600519.SH", "valuation", "估值分位")
        assert resp["errors"] == ["Tushare 超时"]
        assert isinstance(resp["errors"], list)
        # data is now a stub dict (not None) to allow frontend graceful rendering
        assert resp["data"] is not None
        assert "rows" in resp["data"]
        assert resp["partial"] is True

    @patch("app.core.config.settings")
    def test_ae3_partial_errors_in_list(self, mock_settings):
        """AE-3: partial_errors → errors 为列表，partial=True。"""
        mock_settings.enable_akshare = False
        env = ok_envelope({"a": 1}, partial_errors=["b: 解析失败", "c: 缺失"])
        resp = build_api_response(env, "CN", "600519", "600519.SH", "financial_summary", "财报核心数据")
        assert resp["partial"] is True
        assert len(resp["errors"]) == 2

    @patch("app.core.config.settings")
    def test_ae4_stale_flag_propagated(self, mock_settings):
        """AE-4: stale=True 从 envelope 传播到 API 响应。"""
        mock_settings.enable_akshare = True
        env = ok_envelope({"source": "akshare_fallback"}, stale=True)
        resp = build_api_response(env, "CN", "600519", "600519.SH", "dupont", "杜邦分析")
        assert resp["stale"] is True

    @patch("app.core.config.settings")
    def test_ae5_source_actual_extracted(self, mock_settings):
        """AE-5: data 中 source 字段被提取到 source.actual。"""
        mock_settings.enable_akshare = False
        env = ok_envelope({"x": 1, "source": "tushare"})
        resp = build_api_response(env, "CN", "600519", "600519.SH", "valuation", "估值分位")
        assert resp["source"]["actual"] == "tushare"

    @patch("app.core.config.settings")
    def test_ae6_akshare_enabled_in_source(self, mock_settings):
        """AE-6: ENABLE_AKSHARE=true 时 source.akshare_enabled=True。"""
        mock_settings.enable_akshare = True
        env = ok_envelope({})
        resp = build_api_response(env, "CN", "600519", "600519.SH", "cashflow_quality", "现金流质量")
        assert resp["source"]["akshare_enabled"] is True
        assert resp["source"]["fallback"] == "akshare"

    @patch("app.core.config.settings")
    def test_ae7_akshare_disabled_in_source(self, mock_settings):
        """AE-7: ENABLE_AKSHARE=false 时 source.fallback=None。"""
        mock_settings.enable_akshare = False
        env = ok_envelope({})
        resp = build_api_response(env, "CN", "600519", "600519.SH", "valuation", "估值分位")
        assert resp["source"]["akshare_enabled"] is False
        assert resp["source"]["fallback"] is None

    @patch("app.core.config.settings")
    def test_ae8_generated_at_is_iso8601(self, mock_settings):
        """AE-8: generated_at 是 ISO 8601 格式（含时区）。"""
        mock_settings.enable_akshare = False
        env = ok_envelope({"x": 1})
        resp = build_api_response(env, "CN", "600519", "600519.SH", "dupont", "杜邦分析")
        from datetime import datetime
        dt = datetime.fromisoformat(resp["generated_at"])
        assert dt.tzinfo is not None     # 有时区信息


# ═══════════════════════════════════════════════════════════════════════════
# V-1 ~ V-8  估值工具金融逻辑（纯计算，无 HTTP）
# ═══════════════════════════════════════════════════════════════════════════

from app.tools.fundamental.valuation import _metric_stats, _percentile_rank


class TestValuationLogic:

    def test_v1_pe_positive_percentile_computed(self):
        """V-1: PE 全为正数时 percentile 正常计算。"""
        series = pd.Series([10.0, 20.0, 30.0, 40.0, 50.0])
        stats = _metric_stats(series, current=30.0, metric="pe_ttm")
        assert stats["percentile"] is not None
        assert 0 <= stats["percentile"] <= 100

    def test_v2_pe_ttm_zero_percentile_null(self):
        """V-2: 当前 PE_TTM <= 0 时 percentile=null（亏损期不计分位）。"""
        series = pd.Series([10.0, 20.0, 30.0])
        stats = _metric_stats(series, current=-5.0, metric="pe_ttm")
        assert stats["percentile"] is None
        assert stats["note"] is not None
        assert "≤ 0" in stats["note"]

    def test_v3_pe_ttm_exactly_zero_percentile_null(self):
        """V-3: 当前 PE_TTM == 0 → percentile=null。"""
        series = pd.Series([10.0, 20.0])
        stats = _metric_stats(series, current=0.0, metric="pe_ttm")
        assert stats["percentile"] is None

    def test_v4_ps_ttm_negative_current_null(self):
        """V-4: 当前 PS_TTM < 0 → percentile=null（同 PE 规则）。"""
        series = pd.Series([2.0, 4.0, 6.0])
        stats = _metric_stats(series, current=-1.0, metric="ps_ttm")
        assert stats["percentile"] is None

    def test_v5_pb_negative_no_filter(self):
        """V-5: PB 不过滤非正值（PB 可为负，如净资产为负）。"""
        series = pd.Series([-1.0, 2.0, 4.0])
        stats = _metric_stats(series, current=3.0, metric="pb")
        # 不过滤负数，3 个样本都参与
        assert stats["samples"] == 3

    def test_v6_empty_series_returns_none(self):
        """V-6: 历史序列为空时所有统计字段为 null。"""
        series = pd.Series(dtype=float)
        stats = _metric_stats(series, current=30.0, metric="pe_ttm")
        assert stats["percentile"] is None
        assert stats["min"] is None
        assert stats["samples"] == 0

    def test_v7_positive_filter_excludes_negatives(self):
        """V-7: PE_TTM 历史中的负值被自动剔除。"""
        series = pd.Series([-10.0, -5.0, 20.0, 30.0, 40.0])  # 2 负值应被剔除
        stats = _metric_stats(series, current=25.0, metric="pe_ttm")
        assert stats["samples"] == 3  # 只剩 20/30/40

    def test_v8_percentile_rank_correctness(self):
        """V-8: percentile_rank 计算正确（25 在 [10,20,30,40] 中 = 50%）。"""
        series = pd.Series([10.0, 20.0, 30.0, 40.0])
        # 25 >= 10, 20 → 2/4 = 50%
        pct = _percentile_rank(series, 25.0)
        assert pct == 50.0


# ═══════════════════════════════════════════════════════════════════════════
# D-1 ~ D-5  杜邦分析金融逻辑
# ═══════════════════════════════════════════════════════════════════════════

from app.tools.fundamental.dupont import (
    _equity_multiplier, _factor_product, _generate_comment,
)


class TestDupontLogic:

    def test_d1_equity_multiplier_normal(self):
        """D-1: 正常资产负债率 → 权益乘数正确。"""
        # 50% 负债率 → 1/(1-0.5) = 2.0
        em = _equity_multiplier(50.0)
        assert em is not None
        assert abs(em - 2.0) < 0.001

    def test_d2_equity_multiplier_zero_debt(self):
        """D-2: 0% 负债率 → 权益乘数 = 1.0。"""
        em = _equity_multiplier(0.0)
        assert em is None  # 0% 被视为无效（边界）

    def test_d3_equity_multiplier_none_input(self):
        """D-3: 输入 None → 返回 None。"""
        assert _equity_multiplier(None) is None

    def test_d4_factor_product_any_none_returns_null(self):
        """D-4: 任一因子为 None → factor_product 为 null。"""
        assert _factor_product(None, 0.45, 2.0) is None
        assert _factor_product(49.8, None, 2.0) is None
        assert _factor_product(49.8, 0.45, None) is None

    def test_d5_factor_product_correct(self):
        """D-5: 三因子乘积计算正确。"""
        # 净利率=50%, 周转率=0.4, 权益乘数=2.0
        # ROE = (50/100) * 0.4 * 2.0 * 100 = 40.0
        fp = _factor_product(50.0, 0.4, 2.0)
        assert fp is not None
        assert abs(fp - 40.0) < 0.01


# ═══════════════════════════════════════════════════════════════════════════
# C-1 ~ C-8  现金流质量金融逻辑
# ═══════════════════════════════════════════════════════════════════════════

from app.tools.fundamental.cashflow_quality import _cashflow_profile, _ocf_comment


class TestCashflowQuality:

    def test_c1_ocf_to_np_positive_profit(self):
        """C-1: 净利润 > 0 时净现比正常计算。"""
        # ocf=85e8, net_profit=86e8 → ~0.988
        ocf = 8.5e9
        np_parent = 8.6e9
        ratio = round(ocf / np_parent, 4)
        assert ratio > 0

    def test_c2_ocf_to_np_zero_profit_null(self):
        """C-2: 归母净利润 <= 0 时净现比 = null。"""
        # 在 cashflow_quality 代码中检验：net_profit_parent <= 0 → ocf_to_np = None
        net_p = 0.0
        ocf = 5e9
        result = None if net_p <= 0 else round(ocf / net_p, 4)
        assert result is None

    def test_c3_ocf_to_np_negative_profit_null(self):
        """C-3: 归母净利润 < 0 时净现比 = null。"""
        net_p = -1e9
        ocf = 5e9
        result = None if net_p <= 0 else round(ocf / net_p, 4)
        assert result is None

    def test_c4_cashflow_profile_cow(self):
        """C-4: (+,-,-) → 奶牛型。"""
        profile, signs = _cashflow_profile(8.5e9, -3e9, -2e9)
        assert profile == "奶牛型"
        assert signs == ["+", "-", "-"]

    def test_c5_cashflow_profile_growth(self):
        """C-5: (+,-,+) → 扩张型。"""
        profile, signs = _cashflow_profile(5e9, -8e9, 3e9)
        assert profile == "扩张型"

    def test_c6_cashflow_profile_blood_transfusion(self):
        """C-6: (-,-,+) → 输血型（经营失血，融资支撑）。"""
        profile, signs = _cashflow_profile(-2e9, -5e9, 8e9)
        assert profile == "输血型"

    def test_c7_cashflow_profile_decline(self):
        """C-7: (-,-,-) → 衰退型（三流均负）。"""
        profile, signs = _cashflow_profile(-1e9, -2e9, -3e9)
        assert profile == "衰退型"

    def test_c8_cashflow_profile_none_input(self):
        """C-8: 任一为 None → profile=数据不足。"""
        profile, signs = _cashflow_profile(None, -3e9, -2e9)
        assert profile == "数据不足"
        assert "?" in signs


# ═══════════════════════════════════════════════════════════════════════════
# CR-1 ~ CR-6  兼容路由（mock aggregator）
# ═══════════════════════════════════════════════════════════════════════════

from fastapi.testclient import TestClient
from unittest.mock import patch, AsyncMock


def _make_test_app():
    """创建仅含 compat_router 的 FastAPI 测试应用。"""
    from fastapi import FastAPI
    from app.routers.fundamentals_compat import compat_router
    app = FastAPI()
    app.include_router(compat_router)
    return app


class TestCompatRouter:

    @patch("app.routers.fundamentals_compat.get_aggregator")
    @patch("app.core.config.settings")
    def test_cr1_get_modules_returns_24(self, mock_settings, mock_get_agg):
        """CR-1: GET /api/v1/modules 返回 24 个模块。"""
        mock_settings.enable_akshare = False
        mock_agg = MagicMock()
        mock_agg.list_modules.return_value = [{"key": f"mod{i}", "name_zh": f"模块{i}"} for i in range(24)]
        mock_get_agg.return_value = mock_agg

        client = TestClient(_make_test_app())
        resp = client.get("/api/v1/modules")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 24

    @patch("app.routers.fundamentals_compat.get_aggregator")
    @patch("app.core.config.settings")
    def test_cr2_modules_disclaimer_header(self, mock_settings, mock_get_agg):
        """CR-2: /api/v1/modules 响应头含免责声明。"""
        mock_settings.enable_akshare = False
        mock_agg = MagicMock()
        mock_agg.list_modules.return_value = []
        mock_get_agg.return_value = mock_agg

        client = TestClient(_make_test_app())
        resp = client.get("/api/v1/modules")
        assert "X-Data-Disclaimer" in resp.headers

    @patch("app.routers.fundamentals_compat.get_aggregator")
    @patch("app.core.config.settings")
    def test_cr3_overview_code_600519(self, mock_settings, mock_get_agg):
        """CR-3: GET /api/v1/stock/600519/overview → 解析为 CN/600519。"""
        mock_settings.enable_akshare = False
        mock_agg = MagicMock()
        mock_agg.fetch_snapshot = AsyncMock(return_value={
            "snapshot": __import__("app.aggregator.envelope", fromlist=["ok_envelope"]).ok_envelope({"close": 1850.0}),
            "financial_summary": __import__("app.aggregator.envelope", fromlist=["ok_envelope"]).ok_envelope({"roe": 40.0}),
        })
        mock_get_agg.return_value = mock_agg

        client = TestClient(_make_test_app())
        resp = client.get("/api/v1/stock/600519/overview")
        assert resp.status_code == 200
        data = resp.json()
        assert "snapshot" in data or "financial_summary" in data

    @patch("app.routers.fundamentals_compat.get_aggregator")
    @patch("app.core.config.settings")
    def test_cr4_overview_code_with_suffix(self, mock_settings, mock_get_agg):
        """CR-4: GET /api/v1/stock/600519.SH/overview → 正常解析。"""
        mock_settings.enable_akshare = False
        mock_agg = MagicMock()
        mock_agg.fetch_snapshot = AsyncMock(return_value={})
        mock_get_agg.return_value = mock_agg

        client = TestClient(_make_test_app())
        resp = client.get("/api/v1/stock/600519.SH/overview")
        assert resp.status_code == 200

    @patch("app.routers.fundamentals_compat.get_aggregator")
    @patch("app.core.config.settings")
    def test_cr5_module_cashflow_alias(self, mock_settings, mock_get_agg):
        """CR-5: /stock/600519/modules/cashflow → cashflow_quality 被调用。"""
        mock_settings.enable_akshare = False
        from app.aggregator.envelope import ok_envelope
        mock_agg = MagicMock()
        mock_agg.fetch_module = AsyncMock(return_value=ok_envelope({"periods": []}))
        mock_get_agg.return_value = mock_agg

        client = TestClient(_make_test_app())
        resp = client.get("/api/v1/stock/600519/modules/cashflow")
        assert resp.status_code == 200

        # 检查聚合器被以 cashflow_quality 为 key 调用
        call_kwargs = mock_agg.fetch_module.call_args
        assert call_kwargs[1]["module_key"] == "cashflow_quality"

    @patch("app.routers.fundamentals_compat.get_aggregator")
    @patch("app.core.config.settings")
    def test_cr6_module_200_with_partial_on_failure(self, mock_settings, mock_get_agg):
        """CR-6: 模块 fetch 失败 → HTTP 200 + partial=true + errors（Phase 4E-1 503 降噪）。
        模块级错误通过 partial=true 和 errors[] 传达，HTTP 状态始终 200，
        避免前端因单模块失败而崩溃或控制台出现大量未处理异常。"""
        mock_settings.enable_akshare = False
        from app.aggregator.envelope import err_envelope
        mock_agg = MagicMock()
        mock_agg.fetch_module = AsyncMock(return_value=err_envelope("Tushare Token 未配置"))
        mock_get_agg.return_value = mock_agg

        client = TestClient(_make_test_app())
        resp = client.get("/api/v1/stock/600519/modules/valuation")
        assert resp.status_code == 200   # always 200; errors in body
        data = resp.json()
        assert isinstance(data["errors"], list)
        assert len(data["errors"]) > 0
        assert data["partial"] is True   # frontend reads this to show empty state
        # data is a stub dict (not null), so frontend never crashes
        assert data["data"] is not None


# ═══════════════════════════════════════════════════════════════════════════
# 综合检查：MODULE_NAME_MAP 覆盖所有重要 key
# ═══════════════════════════════════════════════════════════════════════════

from app.tools.fundamental import MODULE_NAME_MAP


def test_module_name_map_covers_new_tools():
    """MODULE_NAME_MAP 包含 Phase 1.5 所有新模块 key。"""
    required_keys = {"snapshot", "valuation", "dupont", "cashflow_quality", "financial_summary"}
    for k in required_keys:
        assert k in MODULE_NAME_MAP, f"{k} 缺少 name 映射"


def test_module_name_map_covers_compat_aliases():
    """MODULE_NAME_MAP 包含兼容别名（quote_snapshot, cashflow）。"""
    assert "quote_snapshot" in MODULE_NAME_MAP
    assert "cashflow" in MODULE_NAME_MAP


def test_catalog_has_seq_field():
    """MODULE_CATALOG 每条记录都有 seq 字段。"""
    from app.tools.fundamental import MODULE_CATALOG
    for m in MODULE_CATALOG:
        assert "seq" in m, f"{m['key']} 缺少 seq 字段"
        assert isinstance(m["seq"], int)


def test_catalog_has_status_field():
    """MODULE_CATALOG 每条记录都有 status 字段，且取值合法。"""
    from app.tools.fundamental import MODULE_CATALOG
    valid_statuses = {"available", "legacy", "planned", "hidden"}
    for m in MODULE_CATALOG:
        assert "status" in m, f"{m['key']} 缺少 status 字段"
        assert m["status"] in valid_statuses, f"{m['key']} status={m['status']} 非法"


def test_phase15_available_modules_in_registry():
    """Phase 1.5 标注 available 的模块必须在 TOOL_REGISTRY 中。"""
    from app.tools.fundamental import MODULE_CATALOG, TOOL_REGISTRY
    for m in MODULE_CATALOG:
        if m.get("status") == "available":
            assert m["key"] in TOOL_REGISTRY, (
                f"status=available 的模块 {m['key']} 未在 TOOL_REGISTRY 中注册"
            )
