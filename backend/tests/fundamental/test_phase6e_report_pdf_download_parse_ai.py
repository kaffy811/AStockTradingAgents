"""
test_phase6e_report_pdf_download_parse_ai.py — Phase 6E: PDF Download + Parse + AI Integration

Tests:
  1.  download: report_id not found returns failed
  2.  download: no pdf_url returns failed
  3.  download: untrusted domain returns failed
  4.  download: already downloaded + file exists returns exists
  5.  download: content-type mismatch returns failed
  6.  download: file too large returns failed
  7.  download: successful download returns downloaded + updates db fields
  8.  parse: report_id not found returns failed
  9.  parse: download_status != downloaded returns skipped
  10. parse: local file not found returns failed
  11. parse: successful extraction returns parsed + sets text_excerpt
  12. parse: get_text returns full text_excerpt
  13. fundamental_analyst: source_reports injected into user prompt
"""
from __future__ import annotations

import asyncio
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch, mock_open


# ── Helper: mock ReportDocument ───────────────────────────────────────────────

def _mock_doc(
    report_id=1,
    pdf_url="http://static.cninfo.com.cn/finalpage/2025-04-30/test.PDF",
    download_status="pending",
    local_path=None,
    file_sha256=None,
    file_size=None,
    parse_status="pending",
    text_excerpt=None,
    ts_code="600519.SH",
    title="贵州茅台2024年年度报告",
    report_type="annual",
    period_end="2024-12-31",
):
    doc = MagicMock()
    doc.id = report_id
    doc.pdf_url = pdf_url
    doc.download_status = download_status
    doc.local_path = local_path
    doc.file_sha256 = file_sha256
    doc.file_size = file_size
    doc.parse_status = parse_status
    doc.text_excerpt = text_excerpt
    doc.ts_code = ts_code
    doc.title = title
    doc.report_type = report_type
    doc.period_end = period_end
    doc.parsed = text_excerpt is not None
    return doc


def _mock_db_with_doc(doc):
    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.first.return_value = doc
    mock_db.execute = AsyncMock(return_value=mock_result)
    mock_db.commit = AsyncMock()
    mock_db.rollback = AsyncMock()
    return mock_db


def _mock_db_no_doc():
    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.first.return_value = None
    mock_db.execute = AsyncMock(return_value=mock_result)
    return mock_db


# ── 1. download: report_id not found ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_download_report_not_found():
    from app.services.report_pdf_download_service import ReportPdfDownloadService

    svc = ReportPdfDownloadService(download_dir=Path("/tmp/test_rdl"))
    db = _mock_db_no_doc()
    result = await svc.download(99999, db)
    assert result["status"] == "failed"
    assert "not found" in result["reason"]


# ── 2. download: no pdf_url ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_download_no_pdf_url():
    from app.services.report_pdf_download_service import ReportPdfDownloadService

    svc = ReportPdfDownloadService(download_dir=Path("/tmp/test_rdl"))
    doc = _mock_doc(pdf_url="")
    db = _mock_db_with_doc(doc)
    result = await svc.download(1, db)
    assert result["status"] == "failed"
    assert "no pdf_url" in result["reason"]


# ── 3. download: untrusted domain ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_download_untrusted_domain():
    from app.services.report_pdf_download_service import ReportPdfDownloadService

    svc = ReportPdfDownloadService(download_dir=Path("/tmp/test_rdl"))
    doc = _mock_doc(pdf_url="http://evil.com/malware.pdf")
    db = _mock_db_with_doc(doc)
    result = await svc.download(1, db)
    assert result["status"] == "failed"
    assert "untrusted" in result["reason"]


# ── 4. download: already downloaded + file exists ─────────────────────────────

@pytest.mark.asyncio
async def test_download_already_downloaded(tmp_path):
    from app.services.report_pdf_download_service import ReportPdfDownloadService

    existing_file = tmp_path / "existing.pdf"
    existing_file.write_bytes(b"%PDF-1.4 mock content")

    svc = ReportPdfDownloadService(download_dir=tmp_path)
    doc = _mock_doc(download_status="downloaded", local_path=str(existing_file))
    db = _mock_db_with_doc(doc)
    result = await svc.download(1, db)
    assert result["status"] == "exists"


# ── 5. download: content-type mismatch ───────────────────────────────────────

@pytest.mark.asyncio
async def test_download_content_type_mismatch(tmp_path):
    from app.services.report_pdf_download_service import ReportPdfDownloadService

    svc = ReportPdfDownloadService(download_dir=tmp_path)
    doc = _mock_doc()
    db = _mock_db_with_doc(doc)

    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.headers = {"content-type": "text/html"}
    mock_resp.content = b"<html>Not a PDF</html>"

    with patch("app.services.report_pdf_download_service.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_cls.return_value = mock_client

        result = await svc.download(1, db)

    assert result["status"] == "failed"
    assert "Content-Type" in result["reason"] or "content-type" in result["reason"].lower()


# ── 6. download: file too large ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_download_file_too_large(tmp_path):
    from app.services.report_pdf_download_service import ReportPdfDownloadService, _MAX_SIZE_BYTES

    svc = ReportPdfDownloadService(download_dir=tmp_path)
    doc = _mock_doc()
    db = _mock_db_with_doc(doc)

    oversized = b"X" * (_MAX_SIZE_BYTES + 1)
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.headers = {"content-type": "application/pdf"}
    mock_resp.content = oversized

    with patch("app.services.report_pdf_download_service.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_cls.return_value = mock_client

        result = await svc.download(1, db)

    assert result["status"] == "failed"
    assert "large" in result["reason"] or "limit" in result["reason"]


# ── 7. download: successful download ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_download_success(tmp_path):
    from app.services.report_pdf_download_service import ReportPdfDownloadService

    svc = ReportPdfDownloadService(download_dir=tmp_path)
    doc = _mock_doc()
    db = _mock_db_with_doc(doc)

    pdf_content = b"%PDF-1.4 sample content for test"
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.headers = {"content-type": "application/pdf"}
    mock_resp.content = pdf_content

    with patch("app.services.report_pdf_download_service.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_cls.return_value = mock_client

        result = await svc.download(1, db)

    assert result["status"] == "downloaded", f"Expected downloaded, got: {result}"
    assert result["file_size"] == len(pdf_content)
    assert result["sha256"]
    # Verify DB fields were set
    assert doc.download_status == "downloaded"
    assert doc.file_sha256 == result["sha256"]
    assert doc.file_size == len(pdf_content)


# ── 8. parse: report_id not found ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_parse_report_not_found():
    from app.services.report_text_extract_service import ReportTextExtractService

    svc = ReportTextExtractService()
    db = _mock_db_no_doc()
    result = await svc.parse(99999, db)
    assert result["status"] == "failed"
    assert "not found" in result["reason"]


# ── 9. parse: download_status not downloaded ──────────────────────────────────

@pytest.mark.asyncio
async def test_parse_not_downloaded_skipped():
    from app.services.report_text_extract_service import ReportTextExtractService

    svc = ReportTextExtractService()
    doc = _mock_doc(download_status="pending")
    db = _mock_db_with_doc(doc)
    result = await svc.parse(1, db)
    assert result["status"] == "skipped"
    assert "downloaded" in result["reason"]


# ── 10. parse: local file not found ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_parse_local_file_missing():
    from app.services.report_text_extract_service import ReportTextExtractService

    svc = ReportTextExtractService()
    doc = _mock_doc(download_status="downloaded", local_path="/nonexistent/file.pdf")
    db = _mock_db_with_doc(doc)
    result = await svc.parse(1, db)
    assert result["status"] == "failed"
    assert "not found" in result["reason"]


# ── 11. parse: successful extraction ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_parse_success(tmp_path):
    from app.services.report_text_extract_service import ReportTextExtractService

    # Create a fake "pdf" file (we'll mock the extraction)
    fake_pdf = tmp_path / "report_1.pdf"
    fake_pdf.write_bytes(b"%PDF-1.4 fake")

    svc = ReportTextExtractService()
    doc = _mock_doc(download_status="downloaded", local_path=str(fake_pdf))
    db = _mock_db_with_doc(doc)

    # Phase 6T contract: parse() now uses page-level parse_pdf_text (pypdf sidecar
    # pipeline); the old _extract_text_pdfminer mock contract is superseded.
    fake_text = "贵州茅台2024年年度报告\n" + "正文内容 " * 500  # >3000 chars
    fake_parsed = {
        "report_id": "1",
        "page_count": 2,
        "text_pages": [
            {"page": 1, "text": fake_text[: len(fake_text) // 2]},
            {"page": 2, "text": fake_text[len(fake_text) // 2:]},
        ],
        "parse_status": "parsed",
        "warnings": [],
    }

    with patch("app.services.report_text_extract_service.parse_pdf_text", return_value=fake_parsed):
        result = await svc.parse(1, db)

    assert result["status"] == "parsed", f"Expected parsed, got: {result}"
    assert result["page_count"] == 2
    assert result["chars"] > 0
    assert doc.parsed is True
    assert doc.parse_status == "parsed"
    assert doc.text_excerpt is not None
    assert len(doc.text_excerpt) <= 8000


# ── 12. get_text returns text_excerpt ────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_text_returns_excerpt():
    from app.services.report_text_extract_service import ReportTextExtractService

    svc = ReportTextExtractService()
    sample_text = "年度报告正文摘录内容" * 100
    doc = _mock_doc(
        download_status="downloaded",
        parse_status="parsed",
        text_excerpt=sample_text,
    )
    db = _mock_db_with_doc(doc)
    result = await svc.get_text(1, db)
    assert result["found"] is True
    assert result["text"] == sample_text
    assert result["chars"] == len(sample_text)


# ── 13. fundamental_analyst: source_reports injected into prompt ──────────────

def test_fundamental_analyst_source_reports_injected():
    from app.agents.fundamental_analyst import FundamentalAnalystAgent
    from unittest.mock import MagicMock

    mock_llm = MagicMock()
    mock_llm.chat = MagicMock(return_value="# 分析报告")

    mock_svc = MagicMock()
    mock_svc.get_fundamentals = MagicMock(return_value={
        "data_quality": {"provider": "baostock", "latest_report_date": "2024-12-31"},
        "company": {"name": "贵州茅台", "industry": "白酒"},
        "valuation": {"pe": 30.0, "pb": 10.0, "ps": None, "market_cap": 1e12, "dividend_yield": None},
        "profitability": {"roe": 35.0, "gross_margin": 92.0, "net_margin": 50.0},
        "growth": {"revenue_growth_yoy": 18.0, "net_profit_growth_yoy": 20.0},
        "financial_health": {"debt_ratio": 20.0, "operating_cashflow": 5e10},
    })

    agent = FundamentalAnalystAgent(llm=mock_llm, svc=mock_svc)

    source_reports = [{
        "title": "贵州茅台2024年年度报告",
        "report_type": "annual",
        "period_end": "2024-12-31",
        "text_excerpt": "本报告期营业收入增长18%，净利润增长20%...",
    }]

    agent.analyze("CN", "600519", output_language="zh-CN", source_reports=source_reports)

    # The LLM should have been called
    assert mock_llm.chat.called

    # Check the user message contains source_reports content
    call_args = mock_llm.chat.call_args
    messages = call_args[0][0]
    user_msg = next((m for m in messages if m["role"] == "user"), None)
    assert user_msg is not None
    assert "年报摘录" in user_msg["content"] or "source_reports" in user_msg["content"].lower() or "贵州茅台2024年年度报告" in user_msg["content"]
