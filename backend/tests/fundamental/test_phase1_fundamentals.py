"""
tests/fundamental/test_phase1_fundamentals.py — Phase 1 基本面服务单元测试

测试覆盖（共 35 个）：

EnvelopeTests (E-1~E-10)：DataEnvelope 构建函数
TsCodeTests   (T-1~T-10)：ts_code 转换工具
RateLimiterTests (R-1~R-5)：令牌桶速率限制器
AggregatorTests  (A-1~A-7)：聚合器（mock tool / mock redis）
ToolBaseTests    (B-1~B-3)：BaseFundamentalTool.fetch_with_fallback

原则：
- 不发真实 HTTP 请求（所有 Tushare / AkShare 调用均 mock）
- 不依赖 PostgreSQL / Redis（聚合器缓存路径 mock 掉）
- 不使用 LLM（Phase 1 工具无 LLM 调用）
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pandas as pd
import pytest

# ── 待测模块 ────────────────────────────────────────────────────────────────

from app.aggregator.envelope import (
    DataEnvelope,
    err_envelope,
    from_cache,
    ok_envelope,
)
from app.datasource.tushare_client import (
    TushareAuthError,
    TushareError,
    TushareRateLimitError,
    _TokenBucket,
    _to_ts_code,
)
from app.tools.fundamental import MODULE_CATALOG, TOOL_REGISTRY
from app.tools.fundamental.base import BaseFundamentalTool, FundamentalToolError


# ═══════════════════════════════════════════════════════════════════════════
# E-1 ~ E-10  DataEnvelope 构建函数
# ═══════════════════════════════════════════════════════════════════════════

class TestEnvelope:

    def test_e1_ok_envelope_basic(self):
        """E-1: ok_envelope 返回 ok=True，data 正确，其余默认。"""
        env = ok_envelope({"price": 100.0})
        assert env["ok"] is True
        assert env["data"] == {"price": 100.0}
        assert env["reason"] is None
        assert env["stale"] is False
        assert env["partial_errors"] == []
        assert env["cached_at"] is None

    def test_e2_ok_envelope_stale(self):
        """E-2: ok_envelope stale=True 传递正确。"""
        env = ok_envelope({"x": 1}, stale=True, cached_at="2026-07-04T10:00:00+08:00")
        assert env["stale"] is True
        assert env["cached_at"] == "2026-07-04T10:00:00+08:00"

    def test_e3_ok_envelope_partial_errors(self):
        """E-3: ok_envelope 带 partial_errors。"""
        env = ok_envelope({"a": 1, "b": None}, partial_errors=["b: 解析失败"])
        assert env["ok"] is True
        assert env["partial_errors"] == ["b: 解析失败"]

    def test_e4_err_envelope_basic(self):
        """E-4: err_envelope 返回 ok=False，data=None。"""
        env = err_envelope("Tushare 超时")
        assert env["ok"] is False
        assert env["data"] is None
        assert env["reason"] == "Tushare 超时"
        assert env["stale"] is False

    def test_e5_err_envelope_stale(self):
        """E-5: err_envelope stale=True（有旧数据但当前请求失败的边界场景）。"""
        env = err_envelope("网络错误", stale=True)
        assert env["ok"] is False
        assert env["stale"] is True

    def test_e6_from_cache_basic(self):
        """E-6: from_cache 正确反序列化 Redis JSON。"""
        raw = {
            "ok": True,
            "data": {"pe": 30.5},
            "reason": None,
            "stale": False,
            "partial_errors": [],
            "cached_at": "2026-07-04T10:00:00+08:00",
        }
        env = from_cache(raw)
        assert env["ok"] is True
        assert env["data"]["pe"] == 30.5
        assert env["cached_at"] == "2026-07-04T10:00:00+08:00"

    def test_e7_from_cache_missing_fields(self):
        """E-7: from_cache 对缺失字段提供默认值（不崩溃）。"""
        env = from_cache({"ok": False})
        assert env["ok"] is False
        assert env["data"] is None
        assert env["partial_errors"] == []
        assert env["stale"] is False

    def test_e8_ok_envelope_data_none_allowed(self):
        """E-8: ok_envelope 允许 data=None（不合理但不报错）。"""
        env = ok_envelope(None)
        assert env["ok"] is True
        assert env["data"] is None

    def test_e9_err_envelope_empty_reason(self):
        """E-9: err_envelope reason 为空字符串不崩溃。"""
        env = err_envelope("")
        assert env["ok"] is False
        assert env["reason"] == ""

    def test_e10_envelope_is_json_serializable(self):
        """E-10: DataEnvelope 可以被 json.dumps 序列化。"""
        env = ok_envelope({"pe": 30.5, "name": "贵州茅台"}, partial_errors=["x"])
        serialized = json.dumps(dict(env), ensure_ascii=False)
        loaded = json.loads(serialized)
        assert loaded["data"]["name"] == "贵州茅台"


# ═══════════════════════════════════════════════════════════════════════════
# T-1 ~ T-10  ts_code 转换
# ═══════════════════════════════════════════════════════════════════════════

class TestTsCode:

    def test_t1_cn_sh_prefix_6(self):
        """T-1: 沪市主板（6 开头）→ .SH"""
        assert _to_ts_code("CN", "600519") == "600519.SH"

    def test_t2_cn_sz_prefix_0(self):
        """T-2: 深市主板（0 开头）→ .SZ"""
        assert _to_ts_code("CN", "000858") == "000858.SZ"

    def test_t3_cn_sz_prefix_3(self):
        """T-3: 创业板（3 开头）→ .SZ"""
        assert _to_ts_code("CN", "300760") == "300760.SZ"

    def test_t4_cn_sh_prefix_688(self):
        """T-4: 科创板（688 开头，归属 6 → .SH）"""
        assert _to_ts_code("CN", "688981") == "688981.SH"

    def test_t5_cn_bj_prefix_8(self):
        """T-5: 北交所（8 开头）→ .BJ"""
        assert _to_ts_code("CN", "838030") == "838030.BJ"

    def test_t6_hk_5digit(self):
        """T-6: 港股 5 位数字→ XXXXX.HK"""
        assert _to_ts_code("HK", "00700") == "00700.HK"

    def test_t7_hk_short_padded(self):
        """T-7: 港股短代码补零至 5 位。"""
        assert _to_ts_code("HK", "700") == "00700.HK"

    def test_t8_us_ticker(self):
        """T-8: 美股 ticker 原样返回。"""
        assert _to_ts_code("US", "AAPL") == "AAPL"

    def test_t9_market_case_insensitive(self):
        """T-9: market 参数大小写不敏感。"""
        assert _to_ts_code("cn", "600519") == "600519.SH"
        assert _to_ts_code("hk", "700") == "00700.HK"

    def test_t10_cn_prefix_2(self):
        """T-10: B 股（2 开头）→ .SZ"""
        assert _to_ts_code("CN", "200012") == "200012.SZ"


# ═══════════════════════════════════════════════════════════════════════════
# R-1 ~ R-5  令牌桶速率限制器
# ═══════════════════════════════════════════════════════════════════════════

class TestRateLimiter:

    @pytest.mark.asyncio
    async def test_r1_acquire_single_token(self):
        """R-1: 满桶时 acquire 立即返回（不阻塞）。"""
        bucket = _TokenBucket(rate_per_min=500, burst=10, acquire_timeout=5.0)
        t0 = time.monotonic()
        await bucket.acquire()
        elapsed = time.monotonic() - t0
        assert elapsed < 0.05, f"acquire 耗时过长: {elapsed:.3f}s"

    @pytest.mark.asyncio
    async def test_r2_burst_limit(self):
        """R-2: 连续 burst 次 acquire 均成功（令牌桶初始满桶）。"""
        bucket = _TokenBucket(rate_per_min=600, burst=10, acquire_timeout=5.0)
        for _ in range(10):
            await bucket.acquire()  # 不应抛出异常

    @pytest.mark.asyncio
    async def test_r3_rate_limit_timeout(self):
        """R-3: 令牌耗尽且 acquire_timeout 很短时抛出 TushareRateLimitError。"""
        # 极小速率（1 token/min）和极短超时（0.05s）— 令牌必然耗尽
        bucket = _TokenBucket(rate_per_min=1, burst=1, acquire_timeout=0.05)
        await bucket.acquire()  # 消耗唯一令牌
        with pytest.raises(TushareRateLimitError):
            await bucket.acquire()

    @pytest.mark.asyncio
    async def test_r4_tokens_not_exceed_capacity(self):
        """R-4: 等待足够时间后令牌数不超过容量上限。"""
        bucket = _TokenBucket(rate_per_min=60, burst=5, acquire_timeout=5.0)
        # 消耗全部令牌
        for _ in range(5):
            await bucket.acquire()
        # 等待一段时间让令牌补充
        await asyncio.sleep(0.2)  # 0.2s * 1 token/s = ~0.2 tokens
        bucket._refill()
        assert bucket._tokens <= bucket._capacity

    @pytest.mark.asyncio
    async def test_r5_concurrent_acquires(self):
        """R-5: 并发 acquire 不产生竞争条件（令牌不超发）。"""
        bucket = _TokenBucket(rate_per_min=600, burst=10, acquire_timeout=5.0)
        acquired = 0

        async def _do_acquire():
            nonlocal acquired
            await bucket.acquire()
            acquired += 1

        await asyncio.gather(*[_do_acquire() for _ in range(10)])
        assert acquired == 10


# ═══════════════════════════════════════════════════════════════════════════
# A-1 ~ A-7  聚合器（mock tool / mock redis）
# ═══════════════════════════════════════════════════════════════════════════

class TestAggregator:

    def _make_aggregator(self):
        from app.aggregator.fundamentals_aggregator import FundamentalsAggregator
        agg = FundamentalsAggregator()
        agg._cache_version = "v1"
        return agg

    @pytest.mark.asyncio
    async def test_a1_fetch_module_not_implemented(self):
        """A-1: 请求未实现的模块返回 ok=False，不崩溃。"""
        agg = self._make_aggregator()
        env = await agg.fetch_module("CN", "600519", "rank_revenue")
        assert env["ok"] is False
        assert "未实现" in env["reason"] or "Phase" in env["reason"]

    @pytest.mark.asyncio
    async def test_a2_fetch_module_invalid_key(self):
        """A-2: 请求完全无效的模块 key 返回 err_envelope。"""
        agg = self._make_aggregator()
        env = await agg.fetch_module("CN", "600519", "nonexistent_module_xyz")
        assert env["ok"] is False

    @pytest.mark.asyncio
    @patch("app.aggregator.fundamentals_aggregator.FundamentalsAggregator._read_cache", new_callable=AsyncMock, return_value=None)
    @patch("app.aggregator.fundamentals_aggregator.FundamentalsAggregator._write_cache", new_callable=AsyncMock)
    async def test_a3_fetch_module_success_path(self, mock_write, mock_read):
        """A-3: fetch_module 在 cache MISS 后调用工具，成功返回 ok=True。"""
        agg = self._make_aggregator()

        # Mock TOOL_REGISTRY 中的 quote_snapshot 工具
        mock_tool_cls = MagicMock()
        mock_tool_instance = MagicMock()
        mock_tool_instance.module_key = "quote_snapshot"
        mock_tool_instance.cache_ttl_seconds = 60
        mock_tool_instance.fetch_with_fallback = AsyncMock(
            return_value=ok_envelope({"close": 1850.0})
        )
        mock_tool_cls.return_value = mock_tool_instance

        with patch.dict("app.tools.fundamental.TOOL_REGISTRY", {"quote_snapshot": mock_tool_cls}):
            env = await agg.fetch_module("CN", "600519", "quote_snapshot")

        assert env["ok"] is True
        assert env["data"]["close"] == 1850.0
        mock_write.assert_called_once()

    @pytest.mark.asyncio
    @patch("app.aggregator.fundamentals_aggregator.FundamentalsAggregator._read_cache", new_callable=AsyncMock)
    async def test_a4_fetch_module_cache_hit(self, mock_read):
        """A-4: cache HIT 时直接返回缓存，不调用工具。"""
        cached_env = ok_envelope({"close": 1850.0}, cached_at="2026-07-04T10:00:00+08:00")
        mock_read.return_value = cached_env

        agg = self._make_aggregator()
        env = await agg.fetch_module("CN", "600519", "quote_snapshot")

        assert env["ok"] is True
        assert env["cached_at"] == "2026-07-04T10:00:00+08:00"

    @pytest.mark.asyncio
    @patch("app.aggregator.fundamentals_aggregator.FundamentalsAggregator.fetch_module", new_callable=AsyncMock)
    async def test_a5_fetch_snapshot_concurrent(self, mock_fetch_module):
        """A-5: fetch_snapshot 并发调用 fetch_module（M01+M02）。"""
        mock_fetch_module.side_effect = [
            ok_envelope({"close": 1850.0}),
            ok_envelope({"roe": 40.2}),
        ]

        agg = self._make_aggregator()
        snapshot = await agg.fetch_snapshot("CN", "600519")

        assert "quote_snapshot" in snapshot
        assert "financial_summary" in snapshot
        assert snapshot["quote_snapshot"]["ok"] is True
        assert snapshot["financial_summary"]["ok"] is True
        assert mock_fetch_module.call_count == 2

    @pytest.mark.asyncio
    @patch("app.aggregator.fundamentals_aggregator.FundamentalsAggregator.fetch_module", new_callable=AsyncMock)
    async def test_a6_fetch_snapshot_partial_failure(self, mock_fetch_module):
        """A-6: snapshot 中单个模块失败不影响其他模块。"""
        mock_fetch_module.side_effect = [
            ok_envelope({"close": 1850.0}),
            err_envelope("Tushare 超时"),
        ]

        agg = self._make_aggregator()
        snapshot = await agg.fetch_snapshot("CN", "600519")

        assert snapshot["quote_snapshot"]["ok"] is True
        assert snapshot["financial_summary"]["ok"] is False

    def test_a7_list_modules_returns_all_24(self):
        """A-7: list_modules 返回模块列表；已注册工具的模块 available=True。"""
        agg = self._make_aggregator()
        modules = agg.list_modules()
        # Phase 2A 后 catalog 已扩展到 27 条，断言 >= 24
        assert len(modules) >= 24

        # Phase 1.5 + Phase 2A + Phase 2B + Phase 2C 可用模块（available 或 legacy 均已实现）
        implemented_keys = {
            "snapshot", "financial_summary", "valuation", "dupont", "cashflow_quality",
            "income_statement", "balance_sheet", "cashflow_health",
            "growth", "profitability", "expense_analysis", "asset_structure",
            "solvency", "operation_capability", "capital_occupation",
            "industry_rank",
            # Phase 2C
            "main_business", "dividend_history", "major_holders",
            "equity_structure", "announcements", "analyst_ratings",
            # Phase 3
            "ai_analysis",
        }
        for m in modules:
            if m["key"] in implemented_keys:
                assert m["available"] is True, (
                    f"{m['key']} status={m.get('status')} 应该 available（已注册工具）"
                )
            else:
                assert m["available"] is False, (
                    f"{m['key']} 尚未实现（Phase {m.get('phase')}），应该 not available"
                )


# ═══════════════════════════════════════════════════════════════════════════
# B-1 ~ B-3  BaseFundamentalTool.fetch_with_fallback
# ═══════════════════════════════════════════════════════════════════════════

class _ConcreteToolNoFallback(BaseFundamentalTool):
    """测试用具体工具（无 AkShare fallback）。"""
    module_key = "test_tool"
    cache_ttl_seconds = 60
    stale_ttl_seconds = 300

    def __init__(self, fetch_result=None, fetch_exc=None):
        self._fetch_result = fetch_result
        self._fetch_exc = fetch_exc

    async def fetch(self, market: str, symbol: str) -> dict:
        if self._fetch_exc:
            raise self._fetch_exc
        return self._fetch_result or {}


class _ConcreteToolWithFallback(_ConcreteToolNoFallback):
    """测试用具体工具（有 AkShare fallback）。"""

    def __init__(self, fetch_exc=None, fallback_result=None):
        super().__init__(fetch_exc=fetch_exc)
        self._fallback_result = fallback_result

    async def fetch_akshare(self, market: str, symbol: str) -> dict:
        return self._fallback_result or {"source": "akshare"}


class TestToolBase:

    @pytest.mark.asyncio
    @patch("app.core.config.settings")
    async def test_b1_success_no_fallback(self, mock_settings):
        """B-1: Tushare 成功时返回 ok_envelope，不调用 AkShare。"""
        mock_settings.enable_akshare = False
        tool = _ConcreteToolNoFallback(fetch_result={"pe": 30.5})
        env = await tool.fetch_with_fallback("CN", "600519")
        assert env["ok"] is True
        assert env["data"]["pe"] == 30.5
        assert env["stale"] is False

    @pytest.mark.asyncio
    @patch("app.core.config.settings")
    async def test_b2_tushare_fail_akshare_disabled(self, mock_settings):
        """B-2: Tushare 失败 + ENABLE_AKSHARE=false → 返回 err_envelope。"""
        mock_settings.enable_akshare = False
        from app.datasource.tushare_client import TushareError
        tool = _ConcreteToolNoFallback(fetch_exc=TushareError("超时"))
        env = await tool.fetch_with_fallback("CN", "600519")
        assert env["ok"] is False
        assert "超时" in env["reason"]

    @pytest.mark.asyncio
    @patch("app.core.config.settings")
    async def test_b3_tushare_fail_akshare_enabled_fallback_success(self, mock_settings):
        """B-3: Tushare 失败 + ENABLE_AKSHARE=true → AkShare 成功 → ok=True, stale=True。"""
        mock_settings.enable_akshare = True
        from app.datasource.tushare_client import TushareError
        tool = _ConcreteToolWithFallback(
            fetch_exc=TushareError("超时"),
            fallback_result={"source": "akshare_fallback", "n_cashflow_act": 8.5e10},
        )
        env = await tool.fetch_with_fallback("CN", "600519")
        assert env["ok"] is True
        assert env["stale"] is True   # 来自 AkShare 降级，标记 stale
        assert env["data"]["source"] == "akshare_fallback"


# ═══════════════════════════════════════════════════════════════════════════
# 工具注册表和模块目录完整性检查
# ═══════════════════════════════════════════════════════════════════════════

def test_tool_registry_phase1_complete():
    """TOOL_REGISTRY 包含 Phase 1 原始工具 + Phase 1.5 新工具。"""
    expected = {
        # Phase 1 原始
        "quote_snapshot", "financial_summary",
        "income_statement", "balance_sheet", "cashflow_health",
        # Phase 1.5 新增
        "snapshot", "valuation", "dupont", "cashflow_quality",
    }
    assert expected.issubset(TOOL_REGISTRY.keys())


def test_module_catalog_has_minimum_entries():
    """MODULE_CATALOG 至少 24 条（Phase 2A 后已扩展到 27）。"""
    assert len(MODULE_CATALOG) >= 24


def test_module_catalog_ai_module_requires_llm():
    """AI 模块 requires_llm=True，其余全部 False。"""
    for m in MODULE_CATALOG:
        if m["key"] == "ai_analysis":
            assert m["requires_llm"] is True
        else:
            assert m["requires_llm"] is False, f"{m['key']} 不应该 requires_llm"


def test_phase1_tools_have_correct_cache_ttl():
    """Phase 1 + Phase 1.5 工具 cache_ttl_seconds 符合规范。"""
    ttl_expectations = {
        "quote_snapshot":   60,
        "snapshot":         60,
        "financial_summary": 14400,
        "income_statement":  14400,
        "balance_sheet":     14400,
        "cashflow_health":   14400,
        "valuation":         3600,
        "dupont":            14400,
        "cashflow_quality":  14400,
    }
    for key, expected_ttl in ttl_expectations.items():
        tool = TOOL_REGISTRY[key]()
        assert tool.cache_ttl_seconds == expected_ttl, (
            f"{key}: 期望 TTL={expected_ttl}，实际={tool.cache_ttl_seconds}"
        )


def test_compliance_no_aicaibao_in_tools():
    """合规检查：所有工具层文件无 aicaibao 引用。"""
    import inspect
    import app.tools.fundamental.quote_snapshot as qs
    import app.tools.fundamental.financial_summary as fs
    import app.tools.fundamental.income_statement as ist
    import app.tools.fundamental.balance_sheet as bs
    import app.tools.fundamental.cashflow_health as ch
    import app.tools.fundamental.valuation as val
    import app.tools.fundamental.dupont as dp
    import app.tools.fundamental.cashflow_quality as cq

    for mod in [qs, fs, ist, bs, ch, val, dp, cq]:
        src = inspect.getsource(mod)
        assert "aicaibao" not in src, f"{mod.__name__} 包含 aicaibao 引用（违规）"
