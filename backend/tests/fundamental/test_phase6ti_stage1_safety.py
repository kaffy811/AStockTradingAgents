from __future__ import annotations

import asyncio
import json


class _FakeScalars:
    def __init__(self, doc):
        self._doc = doc

    def all(self):
        return [self._doc]

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


def _make_doc(tmp_path):
    from app.models.report_document import ReportDocument

    pdf = tmp_path / "report.pdf"
    pdf.write_bytes(b"%PDF-1.4\n%%EOF")
    return ReportDocument(
        id=1,
        ts_code="601686.SH",
        report_type="annual",
        report_year=2024,
        title="2024 annual",
        disclosure_date="2025-04-01",
        pdf_url="https://static.cninfo.com.cn/report.pdf",
        local_path=None,
        file_sha256="hash-1",
        parsed=False,
        parse_status="pending",
        download_status="pending",
    )


def test_readiness_endpoint_has_no_side_effects(tmp_path, monkeypatch):
    from app.routers.company_v2_financial_fusion import get_company_v2_financial_fusion_readiness

    doc = _make_doc(tmp_path)
    db = _FakeDb(doc)

    monkeypatch.setattr("app.routers.company_v2_financial_fusion.report_pdf_download_service.download", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("download must not run")))
    monkeypatch.setattr("app.routers.company_v2_financial_fusion.report_text_extract_service.parse", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("parse must not run")))
    monkeypatch.setattr("app.routers.company_v2_financial_fusion.company_v2_report_rag_index_manager.enqueue_create_index", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("index must not run")))

    response = asyncio.run(get_company_v2_financial_fusion_readiness("CN", "601686", db))
    payload = json.loads(response.body)
    assert payload["status"] in {"pdf_not_downloaded", "parse_pending", "report_discovered"}
    assert payload["fusion_ready"] is False
