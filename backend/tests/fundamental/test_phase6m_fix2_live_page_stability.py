"""
tests/fundamental/test_phase6m_fix2_live_page_stability.py — Phase 6M-Fix2 Stability Tests

Covers:
  T01  report_documents compat route returns data (not "Phase 1 未实现")
  T02  report_documents API response does NOT contain local_path
  T03  pgvector CAST syntax present in report_rag_service
  T04  baostock_client has module-level _get_bs_lock function
  T05  baostock_client _fetch_quarters uses asyncio lock
  T06  baostock_client has _suppress_bs_output context manager
  T07  baostock_client has get_recent_close method
  T08  QuoteSnapshotTool has fetch_baostock method
  T09  fetch_baostock returns baostock_kline_fallback source on success
  T10  fetch_baostock raises FundamentalToolError for non-CN markets
  T11  SZSE HTTP 400 is downgraded to DEBUG (not WARNING)
  T12  fundamentals_compat has special case for report_documents before aggregator
  T13  get_recent_close returns None on baostock import failure
  T14  fundamentals.py get_report_documents excludes local_path from rows
"""
from __future__ import annotations

import ast
import importlib
import inspect
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

_BACKEND_ROOT = Path(__file__).resolve().parents[2]

# ── T01: report_documents compat returns real data, not "Phase 1 未实现" ────────

@pytest.mark.asyncio
async def test_report_documents_compat_route_not_unimplemented():
    """fundamentals_compat route for report_documents must NOT return Phase-1-未实现."""
    from httpx import AsyncClient, ASGITransport
    from app.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        with patch("app.routers.fundamentals.get_report_documents") as mock_handler:
            from fastapi.responses import JSONResponse
            import json
            mock_handler.return_value = JSONResponse(
                content={"ok": True, "partial": False, "data": {"ts_code": "600519.SH", "rows": []}, "errors": []},
                status_code=200,
            )
            r = await client.get("/api/v1/stock/600519/modules/report_documents")
            assert r.status_code == 200
            body = r.json()
            # Must not be "Phase 1 未实现" (aggregator fallback)
            body_str = str(body)
            assert "Phase 1" not in body_str, f"Got Phase-1 fallback: {body_str[:200]}"
            assert "未实现" not in body_str, f"Got 未实现 fallback: {body_str[:200]}"


# ── T02: local_path not in API response (source-level check) ────────────────────

def test_report_documents_no_local_path_in_api_response_source():
    """fundamentals.py row construction must not include local_path key."""
    fund_path = _BACKEND_ROOT / "app" / "routers" / "fundamentals.py"
    source = fund_path.read_text()
    # local_path must not appear as a dict key in the row construction block
    assert '"local_path"' not in source or "d.local_path" not in source, (
        "local_path must be removed from the rows dict in get_report_documents"
    )
    # More specifically, the pair must not coexist
    lines = source.splitlines()
    for i, line in enumerate(lines):
        if '"local_path"' in line and 'd.local_path' in line:
            pytest.fail(
                f"local_path still leaked at line {i+1}: {line.strip()}"
            )


# ── T03: pgvector CAST syntax ────────────────────────────────────────────────────

def test_pgvector_uses_cast_not_colon_cast():
    """report_rag_service must use CAST(:query_vec AS vector) not :query_vec::vector."""
    rag_path = _BACKEND_ROOT / "app" / "services" / "report_rag_service.py"
    source = rag_path.read_text()
    assert "CAST(:query_vec AS vector)" in source, \
        "pgvector query must use CAST(:query_vec AS vector) for asyncpg compatibility"
    assert ":query_vec::vector" not in source, \
        "Old PostgreSQL cast syntax :query_vec::vector must be removed"


# ── T04: baostock_client has _get_bs_lock ────────────────────────────────────────

def test_baostock_client_has_get_bs_lock():
    """baostock_client module must define _get_bs_lock() for lock serialization."""
    import app.datasource.baostock_client as bc
    assert hasattr(bc, "_get_bs_lock"), "_get_bs_lock must be defined in baostock_client"
    assert callable(bc._get_bs_lock)


# ── T05: baostock_client _fetch_quarters uses asyncio lock ──────────────────────

def test_baostock_fetch_quarters_uses_lock():
    """_fetch_quarters source must contain _get_bs_lock() call."""
    import app.datasource.baostock_client as bc
    src = inspect.getsource(bc.BaoStockClient._fetch_quarters)
    assert "_get_bs_lock" in src, "_fetch_quarters must acquire lock via _get_bs_lock()"
    assert "async with" in src, "_fetch_quarters must use 'async with' for lock"


# ── T06: _suppress_bs_output context manager ────────────────────────────────────

def test_suppress_bs_output_exists():
    """baostock_client must have _suppress_bs_output context manager."""
    import app.datasource.baostock_client as bc
    assert hasattr(bc, "_suppress_bs_output"), "_suppress_bs_output must be defined"
    assert callable(bc._suppress_bs_output)


def test_suppress_bs_output_captures_stdout(capsys):
    """_suppress_bs_output must suppress print statements."""
    from app.datasource.baostock_client import _suppress_bs_output
    with _suppress_bs_output():
        print("login ok")
        print("logout ok")
    captured = capsys.readouterr()
    assert "login ok" not in captured.out
    assert "logout ok" not in captured.out


# ── T07: get_recent_close method exists ─────────────────────────────────────────

def test_baostock_client_has_get_recent_close():
    """BaoStockClient must have get_recent_close() method."""
    import app.datasource.baostock_client as bc
    assert hasattr(bc.BaoStockClient, "get_recent_close")
    assert callable(bc.BaoStockClient.get_recent_close)


# ── T08: QuoteSnapshotTool has fetch_baostock ────────────────────────────────────

def test_quote_snapshot_tool_has_fetch_baostock():
    """QuoteSnapshotTool must implement fetch_baostock for free mode fallback."""
    from app.tools.fundamental.quote_snapshot import QuoteSnapshotTool
    assert hasattr(QuoteSnapshotTool, "fetch_baostock")
    tool = QuoteSnapshotTool()
    assert callable(tool.fetch_baostock)


# ── T09: fetch_baostock returns baostock_kline_fallback on success ────────────────

@pytest.mark.asyncio
async def test_quote_snapshot_fetch_baostock_returns_kline_fallback():
    """fetch_baostock returns source='baostock_kline_fallback' and None PE/PB."""
    from app.tools.fundamental.quote_snapshot import QuoteSnapshotTool

    tool = QuoteSnapshotTool()
    mock_rec = {"ts_code": "600519.SH", "trade_date": "2026-07-01", "close": 1600.0}

    with patch("app.datasource.baostock_client.baostock_client") as mock_client:
        mock_client.get_recent_close = AsyncMock(return_value=mock_rec)
        result = await tool.fetch_baostock("CN", "600519")

    assert result["source"] == "baostock_kline_fallback"
    assert result["close"] == 1600.0
    assert result["pe"] is None
    assert result["pb"] is None
    assert result["total_mv"] is None
    assert result["ts_code"] == "600519.SH"


# ── T10: fetch_baostock raises for non-CN markets ────────────────────────────────

@pytest.mark.asyncio
async def test_quote_snapshot_fetch_baostock_rejects_non_cn():
    """fetch_baostock must raise FundamentalToolError for HK/US markets."""
    from app.tools.fundamental.quote_snapshot import QuoteSnapshotTool
    from app.tools.fundamental.base import FundamentalToolError

    tool = QuoteSnapshotTool()
    with pytest.raises(FundamentalToolError):
        await tool.fetch_baostock("HK", "00700")


# ── T11: SZSE HTTP 400 uses DEBUG not WARNING ────────────────────────────────────

def test_szse_400_uses_debug_log():
    """SZSE tool must log HTTP 400 at DEBUG level, not WARNING."""
    szse_path = _BACKEND_ROOT / "app" / "tools" / "reports" / "szse_report_search_tool.py"
    source = szse_path.read_text()
    # Check DEBUG for 400 is present
    assert "log.debug" in source and "400" in source, \
        "SZSE tool must log HTTP 400 at DEBUG level"
    # Check that the 400 branch uses debug, not warning
    lines = source.splitlines()
    in_400_block = False
    found_debug = False
    for line in lines:
        if "status_code == 400" in line:
            in_400_block = True
        if in_400_block and "log.debug" in line:
            found_debug = True
            break
        if in_400_block and "log.warning" in line and "400" in line:
            pytest.fail("SZSE 400 must use log.debug, not log.warning")
    assert found_debug, "SZSE 400 branch must contain log.debug"


# ── T12: fundamentals_compat special-cases report_documents ──────────────────────

def test_fundamentals_compat_has_report_documents_special_case():
    """fundamentals_compat.get_stock_module_compat must handle report_documents specially."""
    compat_path = _BACKEND_ROOT / "app" / "routers" / "fundamentals_compat.py"
    source = compat_path.read_text()
    assert 'module_key == "report_documents"' in source, \
        "fundamentals_compat must special-case report_documents"
    assert "get_report_documents" in source, \
        "fundamentals_compat must call get_report_documents for report_documents module"


# ── T13: get_recent_close returns None on import failure ─────────────────────────

@pytest.mark.asyncio
async def test_get_recent_close_returns_none_on_baostock_import_failure():
    """get_recent_close must return None if baostock is not installed."""
    import app.datasource.baostock_client as bc

    original_import = __builtins__.__import__ if hasattr(__builtins__, '__import__') else __import__

    with patch.object(bc, "_get_bs_lock") as mock_lock:
        mock_lock.return_value.__aenter__ = AsyncMock(return_value=None)
        mock_lock.return_value.__aexit__ = AsyncMock(return_value=None)

        client = bc.BaoStockClient()
        # Patch asyncio.to_thread to raise ImportError
        with patch("asyncio.to_thread", side_effect=ImportError("baostock")):
            result = await client.get_recent_close("600519.SH")
        assert result is None


# ── T14: fundamentals.py excludes local_path from rows ───────────────────────────

def test_fundamentals_get_report_documents_no_local_path_in_source():
    """fundamentals.py must not include local_path in the rows dict."""
    fund_path = _BACKEND_ROOT / "app" / "routers" / "fundamentals.py"
    source = fund_path.read_text()
    # Find the rows = [...] block
    # local_path must not appear as a key in the row construction
    lines = source.splitlines()
    in_rows_block = False
    for i, line in enumerate(lines):
        if '"local_path"' in line and 'd.local_path' in line:
            pytest.fail(
                f"local_path found in fundamentals.py line {i+1}: {line.strip()!r} — "
                "must be removed to prevent internal path leakage"
            )
