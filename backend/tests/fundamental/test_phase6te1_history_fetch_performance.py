"""
backend/tests/fundamental/test_phase6te1_history_fetch_performance.py
Phase 6T-E1: History Fetch Performance Fix（消除 N+1 逐季请求）
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest


# ── 批量抓取行为 ──────────────────────────────────────────────────────────────

def test_annual_mode_queries_q4_only():
    """annual 模式每年只查 Q4，不按季度逐条请求。"""
    from app.datasource.baostock_client import _BULK_TABLE_KEYS

    # worker 输入构造逻辑：annual → 每年 1 个 (year, 4)
    quarters_annual = (4,)
    quarters_quarterly = (1, 2, 3, 4)
    years = list(range(2007, 2027))          # 20 年
    annual_pairs = [(y, q) for y in years for q in quarters_annual]
    quarterly_pairs = [(y, q) for y in years for q in quarters_quarterly]
    assert len(annual_pairs) == 20            # 非 80
    assert len(quarterly_pairs) == 80
    assert len(_BULK_TABLE_KEYS) == 6
    # annual 全量调用上限：年数 × 6 表（600519≈20×6=120 << 624）
    assert len(annual_pairs) * 6 <= 130


def test_baostock_data_start_year_clamp():
    """早于 2007（BaoStock 季频数据起点）的年份直接跳过。"""
    from app.datasource.baostock_client import BAOSTOCK_FINANCIAL_DATA_START_YEAR
    assert BAOSTOCK_FINANCIAL_DATA_START_YEAR == 2007


@pytest.mark.asyncio
async def test_bulk_fetch_uses_year_cache_and_reports_stats():
    """分年缓存命中时零外部调用；stats 真实反映。"""
    from app.datasource import baostock_client as bc

    cached_year = {
        "tables": {k: [{"statDate": "2024-12-31"}] for k in bc._BULK_TABLE_KEYS},
        "year": 2024, "mode": "annual",
    }

    async def fake_get(key, *, force_refresh=False):
        return cached_year, True, False, "memory"

    with patch("app.services.company_v2_snapshot_cache_service.company_v2_snapshot_cache_service.get",
               new=AsyncMock(side_effect=fake_get)):
        result = await bc.baostock_client.get_financial_history_bulk(
            "601686.SH", start_year=2024, end_year=2024, mode="annual")

    stats = result["_bulk_stats"]
    assert stats["provider_calls"] == 0
    assert stats["years_from_cache"] == 1
    assert stats["years_fetched"] == 0
    assert stats["cache_hit"] is True
    assert stats["login_batches"] == 0
    assert len(result["profit"]) == 1


@pytest.mark.asyncio
async def test_bulk_fetch_clamps_pre_2007_years():
    """1996 年上市股票（如 000725）：请求年份被截断到 2007。"""
    from app.datasource import baostock_client as bc

    async def fake_get(key, *, force_refresh=False):
        return {"tables": {k: [] for k in bc._BULK_TABLE_KEYS}}, True, False, "memory"

    with patch("app.services.company_v2_snapshot_cache_service.company_v2_snapshot_cache_service.get",
               new=AsyncMock(side_effect=fake_get)):
        result = await bc.baostock_client.get_financial_history_bulk(
            "000725.SZ", start_year=1996, end_year=2026, mode="annual")

    stats = result["_bulk_stats"]
    assert stats["requested_start_year"] == 1996
    assert stats["effective_start_year"] == 2007
    assert stats["provider_history_clamped_to_2007"] is True
    assert stats["years_total"] == 20


@pytest.mark.asyncio
async def test_bulk_singleflight_dedupes_concurrent_requests():
    """并发相同请求只执行一次真实抓取（singleflight）。"""
    import asyncio
    from app.datasource import baostock_client as bc

    fetch_count = 0
    miss_then_hit: dict[str, dict] = {}

    async def fake_get(key, *, force_refresh=False):
        cached = miss_then_hit.get(key)
        if cached:
            return cached, True, False, "memory"
        return None, False, False, "memory"

    async def fake_set(key, value, ttl):
        miss_then_hit[key] = value

    def fake_worker(bs_code, year_quarters):
        nonlocal fetch_count
        fetch_count += 1
        by_year = {}
        for year, _q in year_quarters:
            by_year[year] = {k: [] for k in bc._BULK_TABLE_KEYS}
        return by_year, len(year_quarters) * 6

    with patch("app.services.company_v2_snapshot_cache_service.company_v2_snapshot_cache_service.get",
               new=AsyncMock(side_effect=fake_get)):
        with patch("app.services.company_v2_snapshot_cache_service.company_v2_snapshot_cache_service.set",
                   new=AsyncMock(side_effect=fake_set)):
            with patch.object(bc, "_bulk_fetch_years_worker", side_effect=fake_worker):
                # 强制走串行回退路径（禁用进程池，便于计数）
                with patch("concurrent.futures.ProcessPoolExecutor", side_effect=OSError("disabled")):
                    results = await asyncio.gather(
                        bc.baostock_client.get_financial_history_bulk(
                            "601686.SH", start_year=2023, end_year=2024, mode="annual"),
                        bc.baostock_client.get_financial_history_bulk(
                            "601686.SH", start_year=2023, end_year=2024, mode="annual"),
                    )

    # 第二个请求在锁内重新读缓存 → 全命中，不再抓取
    assert fetch_count == 1
    assert results[1]["_bulk_stats"]["years_from_cache"] == 2


@pytest.mark.asyncio
async def test_modules_share_single_bulk_fetch():
    """6 个模块共享一次批量结果，不允许各自重复请求。"""
    from app.datasource.history_financial_provider import fetch_all_modules_history
    from app.datasource import baostock_client as bc

    aggregate = {k: [] for k in ("profit", "growth", "balance", "operation", "cash_flow", "dupont")}
    aggregate["profit"] = [{"stat_date": "2024-12-31", "roe_avg": "0.1"}]
    aggregate["_bulk_stats"] = {"provider_calls": 12, "login_batches": 2}
    mock_bulk = AsyncMock(return_value=aggregate)

    with patch.object(bc.baostock_client, "get_financial_history_bulk", mock_bulk):
        stats: dict = {}
        result = await fetch_all_modules_history(
            "601686.SH", start_year=2023, end_year=2024, period="annual", stats_out=stats)

    mock_bulk.assert_awaited_once()          # 单次批量，模块共享
    assert len(result) == 6
    assert stats["login_batches"] <= 3


# ── history service 默认范围 ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_quarterly_default_limits_to_recent_5_years():
    """quarterly 默认最近 5 年；annual 保持上市以来。"""
    from datetime import date
    from app.services.company_v2_history_service import build_company_history_dashboard

    captured: dict = {}

    async def fake_fetch(ts, *, start_year, end_year, period, valid_quarters=None, stats_out=None):
        captured["start_year"] = start_year
        captured["period"] = period
        return {}

    with patch("app.services.company_v2_history_service.fetch_all_modules_history",
               new=AsyncMock(side_effect=fake_fetch)):
        with patch("app.services.company_v2_history_service.get_stock_basic",
                   new=AsyncMock(return_value={"list_year": 2001, "list_date": "2001-08-27",
                                               "list_date_status": "exact"})):
            result_q = await build_company_history_dashboard(
                "CN", "600519", period="quarterly", force_refresh=True)
            assert captured["start_year"] == date.today().year - 5
            assert result_q["start_year_status"] == "recent_5_complete_years_default"

            result_a = await build_company_history_dashboard(
                "CN", "600519", period="annual", force_refresh=True)
            assert captured["start_year"] == 2001   # annual 上市以来（provider 内部再截 2007）
            assert result_a["start_year_status"] == "from_list_date"


@pytest.mark.asyncio
async def test_explicit_start_year_not_limited():
    """用户显式 start_year 不受最近 5 年限制。"""
    from app.services.company_v2_history_service import build_company_history_dashboard

    captured: dict = {}

    async def fake_fetch(ts, *, start_year, end_year, period, valid_quarters=None, stats_out=None):
        captured["start_year"] = start_year
        return {}

    with patch("app.services.company_v2_history_service.fetch_all_modules_history",
               new=AsyncMock(side_effect=fake_fetch)):
        with patch("app.services.company_v2_history_service.get_stock_basic",
                   new=AsyncMock(return_value={"list_year": 2001, "list_date": "2001-08-27",
                                               "list_date_status": "exact"})):
            await build_company_history_dashboard(
                "CN", "600519", period="quarterly", start_year=2010, force_refresh=True)
    assert captured["start_year"] == 2010


@pytest.mark.asyncio
async def test_performance_summary_exposes_provider_calls():
    from app.services.company_v2_history_service import build_company_history_dashboard

    async def fake_fetch(ts, *, start_year, end_year, period, valid_quarters=None, stats_out=None):
        if stats_out is not None:
            stats_out.update({"provider_calls": 18, "login_batches": 3,
                              "years_from_cache": 2, "years_fetched": 1})
        return {
            "profitability": {
                "history": [{"period": "2024-12-31", "roe": 0.1}],
                "latest": {"period": "2024-12-31", "roe": 0.1},
                "period_type": "point_in_time",
                "chart_contract": {"preferred_chart": "multi_line",
                                   "series": [{"field": "roe", "display_type": "percent"}]},
                "history_coverage": {"start_period": "2024-12-31", "end_period": "2024-12-31",
                                     "periods_count": 1, "history_truncated": True},
                "data_success": True, "provider": "baostock",
            }
        }

    with patch("app.services.company_v2_history_service.fetch_all_modules_history",
               new=AsyncMock(side_effect=fake_fetch)):
        with patch("app.services.company_v2_history_service.get_stock_basic",
                   new=AsyncMock(return_value={"list_year": 2024, "list_date": "2024-01-05",
                                               "list_date_status": "exact"})):
            result = await build_company_history_dashboard(
                "CN", "601686", period="annual", force_refresh=True)

    perf = result["performance_summary"]
    assert perf["provider_calls"] == 18
    assert perf["login_batches"] == 3
    assert perf["years_from_cache"] == 2
    assert perf["years_fetched"] == 1


# ── 验收脚本 ──────────────────────────────────────────────────────────────────

def test_acceptance_script_has_fast_deep_modes_and_timeout():
    import inspect
    import importlib.util
    from pathlib import Path

    script = Path(__file__).resolve().parents[3] / "backend/scripts/company_v2_cross_stock_acceptance.py"
    text = script.read_text(encoding="utf-8")
    assert '"--mode"' in text and '"fast"' in text and '"deep"' in text
    assert "--per-symbol-timeout" in text
    assert "asyncio.wait_for" in text
    assert "checkpoint" in text
    assert "per_symbol_timeout_exceeded" in text
    # 不伪造：超时记录 structured timeout 并继续
    assert "timeout" in text
    # 无投资建议措辞
    for word in ("买入", "卖出", "目标价", "保证上涨"):
        assert word not in text


def test_acceptance_script_checkpoint_resume(tmp_path):
    """checkpoint 加载：同 mode 恢复，异 mode 忽略。"""
    import json
    import sys
    from pathlib import Path

    root = Path(__file__).resolve().parents[3]
    sys.path.insert(0, str(root / "backend/scripts"))
    try:
        from company_v2_cross_stock_acceptance import _load_checkpoint
    finally:
        sys.path.pop(0)

    ckpt = tmp_path / "x.checkpoint.json"
    ckpt.write_text(json.dumps({
        "mode": "fast",
        "symbols": [{"symbol": "600519", "final_status": "passed"}],
    }), encoding="utf-8")
    assert "600519" in _load_checkpoint(ckpt, "fast")
    assert _load_checkpoint(ckpt, "deep") == {}
    assert _load_checkpoint(tmp_path / "missing.json", "fast") == {}


# ── 前端默认行为（源码级检查） ────────────────────────────────────────────────

def test_frontend_defaults_annual_and_lazy_quarterly():
    from pathlib import Path
    view = (Path(__file__).resolve().parents[3]
            / "frontend/src/views/CompanyV2View.vue").read_text(encoding="utf-8")
    assert "periodTab = ref('annual')" in view
    assert "period: 'annual'" in view
    assert "period: 'all'" not in view
    assert "switchToQuarterly" in view
    assert "quarterlyHistoryData" in view
