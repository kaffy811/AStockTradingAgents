from __future__ import annotations

import asyncio


class _FakeScalars:
    def __init__(self, doc):
        self._doc = doc

    def first(self):
        return self._doc


class _FakeResult:
    def __init__(self, doc):
        self._doc = doc

    def scalars(self):
        return _FakeScalars(self._doc)


class _FakeDb:
    def __init__(self, doc):
        self.doc = doc

    async def execute(self, _stmt):
        return _FakeResult(self.doc)

    async def commit(self):
        return None

    async def rollback(self):
        return None


def test_parse_writes_sidecar_and_is_idempotent(tmp_path, monkeypatch):
    from app.models.report_document import ReportDocument
    import app.services.report_text_extract_service as module

    pdf = tmp_path / "report.pdf"
    pdf.write_bytes(b"%PDF-1.4\n%%EOF")
    doc = ReportDocument(
        id=1,
        ts_code="600519.SH",
        report_type="annual",
        report_year=2024,
        title="2024 annual",
        pdf_url="https://static.cninfo.com.cn/1.pdf",
        local_path=str(pdf),
        download_status="downloaded",
        parse_status="pending",
        parsed=False,
    )
    monkeypatch.setattr(module, "parse_pdf_text", lambda path, report_id="": {"report_id": str(report_id), "page_count": 2, "text_pages": [{"page": 1, "text": "营业收入"}, {"page": 2, "text": "净利润"}], "parse_status": "parsed", "warnings": []})

    first = asyncio.run(module.report_text_extract_service.parse(1, _FakeDb(doc)))
    second = asyncio.run(module.report_text_extract_service.parse(1, _FakeDb(doc)))

    assert first["status"] == "parsed"
    assert second["status"] == "parsed"
    assert pdf.with_suffix(".pages.json").exists()
    assert doc.parsed is True
