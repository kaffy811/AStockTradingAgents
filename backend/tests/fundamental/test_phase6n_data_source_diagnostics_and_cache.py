"""
tests/fundamental/test_phase6n_data_source_diagnostics_and_cache.py

Phase 6N: Data Source Diagnostics & Cache-First Tests

Covers:
  T01  debug_free_mode_data_sources.py: importable + main() exists
  T02  debug_free_mode_data_sources.py: --symbols / --years / --out-dir args
  T03  debug_free_mode_data_sources.py: _to_ts_code converts 6-digit codes
  T04  debug_free_mode_data_sources.py: _compute_renderability returns score 0–100
  T05  debug_free_mode_data_sources.py: _compute_renderability no-data → 0.0
  T06  BaoStockClient: get_all_financial_indicators method exists
  T07  BaoStockClient: get_all_financial_indicators returns dict with 6 keys
  T08  BaoStockClient: get_all_financial_indicators returns same shape as individual get_*_data
  T09  BaoStockClient: get_all_financial_indicators fails gracefully when baostock unavailable
  T10  FreeFundamentalCacheService: importable + singleton exists
  T11  FreeFundamentalCacheService: get_financial_table returns None when Redis unavailable
  T12  FreeFundamentalCacheService: set/get financial table round-trip (mock Redis)
  T13  FreeFundamentalCacheService: get_pdf_discovery returns None on cache miss
  T14  FreeFundamentalCacheService: set_pdf_discovery skips empty candidates
  T15  FreeFundamentalCacheService: set_pdf_discovery caches non-empty result
  T16  FreeFundamentalCacheService: get_all_financial returns None on cache miss
"""
from __future__ import annotations

import importlib
import inspect
import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

_BACKEND_ROOT = Path(__file__).resolve().parents[2]


# ── T01: script importable + main() exists ──────────────────────────────────

def test_debug_data_sources_script_importable():
    """debug_free_mode_data_sources.py must be importable and expose main()."""
    script_path = _BACKEND_ROOT / "scripts" / "debug_free_mode_data_sources.py"
    assert script_path.exists(), "scripts/debug_free_mode_data_sources.py not found"

    spec = importlib.util.spec_from_file_location("debug_data_sources", script_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    assert hasattr(mod, "main"), "main() missing from debug_free_mode_data_sources.py"
    assert callable(mod.main)


# ── T02: script has expected CLI args ────────────────────────────────────────

def test_debug_data_sources_script_has_expected_args():
    """Script must declare --symbols, --years, --out-dir, --dry-run args."""
    script_path = _BACKEND_ROOT / "scripts" / "debug_free_mode_data_sources.py"
    source = script_path.read_text(encoding="utf-8")

    assert '"--symbols"' in source or "'--symbols'" in source, "--symbols arg missing"
    assert '"--years"' in source or "'--years'" in source, "--years arg missing"
    assert '"--out-dir"' in source or "'--out-dir'" in source, "--out-dir arg missing"
    assert '"--dry-run"' in source or "'--dry-run'" in source, "--dry-run arg missing"


# ── T03: _to_ts_code conversion ──────────────────────────────────────────────

def test_debug_script_to_ts_code():
    """_to_ts_code must correctly assign .SH / .SZ suffix."""
    script_path = _BACKEND_ROOT / "scripts" / "debug_free_mode_data_sources.py"
    spec = importlib.util.spec_from_file_location("debug_data_sources_t03", script_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    assert mod._to_ts_code("600519") == "600519.SH"
    assert mod._to_ts_code("000725") == "000725.SZ"
    assert mod._to_ts_code("600519.SH") == "600519.SH"
    assert mod._to_ts_code("300750") == "300750.SZ"


# ── T04: _compute_renderability score range ──────────────────────────────────

def test_compute_renderability_score_range():
    """_compute_renderability score must be 0–100."""
    script_path = _BACKEND_ROOT / "scripts" / "debug_free_mode_data_sources.py"
    spec = importlib.util.spec_from_file_location("debug_data_sources_t04", script_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    # Full success
    probes = [
        # BaoStock financial tables (6 total, all renderable)
        *[
            {
                "probe": f"baostock_{tbl}",
                "status": "ok",
                "detail": {"rows_count": 8, "renderable": True},
            }
            for tbl in ("profit", "growth", "balance", "operation", "cash_flow", "dupont")
        ],
        # AkShare quote
        {"probe": "akshare_real_time_quote", "status": "ok", "detail": {"close": 123.4}},
        # PDF
        {"probe": "pdf_discovery_2024", "status": "ok", "detail": {"candidates": 1}},
        # RAG
        {"probe": "db_report_chunks", "status": "ok", "detail": {"chunk_count": 100}},
    ]
    result = mod._compute_renderability(probes)
    assert 0 <= result["score"] <= 100
    assert result["score"] == 100.0, f"Expected 100.0 but got {result['score']}"


# ── T05: _compute_renderability no-data → 0.0 ───────────────────────────────

def test_compute_renderability_empty_probes():
    """_compute_renderability with no successful probes must return score 0."""
    script_path = _BACKEND_ROOT / "scripts" / "debug_free_mode_data_sources.py"
    spec = importlib.util.spec_from_file_location("debug_data_sources_t05", script_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    probes = [
        *[
            {
                "probe": f"baostock_{tbl}",
                "status": "failed",
                "detail": {"rows_count": 0, "renderable": False},
            }
            for tbl in ("profit", "growth", "balance", "operation", "cash_flow", "dupont")
        ],
        {"probe": "akshare_real_time_quote", "status": "failed", "detail": {"close": None}},
        {"probe": "pdf_discovery_2024", "status": "empty", "detail": {"candidates": 0}},
        {"probe": "db_report_chunks", "status": "empty", "detail": {"chunk_count": 0}},
    ]
    result = mod._compute_renderability(probes)
    assert result["score"] == 0.0
    assert result["renderable_bs_modules"] == 0
    assert not result["akshare_quote_ok"]
    assert not result["pdf_any_year_found"]
    assert not result["rag_ready"]


# ── T06: BaoStockClient.get_all_financial_indicators method exists ────────────

def test_baostock_client_has_aggregate_method():
    """BaoStockClient must have get_all_financial_indicators method."""
    from app.datasource.baostock_client import BaoStockClient
    client = BaoStockClient()
    assert hasattr(client, "get_all_financial_indicators"), (
        "get_all_financial_indicators missing from BaoStockClient"
    )
    assert inspect.iscoroutinefunction(client.get_all_financial_indicators), (
        "get_all_financial_indicators must be async"
    )


# ── T07: get_all_financial_indicators returns dict with 6 keys ───────────────

@pytest.mark.asyncio
async def test_baostock_aggregate_returns_six_keys():
    """get_all_financial_indicators must return dict with exactly 6 keys."""
    from app.datasource.baostock_client import BaoStockClient

    client = BaoStockClient()

    # Mock the internal _sync_fetch_all to return empty raw data
    with patch("asyncio.to_thread", new=AsyncMock(return_value={
        "profit": [], "growth": [], "balance": [],
        "operation": [], "cash_flow": [], "dupont": [],
    })):
        with patch("app.datasource.baostock_client._get_bs_lock") as mock_lock:
            mock_lock.return_value.__aenter__ = AsyncMock(return_value=None)
            mock_lock.return_value.__aexit__ = AsyncMock(return_value=None)
            result = await client.get_all_financial_indicators("600519.SH")

    assert isinstance(result, dict)
    expected_keys = {"profit", "growth", "balance", "operation", "cash_flow", "dupont"}
    assert set(result.keys()) == expected_keys, (
        f"Expected keys {expected_keys}, got {set(result.keys())}"
    )


# ── T08: aggregate returns same field shape as individual get_*_data ──────────

@pytest.mark.asyncio
async def test_baostock_aggregate_same_shape_as_individual():
    """get_all_financial_indicators profit rows must have same fields as get_profit_data."""
    from app.datasource.baostock_client import BaoStockClient

    # We test the field mapping by simulating raw BaoStock row data
    mock_raw = {
        "profit": [{"pubDate": "2024-03-30", "statDate": "2023-12-31",
                    "roeAvg": "0.15", "npMargin": "0.30", "gpMargin": "0.40",
                    "netProfit": "1000", "epsTTM": "2.5",
                    "MBRevenue": "5000", "totalShare": "500", "liqaShare": "400"}],
        "growth": [], "balance": [], "operation": [], "cash_flow": [], "dupont": [],
    }

    client = BaoStockClient()
    with patch("asyncio.to_thread", new=AsyncMock(return_value=mock_raw)):
        with patch("app.datasource.baostock_client._get_bs_lock") as mock_lock:
            mock_lock.return_value.__aenter__ = AsyncMock(return_value=None)
            mock_lock.return_value.__aexit__ = AsyncMock(return_value=None)
            result = await client.get_all_financial_indicators("600519.SH")

    profit_rows = result["profit"]
    assert len(profit_rows) == 1
    row = profit_rows[0]
    # Must have same fields as get_profit_data output
    expected_fields = {
        "ts_code", "pub_date", "stat_date", "roe_avg", "net_margin",
        "gross_margin", "net_profit", "eps_ttm", "mb_revenue", "total_share", "liqa_share",
    }
    assert set(row.keys()) == expected_fields, (
        f"profit row fields mismatch: {set(row.keys())} vs {expected_fields}"
    )
    assert row["ts_code"] == "600519.SH"
    assert row["roe_avg"] == 0.15


# ── T09: aggregate fails gracefully when baostock unavailable ────────────────

@pytest.mark.asyncio
async def test_baostock_aggregate_graceful_on_import_error():
    """get_all_financial_indicators must return 6 empty lists if baostock is unavailable."""
    from app.datasource.baostock_client import BaoStockClient

    client = BaoStockClient()
    with patch.dict("sys.modules", {"baostock": None}):
        result = await client.get_all_financial_indicators("600519.SH")

    assert isinstance(result, dict)
    assert all(isinstance(v, list) for v in result.values())
    assert all(len(v) == 0 for v in result.values())


# ── T10: FreeFundamentalCacheService importable ──────────────────────────────

def test_free_fundamental_cache_service_importable():
    """FreeFundamentalCacheService must be importable and singleton must exist."""
    from app.services.free_fundamental_cache_service import (
        FreeFundamentalCacheService,
        free_fundamental_cache,
    )
    assert isinstance(free_fundamental_cache, FreeFundamentalCacheService)


# ── T11: get_financial_table returns None when Redis unavailable ──────────────

@pytest.mark.asyncio
async def test_cache_get_financial_table_no_redis():
    """get_financial_table must return None when Redis is unavailable."""
    from app.services.free_fundamental_cache_service import FreeFundamentalCacheService

    svc = FreeFundamentalCacheService()
    with patch("app.services.free_fundamental_cache_service._get_redis", return_value=None):
        result = await svc.get_financial_table("600519.SH", "profit")
    assert result is None


# ── T12: set/get financial table round-trip ──────────────────────────────────

@pytest.mark.asyncio
async def test_cache_financial_table_round_trip():
    """set_financial_table + get_financial_table must round-trip correctly."""
    from app.services.free_fundamental_cache_service import FreeFundamentalCacheService

    svc = FreeFundamentalCacheService()
    store: dict[str, bytes] = {}

    async def mock_setex(key, ttl, value):
        store[key] = value

    async def mock_get(key):
        return store.get(key)

    mock_redis = MagicMock()
    mock_redis.setex = mock_setex
    mock_redis.get = mock_get

    rows = [{"ts_code": "600519.SH", "pub_date": "2024-03-30", "roe_avg": 0.15}]

    with patch("app.services.free_fundamental_cache_service._get_redis", return_value=mock_redis):
        await svc.set_financial_table("600519.SH", "profit", rows)
        result = await svc.get_financial_table("600519.SH", "profit")

    assert result == rows


# ── T13: get_pdf_discovery returns None on cache miss ────────────────────────

@pytest.mark.asyncio
async def test_cache_get_pdf_discovery_miss():
    """get_pdf_discovery must return None when key not found in Redis."""
    from app.services.free_fundamental_cache_service import FreeFundamentalCacheService

    svc = FreeFundamentalCacheService()

    mock_redis = MagicMock()
    mock_redis.get = AsyncMock(return_value=None)

    with patch("app.services.free_fundamental_cache_service._get_redis", return_value=mock_redis):
        result = await svc.get_pdf_discovery("600519.SH", 2024)
    assert result is None


# ── T14: set_pdf_discovery skips empty candidates ─────────────────────────────

@pytest.mark.asyncio
async def test_cache_set_pdf_discovery_skips_empty():
    """set_pdf_discovery must NOT write to Redis when candidates is empty."""
    from app.services.free_fundamental_cache_service import FreeFundamentalCacheService

    svc = FreeFundamentalCacheService()
    mock_redis = MagicMock()
    mock_redis.setex = AsyncMock()

    with patch("app.services.free_fundamental_cache_service._get_redis", return_value=mock_redis):
        await svc.set_pdf_discovery("600519.SH", 2024, {"candidates": [], "total_found": 0})

    mock_redis.setex.assert_not_called()


# ── T15: set_pdf_discovery caches non-empty result ───────────────────────────

@pytest.mark.asyncio
async def test_cache_set_pdf_discovery_caches_candidates():
    """set_pdf_discovery must write to Redis when candidates is non-empty."""
    from app.services.free_fundamental_cache_service import FreeFundamentalCacheService

    svc = FreeFundamentalCacheService()
    store: dict[str, bytes] = {}

    async def mock_setex(key, ttl, value):
        store[key] = value

    async def mock_get(key):
        return store.get(key)

    mock_redis = MagicMock()
    mock_redis.setex = mock_setex
    mock_redis.get = mock_get

    result_in = {
        "candidates": [{"title": "2024年报", "confidence": 0.9}],
        "total_found": 1,
        "errors": [],
    }

    with patch("app.services.free_fundamental_cache_service._get_redis", return_value=mock_redis):
        await svc.set_pdf_discovery("600519.SH", 2024, result_in)
        cached = await svc.get_pdf_discovery("600519.SH", 2024)

    assert cached is not None
    assert cached["total_found"] == 1
    assert cached["candidates"][0]["title"] == "2024年报"


# ── T16: get_all_financial returns None on cache miss ────────────────────────

@pytest.mark.asyncio
async def test_cache_get_all_financial_miss():
    """get_all_financial must return None when key not found."""
    from app.services.free_fundamental_cache_service import FreeFundamentalCacheService

    svc = FreeFundamentalCacheService()
    mock_redis = MagicMock()
    mock_redis.get = AsyncMock(return_value=None)

    with patch("app.services.free_fundamental_cache_service._get_redis", return_value=mock_redis):
        result = await svc.get_all_financial("600519.SH")
    assert result is None
