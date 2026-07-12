"""
test_phase6d_report_discovery.py — Phase 6D: Report Discovery Agent + Tools

Tests:
  1.  discover() returns empty when all sources return empty
  2.  CNINFO tool returns candidates with correct schema
  3.  SSE tool returns empty for non-SSE stock
  4.  SZSE tool returns empty for non-SZSE stock
  5.  SZSE tool searches for SZSE stock (000725)
  6.  score_candidate: confidence >= 0.75 for good match
  7.  score_candidate: summary keywords reduce confidence
  8.  score_candidate: non-periodic report keywords disqualify
  9.  confidence >= 0.75 triggers auto insert
  10. confidence < 0.75 is skipped by upsert
  11. duplicate pdf_url is not inserted twice
  12. _ts_code_from_stock_code conversion
  13. ReportDiscoveryAgent deduplicates by pdf_url
  14. discover_latest calls all 4 report types
  15. PDF proxy route only allows known report_ids (unit test via router logic)
"""
from __future__ import annotations

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_candidate(
    title="贵州茅台2024年年度报告",
    stock_code="600519",
    company_name="贵州茅台",
    report_type="annual",
    report_year=2024,
    confidence=0.90,
    pdf_url="http://static.cninfo.com.cn/finalpage/2025-04-30/test.PDF",
    source="cninfo",
):
    return {
        "title":         title,
        "stock_code":    stock_code,
        "company_name":  company_name,
        "report_type":   report_type,
        "report_year":   report_year,
        "period":        "20241231",
        "ann_date":      "20250430",
        "source":        source,
        "source_url":    "http://www.cninfo.com.cn/new/disclosure/detail?announcementId=test",
        "pdf_url":       pdf_url,
        "confidence":    confidence,
        "match_reasons": ["stock_code matched", "company_name matched", "年度报告 matched", "2024 matched"],
        "warnings":      [],
    }


# ── 1. discover() returns empty when all sources fail ────────────────────────

@pytest.mark.asyncio
async def test_discover_returns_empty_when_all_sources_empty():
    from app.agents.report_discovery_agent import ReportDiscoveryAgent

    agent = ReportDiscoveryAgent()
    with patch("app.agents.report_discovery_agent.cninfo_tool") as mock_c, \
         patch("app.agents.report_discovery_agent.sse_tool") as mock_s, \
         patch("app.agents.report_discovery_agent.szse_tool") as mock_z:
        mock_c.search = AsyncMock(return_value=[])
        mock_s.search = AsyncMock(return_value=[])
        mock_z.search = AsyncMock(return_value=[])

        result = await agent.discover("600519", "贵州茅台", "annual", 2024)

    assert result["total_found"] == 0
    assert result["partial"] is True
    assert result["candidates"] == []


# ── 2. CNINFO tool returns candidates with correct schema ─────────────────────

@pytest.mark.asyncio
async def test_cninfo_tool_returns_candidates_with_schema():
    from app.tools.reports.cninfo_report_search_tool import CninfoReportSearchTool
    from app.tools.reports.base import CANDIDATE_SCHEMA_KEYS

    tool = CninfoReportSearchTool()
    mock_response = {
        "announcements": [{
            "secCode": "600519",
            "secName": "贵州茅台",
            "orgId": "9900000291",
            "announcementId": "1218018101",
            "announcementTitle": "贵州茅台酒股份有限公司2024年年度报告",
            "announcementTime": 1746028800000,  # 2025-04-30 UTC ms
            "adjunctUrl": "finalpage/2025-04-30/1218018101.PDF",
            "adjunctType": "PDF",
        }],
        "hasMore": False,
        "totals": 1,
    }

    with patch("app.tools.reports.cninfo_report_search_tool.httpx.AsyncClient") as mock_client_cls, \
         patch("app.tools.reports.cninfo_report_search_tool.asyncio.sleep", new_callable=AsyncMock):
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json = MagicMock(return_value=mock_response)
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_client_cls.return_value = mock_client

        candidates = await tool.search("600519", "贵州茅台", "annual", 2024)

    assert len(candidates) > 0
    c = candidates[0]
    for key in CANDIDATE_SCHEMA_KEYS:
        assert key in c, f"Missing key '{key}' in CNINFO candidate"
    assert c["source"] == "cninfo"
    assert "cninfo.com.cn" in c["pdf_url"]
    assert c["report_year"] == 2024


# ── 3. SSE tool skips non-SSE stocks ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_sse_tool_skips_non_sse_stock():
    from app.tools.reports.sse_report_search_tool import SSEReportSearchTool

    tool = SSEReportSearchTool()
    with patch("app.tools.reports.sse_report_search_tool.asyncio.sleep", new_callable=AsyncMock):
        result = await tool.search("000725", "京东方A", "annual", 2024)

    assert result == [], "SSE tool should return empty for non-SSE (SZ) stock"


# ── 4. SZSE tool skips non-SZSE stocks ───────────────────────────────────────

@pytest.mark.asyncio
async def test_szse_tool_skips_non_szse_stock():
    from app.tools.reports.szse_report_search_tool import SZSEReportSearchTool

    tool = SZSEReportSearchTool()
    with patch("app.tools.reports.szse_report_search_tool.asyncio.sleep", new_callable=AsyncMock):
        result = await tool.search("600519", "贵州茅台", "annual", 2024)

    assert result == [], "SZSE tool should return empty for non-SZSE (SH) stock"


# ── 5. SZSE tool handles SZSE stock with empty response ──────────────────────

@pytest.mark.asyncio
async def test_szse_tool_handles_szse_stock_empty_response():
    from app.tools.reports.szse_report_search_tool import SZSEReportSearchTool

    tool = SZSEReportSearchTool()

    with patch("app.tools.reports.szse_report_search_tool.httpx.AsyncClient") as mock_client_cls, \
         patch("app.tools.reports.szse_report_search_tool.asyncio.sleep", new_callable=AsyncMock):
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json = MagicMock(return_value={"data": []})
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_client_cls.return_value = mock_client

        result = await tool.search("000725", "京东方A", "annual", 2024)

    assert result == []


# ── 6. score_candidate: good match yields confidence >= 0.75 ─────────────────

def test_score_candidate_good_match_high_confidence():
    from app.tools.reports.base import score_candidate

    confidence, reasons, warnings = score_candidate(
        title="贵州茅台酒股份有限公司2024年年度报告",
        stock_code="600519",
        company_name="贵州茅台",
        report_type="annual",
        report_year=2024,
        ann_date_str="20250430",
        source="cninfo",
    )

    assert confidence >= 0.75, f"Good match should yield confidence >= 0.75, got {confidence}"
    assert len(reasons) > 0
    assert "年度报告" in " ".join(reasons) or "annual" in " ".join(reasons) or len(reasons) >= 2


# ── 7. score_candidate: summary keyword reduces confidence ────────────────────

def test_score_candidate_summary_reduces_confidence():
    from app.tools.reports.base import score_candidate

    conf_full, _, _ = score_candidate(
        title="贵州茅台2024年年度报告",
        stock_code="600519", company_name="贵州茅台",
        report_type="annual", report_year=2024,
        ann_date_str="20250430", source="cninfo",
    )
    conf_summary, _, warnings = score_candidate(
        title="贵州茅台2024年年度报告摘要",
        stock_code="600519", company_name="贵州茅台",
        report_type="annual", report_year=2024,
        ann_date_str="20250430", source="cninfo",
    )

    assert conf_summary < conf_full, "Summary version should have lower confidence"
    assert any("摘要" in w for w in warnings), "Warning about 摘要 should be present"


# ── 8. score_candidate: skip keywords disqualify ─────────────────────────────

def test_score_candidate_skip_keywords_disqualify():
    from app.tools.reports.base import score_candidate

    confidence, reasons, _ = score_candidate(
        title="关于2024年审计报告的公告",
        stock_code="600519", company_name="贵州茅台",
        report_type="annual", report_year=2024,
        ann_date_str="20250430", source="cninfo",
    )

    assert confidence < 0.5, f"Non-periodic report should be disqualified, got confidence={confidence}"


# ── 9. upsert_discovered_report: high confidence → inserted ──────────────────

@pytest.mark.asyncio
async def test_upsert_high_confidence_inserts():
    from app.services.report_document_service import ReportDocumentService

    service = ReportDocumentService()
    candidate = _make_candidate(confidence=0.90)

    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.first.return_value = None  # no existing
    mock_db.execute = AsyncMock(return_value=mock_result)

    # Make doc.id accessible after flush
    inserted_doc = MagicMock()
    inserted_doc.id = 42

    def _add_side_effect(doc):
        doc.id = 42

    mock_db.add = MagicMock(side_effect=_add_side_effect)
    mock_db.flush = AsyncMock()
    mock_db.commit = AsyncMock()

    result = await service.upsert_discovered_report(candidate, mock_db)

    assert result["status"] == "inserted", f"Expected inserted, got {result}"
    mock_db.add.assert_called_once()
    mock_db.commit.assert_called_once()


# ── 10. upsert_discovered_report: low confidence → skipped ───────────────────

@pytest.mark.asyncio
async def test_upsert_low_confidence_skipped():
    from app.services.report_document_service import ReportDocumentService

    service = ReportDocumentService()
    candidate = _make_candidate(confidence=0.60)

    mock_db = AsyncMock()
    result = await service.upsert_discovered_report(candidate, mock_db)

    assert result["status"] == "skipped"
    assert "confidence" in result["reason"]
    mock_db.add.assert_not_called()


# ── 11. upsert_discovered_report: duplicate pdf_url → exists ─────────────────

@pytest.mark.asyncio
async def test_upsert_duplicate_pdf_url_returns_exists():
    from app.services.report_document_service import ReportDocumentService
    from app.models.report_document import ReportDocument

    service = ReportDocumentService()
    candidate = _make_candidate(confidence=0.90, pdf_url="http://static.cninfo.com.cn/finalpage/2025-04-30/dup.PDF")

    # Simulate existing document with same pdf_url
    existing_doc = MagicMock(spec=ReportDocument)
    existing_doc.id = 99

    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.first.return_value = existing_doc
    mock_db.execute = AsyncMock(return_value=mock_result)

    result = await service.upsert_discovered_report(candidate, mock_db)

    assert result["status"] == "exists"
    assert result["report_id"] == 99
    mock_db.add.assert_not_called()


# ── 12. _ts_code_from_stock_code conversions ─────────────────────────────────

def test_ts_code_from_stock_code():
    from app.services.report_document_service import _ts_code_from_stock_code

    assert _ts_code_from_stock_code("600519") == "600519.SH"
    assert _ts_code_from_stock_code("000725") == "000725.SZ"
    assert _ts_code_from_stock_code("300750") == "300750.SZ"
    assert _ts_code_from_stock_code("600519.SH") == "600519.SH"  # passthrough


# ── 13. ReportDiscoveryAgent deduplicates by pdf_url ─────────────────────────

@pytest.mark.asyncio
async def test_discovery_agent_deduplicates_by_pdf_url():
    from app.agents.report_discovery_agent import ReportDiscoveryAgent

    same_pdf = "http://static.cninfo.com.cn/finalpage/2025-04-30/shared.PDF"
    c1 = _make_candidate(pdf_url=same_pdf, source="cninfo", confidence=0.90)
    c2 = _make_candidate(pdf_url=same_pdf, source="sse", confidence=0.85)  # same PDF, different source

    agent = ReportDiscoveryAgent()
    with patch("app.agents.report_discovery_agent.cninfo_tool") as mock_c, \
         patch("app.agents.report_discovery_agent.sse_tool") as mock_s, \
         patch("app.agents.report_discovery_agent.szse_tool") as mock_z:
        mock_c.search = AsyncMock(return_value=[c1])
        mock_s.search = AsyncMock(return_value=[c2])
        mock_z.search = AsyncMock(return_value=[])

        result = await agent.discover("600519", "贵州茅台", "annual", 2024)

    # Should only have 1 candidate (deduplicated by pdf_url)
    assert result["total_found"] == 1, f"Expected 1 deduplicated candidate, got {result['total_found']}"


# ── 14. discover_latest calls all 4 report types ─────────────────────────────

@pytest.mark.asyncio
async def test_discover_latest_calls_all_report_types():
    from app.agents.report_discovery_agent import ReportDiscoveryAgent

    called_types = []

    async def _mock_discover(stock_code, company_name, report_type, report_year):
        called_types.append(report_type)
        c = _make_candidate(report_type=report_type, confidence=0.80)
        return {
            "candidates": [c],
            "total_found": 1,
            "sources_searched": ["cninfo"],
            "high_confidence": [c],
            "errors": [],
            "partial": False,
        }

    agent = ReportDiscoveryAgent()
    with patch.object(agent, "discover", side_effect=_mock_discover):
        await agent.discover_latest("600519", "贵州茅台", 2024)

    assert set(called_types) == {"annual", "semi", "q1", "q3"}, \
        f"Expected all 4 report types called, got {called_types}"


# ── 15. PDF proxy route blocks unknown report_id ─────────────────────────────

@pytest.mark.asyncio
async def test_pdf_proxy_blocks_unknown_report_id():
    """report_document_service.get_by_id returns None → router should raise 404."""
    from app.services.report_document_service import ReportDocumentService

    service = ReportDocumentService()
    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.first.return_value = None  # not found
    mock_db.execute = AsyncMock(return_value=mock_result)

    doc = await service.get_by_id(99999, mock_db)
    assert doc is None, "Unknown report_id should return None (router then raises 404)"
