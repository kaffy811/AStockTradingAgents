"""
Phase 6T-C: CNINFO PDF download and text parsing safety tests.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest


def test_whitelist_cninfo_pdf_url_accepted():
    from app.services.company_v2_report_pdf_service import validate_cninfo_pdf_url

    ok, reason = validate_cninfo_pdf_url("https://static.cninfo.com.cn/finalpage/2025-04-25/1223277982.PDF")
    assert ok is True
    assert reason == "ok"


def test_non_whitelist_url_rejected():
    from app.services.company_v2_report_pdf_service import validate_cninfo_pdf_url

    ok, reason = validate_cninfo_pdf_url("https://example.com/fake.PDF")
    assert ok is False
    assert "not allowed" in reason


def test_non_https_url_rejected():
    from app.services.company_v2_report_pdf_service import validate_cninfo_pdf_url

    ok, reason = validate_cninfo_pdf_url("http://static.cninfo.com.cn/finalpage/2025-04-25/1223277982.PDF")
    assert ok is False
    assert "https" in reason


def test_localhost_internal_and_file_urls_rejected():
    from app.services.company_v2_report_pdf_service import validate_cninfo_pdf_url

    for url in [
        "https://localhost/fake.PDF",
        "https://127.0.0.1/fake.PDF",
        "file:///tmp/fake.PDF",
    ]:
        ok, _ = validate_cninfo_pdf_url(url)
        assert ok is False


def test_non_pdf_rejected():
    from app.services.company_v2_report_pdf_service import validate_cninfo_pdf_url

    ok, reason = validate_cninfo_pdf_url("https://static.cninfo.com.cn/finalpage/2025-04-25/report.html")
    assert ok is False
    assert "PDF" in reason


class _FakeScalars:
    def __init__(self, doc):
        self.doc = doc

    def first(self):
        return self.doc


class _FakeResult:
    def __init__(self, doc):
        self.doc = doc

    def scalars(self):
        return _FakeScalars(self.doc)


class _FakeDb:
    def __init__(self, doc):
        self.doc = doc
        self.commits = 0

    async def execute(self, _stmt):
        return _FakeResult(self.doc)

    async def commit(self):
        self.commits += 1


@pytest.mark.asyncio
async def test_pdf_download_stores_hash_and_hides_local_path(monkeypatch, tmp_path):
    from app.models.report_document import ReportDocument
    from app.services.company_v2_report_pdf_service import CompanyV2ReportPdfService

    pdf_content = b"%PDF-1.4\n% phase6tc fixture\n%%EOF"

    class _FakeResponse:
        content = pdf_content
        headers = {"content-type": "application/pdf"}

        def raise_for_status(self):
            return None

    class _FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def get(self, *args, **kwargs):
            return _FakeResponse()

    monkeypatch.setattr("app.services.company_v2_report_pdf_service.httpx.AsyncClient", _FakeClient)

    doc = ReportDocument(
        id=1,
        ts_code="601686.SH",
        pdf_url="https://static.cninfo.com.cn/finalpage/2025-04-25/1223277982.PDF",
        title="2024年年度报告",
    )
    service = CompanyV2ReportPdfService(download_dir=tmp_path)
    result = await service.download_report(1, _FakeDb(doc))

    assert result["ok"] is True
    assert result["status"] == "downloaded"
    assert result["file_hash"]
    assert result["file_size"] == len(pdf_content)
    assert doc.local_path
    assert "local_path" not in result


def test_pdf_parser_handles_text_pdf(monkeypatch, tmp_path):
    from app.services.company_v2_pdf_text_parser import parse_pdf_text

    class _FakePage:
        def extract_text(self):
            return "营业收入 1,234.56 万元\n归属于上市公司股东的净利润 88.8 万元\n" * 4

    class _FakeReader:
        def __init__(self, _path):
            self.pages = [_FakePage(), _FakePage()]

    monkeypatch.setitem(__import__("sys").modules, "pypdf", SimpleNamespace(PdfReader=_FakeReader))
    pdf = tmp_path / "fixture.pdf"
    pdf.write_bytes(b"%PDF-1.4\n%%EOF")

    result = parse_pdf_text(pdf, report_id="r1")
    assert result["parse_status"] == "parsed"
    assert result["page_count"] == 2
    assert result["text_pages"][0]["page"] == 1


def test_low_text_coverage_flagged(monkeypatch, tmp_path):
    from app.services.company_v2_pdf_text_parser import LOW_COVERAGE_CODE, parse_pdf_text

    class _FakePage:
        def extract_text(self):
            return "短"

    class _FakeReader:
        def __init__(self, _path):
            self.pages = [_FakePage()]

    monkeypatch.setitem(__import__("sys").modules, "pypdf", SimpleNamespace(PdfReader=_FakeReader))
    pdf = tmp_path / "low.pdf"
    pdf.write_bytes(b"%PDF-1.4\n%%EOF")

    result = parse_pdf_text(pdf, report_id="r2")
    assert result["parse_status"] == "partial"
    assert LOW_COVERAGE_CODE in result["warnings"]


def test_safe_parse_summary_does_not_return_full_text():
    from app.services.company_v2_pdf_text_parser import safe_parse_summary

    parsed = {"report_id": "r", "page_count": 1, "parse_status": "parsed", "warnings": [], "text_pages": [{"page": 1, "text": "x" * 1000}]}
    summary = safe_parse_summary(parsed, excerpt_chars=50)
    assert len(summary["excerpts"][0]["excerpt"]) == 50
    assert "text_pages" not in summary
