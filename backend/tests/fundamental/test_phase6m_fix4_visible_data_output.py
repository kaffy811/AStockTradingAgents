"""
tests/fundamental/test_phase6m_fix4_visible_data_output.py

Phase 6M-Fix4: Visible Data Output + Diagnostics-Driven Rendering Tests

Covers:
  T01  discovery_attempts included in discover/latest response
  T02  discovery_attempts has year/status/candidate_count fields
  T03  year_fallback reflects in discovery_attempts
  T04  diagnostics visibility hides section when module empty
  T05  diagnostics visibility shows section when module has series
  T06  normalizeEnvelope concept: series→rows alias works
  T07  moduleHasRows with series-only data (backend rows counting)
  T08  moduleHasRows with periods-only data
  T09  moduleHasRows with records-only data
  T10  _count_rows handles series field correctly
  T11  _count_rows handles periods field
  T12  diagnostics endpoint includes modules with rows_count
  T13  discover_latest no fallback: single attempt in discovery_attempts
  T14  discover_latest fallback used: multiple attempts in discovery_attempts
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ── T01: discovery_attempts in discover/latest response ──────────────────────

@pytest.mark.asyncio
async def test_discover_latest_includes_discovery_attempts():
    """discover/latest response must include discovery_attempts list."""
    from httpx import AsyncClient, ASGITransport
    from app.main import app

    async def _fake_discover_latest(stock_code, company_name, report_year):
        return {"candidates": [{"title": "2024年报", "confidence": 0.9}], "total_found": 1, "errors": [], "partial": False}

    with patch("app.routers.report_discovery.report_document_service") as mock_svc:
        mock_svc.upsert_discovered_report = AsyncMock(return_value={"status": "inserted", "report_id": 1})
        with patch("app.routers.report_discovery.report_discovery_agent") as mock_agent:
            mock_agent.discover_latest = _fake_discover_latest

            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                r = await client.post(
                    "/api/v1/stocks/CN/600519/reports/discover/latest",
                    params={"report_year": 2024},
                )

    assert r.status_code == 200
    body = r.json()
    assert "discovery_attempts" in body, f"discovery_attempts missing from: {list(body.keys())}"
    assert isinstance(body["discovery_attempts"], list)


# ── T02: discovery_attempts fields ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_discover_latest_attempts_have_required_fields():
    """Each discovery_attempt must have year, status, candidate_count."""
    from httpx import AsyncClient, ASGITransport
    from app.main import app

    async def _fake_discover_latest(stock_code, company_name, report_year):
        return {"candidates": [{"title": "2024年报", "confidence": 0.85}], "total_found": 1, "errors": [], "partial": False}

    with patch("app.routers.report_discovery.report_document_service") as mock_svc:
        mock_svc.upsert_discovered_report = AsyncMock(return_value={"status": "inserted", "report_id": 2})
        with patch("app.routers.report_discovery.report_discovery_agent") as mock_agent:
            mock_agent.discover_latest = _fake_discover_latest

            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                r = await client.post(
                    "/api/v1/stocks/CN/600519/reports/discover/latest",
                    params={"report_year": 2024, "try_year_fallback": "false"},
                )

    body = r.json()
    attempts = body["discovery_attempts"]
    assert len(attempts) == 1
    a = attempts[0]
    assert "year" in a
    assert "status" in a
    assert "candidate_count" in a
    assert a["year"] == 2024
    assert a["status"] == "candidate_found"
    assert a["candidate_count"] == 1


# ── T03: year_fallback reflected in discovery_attempts ──────────────────────

@pytest.mark.asyncio
async def test_discover_latest_fallback_attempts_list():
    """When fallback is used, discovery_attempts includes both tried years."""
    from httpx import AsyncClient, ASGITransport
    from app.main import app

    async def _fake_discover_latest(stock_code, company_name, report_year):
        if report_year == 2025:
            return {"candidates": [], "total_found": 0, "errors": [], "partial": False}
        return {"candidates": [{"title": "2024年报", "confidence": 0.9}], "total_found": 1, "errors": [], "partial": False}

    with patch("app.routers.report_discovery.report_document_service") as mock_svc:
        mock_svc.upsert_discovered_report = AsyncMock(return_value={"status": "inserted", "report_id": 3})
        with patch("app.routers.report_discovery.report_discovery_agent") as mock_agent:
            mock_agent.discover_latest = _fake_discover_latest

            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                r = await client.post(
                    "/api/v1/stocks/CN/600519/reports/discover/latest",
                    params={"report_year": 2025, "try_year_fallback": "true"},
                )

    body = r.json()
    attempts = body["discovery_attempts"]
    assert len(attempts) == 2
    years = [a["year"] for a in attempts]
    assert 2025 in years
    assert 2024 in years
    statuses = {a["year"]: a["status"] for a in attempts}
    assert statuses[2025] == "empty"
    assert statuses[2024] == "candidate_found"


# ── T04: diagnostics visibility hides section when module empty ──────────────

def test_visibility_hides_section_when_module_empty():
    """compute_section_visibility returns False for empty module."""
    from app.services.free_mode_visibility_service import compute_section_visibility
    diagnostics = [{"module_key": "valuation", "status": "empty", "rows_count": 0}]
    vis = compute_section_visibility(diagnostics)
    assert vis.get("valuation") is False


# ── T05: diagnostics visibility shows section when module has series ─────────

def test_visibility_shows_section_when_module_has_series():
    """compute_section_visibility returns True for module with data."""
    from app.services.free_mode_visibility_service import compute_section_visibility
    diagnostics = [
        {"module_key": "growth", "status": "ok", "rows_count": 8},
        {"module_key": "financial_summary", "status": "ok", "rows_count": 4},
    ]
    vis = compute_section_visibility(diagnostics)
    assert vis.get("growth") is True


# ── T06: normalizeEnvelope concept (Python analog) ──────────────────────────

def test_normalize_envelope_series_to_rows():
    """Verify backend growth tool returns 'series' field (frontend normalizes to 'rows')."""
    # The frontend normalizeEnvelope converts data.series → data.rows
    # This test verifies the backend contract: growth data always has 'series'
    from app.routers.fundamentals_compat import _count_rows
    # Simulate BaoStock growth response: series field, no rows field
    data = {"series": [
        {"end_date": "2024-03-31", "net_profit_yoy_pct": 15.6},
        {"end_date": "2023-12-31", "net_profit_yoy_pct": 8.2},
    ]}
    # _count_rows must recognize 'series' and return correct count
    assert _count_rows(data) == 2
    # And the data structure has no 'rows' key (frontend normalizer adds it)
    assert "rows" not in data


# ── T07: _count_rows handles series field ───────────────────────────────────

def test_count_rows_with_series():
    """_count_rows counts items in 'series' when 'rows' is absent."""
    from app.routers.fundamentals_compat import _count_rows
    data = {"series": [{"a": 1}, {"a": 2}, {"a": 3}]}
    assert _count_rows(data) == 3


# ── T08: _count_rows handles periods field ──────────────────────────────────

def test_count_rows_with_periods():
    """_count_rows counts items in 'periods' field."""
    from app.routers.fundamentals_compat import _count_rows
    data = {"periods": [{"end_date": "2024-03-31"}, {"end_date": "2023-12-31"}]}
    assert _count_rows(data) == 2


# ── T09: _count_rows handles records field ──────────────────────────────────

def test_count_rows_with_records():
    """_count_rows counts items in 'records' field."""
    from app.routers.fundamentals_compat import _count_rows
    data = {"records": [{"id": 1}]}
    assert _count_rows(data) == 1


# ── T10: _count_rows with rows field ────────────────────────────────────────

def test_count_rows_with_rows():
    """_count_rows counts items in 'rows' field."""
    from app.routers.fundamentals_compat import _count_rows
    data = {"rows": [1, 2, 3, 4]}
    assert _count_rows(data) == 4


# ── T11: _count_rows empty/None ─────────────────────────────────────────────

def test_count_rows_empty():
    """_count_rows returns 0 for None and empty dicts."""
    from app.routers.fundamentals_compat import _count_rows
    assert _count_rows(None) == 0
    assert _count_rows({}) == 0
    assert _count_rows({"series": []}) == 0


# ── T12: diagnostics endpoint modules have rows_count ───────────────────────

@pytest.mark.asyncio
async def test_diagnostics_modules_have_rows_count():
    """Diagnostics endpoint returns modules list with rows_count field."""
    from httpx import AsyncClient, ASGITransport
    from app.main import app

    with patch("app.routers.fundamentals_compat.get_aggregator") as mock_agg:
        mock_env = {"ok": True, "partial": False, "data": {"series": [{"a": 1}]}, "errors": []}
        mock_instance = MagicMock()
        mock_instance.fetch_module = AsyncMock(return_value=mock_env)
        mock_agg.return_value = mock_instance

        with patch("sqlalchemy.ext.asyncio.AsyncSession.execute") as mock_exec:
            mock_result = MagicMock()
            mock_result.scalar.return_value = 0
            mock_exec.return_value = mock_result

            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                r = await client.get("/api/v1/stock/600519/fundamentals/diagnostics")

    assert r.status_code == 200
    body = r.json()
    modules = body["modules"]
    assert len(modules) > 0
    for m in modules:
        assert "module_key" in m
        assert "rows_count" in m
        assert "status" in m


# ── T13: no fallback: single attempt ────────────────────────────────────────

@pytest.mark.asyncio
async def test_discover_latest_no_fallback_single_attempt():
    """When try_year_fallback=false, only one attempt is tracked."""
    from httpx import AsyncClient, ASGITransport
    from app.main import app

    async def _fake_discover_latest(stock_code, company_name, report_year):
        return {"candidates": [], "total_found": 0, "errors": [], "partial": False}

    with patch("app.routers.report_discovery.report_document_service") as mock_svc:
        mock_svc.upsert_discovered_report = AsyncMock(return_value={"status": "skipped", "reason": "no candidates"})
        with patch("app.routers.report_discovery.report_discovery_agent") as mock_agent:
            mock_agent.discover_latest = _fake_discover_latest

            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                r = await client.post(
                    "/api/v1/stocks/CN/600519/reports/discover/latest",
                    params={"report_year": 2025, "try_year_fallback": "false"},
                )

    body = r.json()
    assert len(body["discovery_attempts"]) == 1
    assert body["discovery_attempts"][0]["year"] == 2025
    assert body["discovery_attempts"][0]["status"] == "empty"


# ── T14: all years empty: three attempts ────────────────────────────────────

@pytest.mark.asyncio
async def test_discover_latest_all_empty_three_attempts():
    """When all years are empty, three attempts are tracked (try_year_fallback=true)."""
    from httpx import AsyncClient, ASGITransport
    from app.main import app

    async def _fake_discover_latest(stock_code, company_name, report_year):
        return {"candidates": [], "total_found": 0, "errors": [], "partial": False}

    with patch("app.routers.report_discovery.report_document_service") as mock_svc:
        mock_svc.upsert_discovered_report = AsyncMock(return_value={"status": "skipped", "reason": "no candidates"})
        with patch("app.routers.report_discovery.report_discovery_agent") as mock_agent:
            mock_agent.discover_latest = _fake_discover_latest

            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                r = await client.post(
                    "/api/v1/stocks/CN/600519/reports/discover/latest",
                    params={"report_year": 2025, "try_year_fallback": "true"},
                )

    body = r.json()
    assert len(body["discovery_attempts"]) == 3
    years = [a["year"] for a in body["discovery_attempts"]]
    assert years == [2025, 2024, 2023]
    assert all(a["status"] == "empty" for a in body["discovery_attempts"])
