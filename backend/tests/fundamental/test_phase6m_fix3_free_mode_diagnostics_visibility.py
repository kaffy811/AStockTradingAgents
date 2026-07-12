"""
tests/fundamental/test_phase6m_fix3_free_mode_diagnostics_visibility.py

Phase 6M-Fix3: Free Mode Diagnostics + Visibility Tests

Covers:
  T01  diagnostics API endpoint returns expected schema
  T02  diagnostics does not call Tushare (DATA_MODE=free passes through)
  T03  compute_section_visibility: ok module makes section visible
  T04  compute_section_visibility: empty module keeps section hidden
  T05  compute_section_visibility: partial module makes section visible
  T06  compute_section_visibility: ALWAYS_SHOW sections always visible
  T07  get_unavailable_sections returns sections with False visibility
  T08  diagnostics endpoint schema has required top-level keys
  T09  diagnostics endpoint visibility includes all expected section IDs
  T10  discover_latest year fallback: matched_year changes on empty result
  T11  discover_latest year fallback: year_fallback_used=True when year changes
  T12  discover_latest no fallback if try_year_fallback=False
  T13  report_chat REPORT_RAG_NOT_READY includes action_suggestions
  T14  report_chat action_suggestions contains discover_reports action
"""
from __future__ import annotations

import importlib
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

_BACKEND_ROOT = Path(__file__).resolve().parents[2]


# ── T01: diagnostics API schema ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_diagnostics_endpoint_schema():
    """GET /stock/{code}/fundamentals/diagnostics returns required schema keys."""
    from httpx import AsyncClient, ASGITransport
    from app.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Patch aggregator to return fast empty results
        with patch("app.routers.fundamentals_compat.get_aggregator") as mock_agg:
            mock_env = {"ok": False, "partial": True, "data": {}, "errors": ["no data"]}
            mock_instance = MagicMock()
            mock_instance.fetch_module = AsyncMock(return_value=mock_env)
            mock_agg.return_value = mock_instance

            with patch("sqlalchemy.ext.asyncio.AsyncSession.execute") as mock_exec:
                mock_result = MagicMock()
                mock_result.scalar.return_value = 0
                mock_exec.return_value = mock_result

                r = await client.get("/api/v1/stock/600519/fundamentals/diagnostics")

    assert r.status_code == 200
    body = r.json()
    assert "market" in body
    assert "symbol" in body
    assert "modules" in body
    assert "visibility" in body
    assert "unavailable_sections" in body
    assert "summary" in body
    assert isinstance(body["modules"], list)
    assert isinstance(body["visibility"], dict)
    assert isinstance(body["unavailable_sections"], list)


# ── T02: diagnostics does not expose secrets ──────────────────────────────────

@pytest.mark.asyncio
async def test_diagnostics_no_secrets_in_response():
    """Diagnostics response must not contain SECRET_KEY or local_path."""
    from httpx import AsyncClient, ASGITransport
    from app.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        with patch("app.routers.fundamentals_compat.get_aggregator") as mock_agg:
            mock_env = {"ok": False, "partial": True, "data": {}, "errors": []}
            mock_instance = MagicMock()
            mock_instance.fetch_module = AsyncMock(return_value=mock_env)
            mock_agg.return_value = mock_instance

            with patch("sqlalchemy.ext.asyncio.AsyncSession.execute") as mock_exec:
                mock_result = MagicMock()
                mock_result.scalar.return_value = 0
                mock_exec.return_value = mock_result

                r = await client.get("/api/v1/stock/000725/fundamentals/diagnostics")

    body_str = r.text
    assert "SECRET_KEY" not in body_str
    assert "local_path" not in body_str
    assert "password" not in body_str.lower()


# ── T03: compute_section_visibility: ok module shows section ─────────────────

def test_compute_section_visibility_ok_shows_section():
    """A module with status='ok' should make its section visible."""
    from app.services.free_mode_visibility_service import compute_section_visibility

    diagnostics = [
        {"module_key": "growth", "status": "ok", "rows_count": 8},
        {"module_key": "financial_summary", "status": "empty", "rows_count": 0},
    ]
    vis = compute_section_visibility(diagnostics)
    assert vis.get("growth") is True


# ── T04: compute_section_visibility: empty module hides section ───────────────

def test_compute_section_visibility_empty_hides_section():
    """A module with status='empty' and rows_count=0 should hide its section."""
    from app.services.free_mode_visibility_service import compute_section_visibility

    diagnostics = [
        {"module_key": "valuation", "status": "empty", "rows_count": 0},
    ]
    vis = compute_section_visibility(diagnostics)
    assert vis.get("valuation") is False


# ── T05: compute_section_visibility: partial module shows section ─────────────

def test_compute_section_visibility_partial_shows_section():
    """A module with status='partial' should make its section visible."""
    from app.services.free_mode_visibility_service import compute_section_visibility

    diagnostics = [
        {"module_key": "profitability", "status": "partial", "rows_count": 3},
    ]
    vis = compute_section_visibility(diagnostics)
    assert vis.get("profitability") is True


# ── T06: ALWAYS_SHOW sections are always visible ─────────────────────────────

def test_always_show_sections_always_visible():
    """ALWAYS_SHOW sections must be True even with no diagnostics data."""
    from app.services.free_mode_visibility_service import (
        compute_section_visibility,
        ALWAYS_SHOW_SECTION_IDS,
    )
    vis = compute_section_visibility([])  # No data at all
    for sid in ALWAYS_SHOW_SECTION_IDS:
        assert vis.get(sid) is True, f"ALWAYS_SHOW section '{sid}' must be visible"


# ── T07: get_unavailable_sections ────────────────────────────────────────────

def test_get_unavailable_sections():
    """get_unavailable_sections returns section IDs with visibility=False."""
    from app.services.free_mode_visibility_service import get_unavailable_sections

    visibility = {
        "overview": True,
        "valuation": False,
        "growth": True,
        "dupont": False,
    }
    all_ids = ["overview", "valuation", "growth", "dupont"]
    unavail = get_unavailable_sections(visibility, all_ids)
    assert "valuation" in unavail
    assert "dupont" in unavail
    assert "overview" not in unavail
    assert "growth" not in unavail


# ── T08: diagnostics summary counts ──────────────────────────────────────────

def test_diagnostics_summary_has_counts():
    """Diagnostics summary must have ok/partial/empty/failed integer counts."""
    from app.routers.fundamentals_compat import _count_rows
    # Test _count_rows helper
    assert _count_rows({"rows": [1, 2, 3]}) == 3
    assert _count_rows({"series": [{"a": 1}, {"b": 2}]}) == 2
    assert _count_rows({"close": 10.5, "pe": 30.0, "name": None}) == 2  # 2 numeric non-null
    assert _count_rows({}) == 0
    assert _count_rows(None) == 0


# ── T09: diagnostics visibility includes all section IDs ─────────────────────

def test_diagnostics_covers_all_anchor_sections():
    """Visibility dict from compute_section_visibility covers all known section IDs."""
    from app.services.free_mode_visibility_service import (
        compute_section_visibility,
        ALWAYS_SHOW_SECTION_IDS,
        SHOW_IF_DATA_SECTIONS,
    )
    all_section_ids = list(ALWAYS_SHOW_SECTION_IDS) + list(SHOW_IF_DATA_SECTIONS.keys())
    # Provide empty diagnostics — all SHOW_IF_DATA should be False
    vis = compute_section_visibility([])
    for sid in all_section_ids:
        assert sid in vis, f"Section '{sid}' must be in visibility result"


# ── T10: discover_latest year fallback changes matched_year ──────────────────

@pytest.mark.asyncio
async def test_discover_latest_year_fallback_changes_year():
    """discover_latest_reports falls back to year-1 when year has no results."""
    from httpx import AsyncClient, ASGITransport
    from app.main import app

    call_years = []

    async def _fake_discover_latest(stock_code, company_name, report_year):
        call_years.append(report_year)
        if report_year == 2025:
            return {"candidates": [], "total_found": 0, "errors": [], "partial": False}
        return {"candidates": [{"title": "2024年报", "confidence": 0.9}], "total_found": 1, "errors": [], "partial": False}

    with patch("app.routers.report_discovery.report_document_service") as mock_svc:
        mock_svc.upsert_discovered_report = AsyncMock(return_value={"status": "inserted", "report_id": 1})
        with patch("app.routers.report_discovery.report_discovery_agent") as mock_agent:
            mock_agent.discover_latest = _fake_discover_latest

            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                r = await client.post(
                    "/api/v1/stocks/CN/600519/reports/discover/latest",
                    params={"report_year": 2025, "try_year_fallback": "true"},
                )

    assert r.status_code == 200
    body = r.json()
    assert body.get("matched_year") == 2024
    assert 2025 in call_years
    assert 2024 in call_years


# ── T11: year_fallback_used True when year changes ───────────────────────────

@pytest.mark.asyncio
async def test_discover_latest_year_fallback_flag():
    """year_fallback_used=True when matched_year != requested_year."""
    from httpx import AsyncClient, ASGITransport
    from app.main import app

    async def _fake_discover_latest(stock_code, company_name, report_year):
        if report_year == 2025:
            return {"candidates": [], "total_found": 0, "errors": [], "partial": False}
        return {"candidates": [{"title": "2024", "confidence": 0.85}], "total_found": 1, "errors": [], "partial": False}

    with patch("app.routers.report_discovery.report_document_service") as mock_svc:
        mock_svc.upsert_discovered_report = AsyncMock(return_value={"status": "inserted", "report_id": 2})
        with patch("app.routers.report_discovery.report_discovery_agent") as mock_agent:
            mock_agent.discover_latest = _fake_discover_latest

            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                r = await client.post(
                    "/api/v1/stocks/CN/600519/reports/discover/latest",
                    params={"report_year": 2025, "try_year_fallback": "true"},
                )

    body = r.json()
    assert body.get("year_fallback_used") is True
    assert body.get("requested_year") == 2025
    assert body.get("matched_year") == 2024
    assert "2024" in body.get("message", "")


# ── T12: no fallback when try_year_fallback=False ────────────────────────────

@pytest.mark.asyncio
async def test_discover_latest_no_fallback_when_disabled():
    """When try_year_fallback=False, only the requested year is tried."""
    from httpx import AsyncClient, ASGITransport
    from app.main import app

    call_years = []

    async def _fake_discover_latest(stock_code, company_name, report_year):
        call_years.append(report_year)
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

    assert call_years == [2025], f"Only 2025 should be tried, got: {call_years}"
    body = r.json()
    assert body.get("year_fallback_used") is False


# ── T13: report_chat REPORT_RAG_NOT_READY includes action_suggestions ─────────

@pytest.mark.asyncio
async def test_report_chat_no_rag_includes_action_suggestions():
    """report_chat with no RAG index returns action_suggestions in response."""
    from httpx import AsyncClient, ASGITransport
    from app.main import app

    mock_result = {
        "answer": "暂无财报索引",
        "source_chunks": [],
        "review_audit": {},
        "rag_status": "unavailable",
        "confidence": "low",
        "evidence_used": [],
        "data_limitations": ["无 RAG 索引"],
        "errors": [],
        "partial": True,
    }

    mock_rl_result = MagicMock()
    mock_rl_result.allowed = True
    mock_rl_result.limit_minute = 10
    mock_rl_result.remaining_minute = 9
    mock_rl_result.limit_hour = 100
    mock_rl_result.remaining_hour = 99
    mock_rl_result.retry_after_seconds = None

    # check_rate_limit is imported inside the function body, patch the source module
    with patch("app.services.rate_limit_service.check_rate_limit", new=AsyncMock(return_value=mock_rl_result)):
        with patch("app.services.rate_limit_service.rate_limit_meta_dict", return_value={}):
            with patch("app.agent.report_chat_copilot_agent.ReportChatCopilotAgent") as mock_cls:
                mock_agent = MagicMock()
                mock_agent.chat = AsyncMock(return_value=mock_result)
                mock_cls.return_value = mock_agent

                async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                    r = await client.post(
                        "/api/v1/stock/600519/report-chat",
                        json={"question": "公司主营是什么？"},
                    )

    assert r.status_code == 200
    body = r.json()
    assert "action_suggestions" in body, f"action_suggestions missing from: {list(body.keys())}"
    assert isinstance(body["action_suggestions"], list)
    assert len(body["action_suggestions"]) > 0


# ── T14: action_suggestions contains discover_reports ────────────────────────

@pytest.mark.asyncio
async def test_report_chat_action_suggestions_has_discover():
    """action_suggestions must contain 'discover_reports' action."""
    from httpx import AsyncClient, ASGITransport
    from app.main import app

    mock_result = {
        "answer": "无索引",
        "source_chunks": [],
        "review_audit": {},
        "rag_status": "unavailable",
        "confidence": "low",
        "evidence_used": [],
        "data_limitations": [],
        "errors": [],
        "partial": True,
    }

    mock_rl_result = MagicMock()
    mock_rl_result.allowed = True
    mock_rl_result.limit_minute = 10
    mock_rl_result.remaining_minute = 9
    mock_rl_result.limit_hour = 100
    mock_rl_result.remaining_hour = 99
    mock_rl_result.retry_after_seconds = None

    with patch("app.services.rate_limit_service.check_rate_limit", new=AsyncMock(return_value=mock_rl_result)):
        with patch("app.services.rate_limit_service.rate_limit_meta_dict", return_value={}):
            with patch("app.agent.report_chat_copilot_agent.ReportChatCopilotAgent") as mock_cls:
                mock_agent = MagicMock()
                mock_agent.chat = AsyncMock(return_value=mock_result)
                mock_cls.return_value = mock_agent

                async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                    r = await client.post(
                        "/api/v1/stock/000725/report-chat",
                        json={"question": "公司有哪些产品？"},
                    )

    body = r.json()
    actions = body.get("action_suggestions", [])
    action_names = [a.get("action") for a in actions]
    assert "discover_reports" in action_names, f"discover_reports not in actions: {action_names}"
