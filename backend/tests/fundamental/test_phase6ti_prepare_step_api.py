from __future__ import annotations

import asyncio
import json


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


def _make_doc(tmp_path):
    from app.models.report_document import ReportDocument

    pdf = tmp_path / "report.pdf"
    pdf.write_bytes(b"%PDF-1.4\n%%EOF")
    sidecar = pdf.with_suffix(".pages.json")
    sidecar.write_text(json.dumps({"page_count": 1, "parse_status": "parsed", "warnings": [], "text_pages": []}, ensure_ascii=False), encoding="utf-8")
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


def test_prepare_step_download_parse_and_index(tmp_path, monkeypatch):
    from app.routers.company_v2_financial_fusion import PrepareStepRequest, prepare_company_v2_financial_fusion_step

    doc = _make_doc(tmp_path)
    db = _FakeDb(doc)

    download_called = {"count": 0}
    parse_called = {"count": 0}
    enqueue_called = {"count": 0}

    async def fake_download(report_id, _db):
        download_called["count"] += 1
        return {"status": "downloaded", "report_id": report_id, "reason": "ok"}

    async def fake_parse(report_id, _db):
        parse_called["count"] += 1
        return {"status": "parsed", "report_id": report_id, "chars": 123, "reason": "ok"}

    def fake_enqueue(descriptor, sidecar_path):
        enqueue_called["count"] += 1
        assert descriptor.report_id == 1
        assert sidecar_path.exists()
        return {"job_id": "job-1", "status": "queued", "duplicate": False}

    monkeypatch.setattr("app.routers.company_v2_financial_fusion.report_pdf_download_service.download", fake_download)
    monkeypatch.setattr("app.routers.company_v2_financial_fusion.report_text_extract_service.parse", fake_parse)
    monkeypatch.setattr("app.routers.company_v2_financial_fusion.company_v2_report_rag_index_manager.enqueue_create_index", fake_enqueue)

    response = asyncio.run(
        prepare_company_v2_financial_fusion_step(
            body=PrepareStepRequest(step="download"),
            market="CN",
            symbol="601686",
            report_id=1,
            db=db,
        )
    )
    payload = json.loads(response.body)
    assert payload["ok"] is True
    assert download_called["count"] == 1

    doc.download_status = "downloaded"
    doc.local_path = str(tmp_path / "report.pdf")
    response = asyncio.run(
        prepare_company_v2_financial_fusion_step(
            body=PrepareStepRequest(step="parse"),
            market="CN",
            symbol="601686",
            report_id=1,
            db=db,
        )
    )
    payload = json.loads(response.body)
    assert payload["ok"] is True
    assert parse_called["count"] == 1

    doc.parsed = True
    doc.parse_status = "parsed"
    response = asyncio.run(
        prepare_company_v2_financial_fusion_step(
            body=PrepareStepRequest(step="index"),
            market="CN",
            symbol="601686",
            report_id=1,
            db=db,
        )
    )
    payload = json.loads(response.body)
    assert payload["ok"] is True
    assert payload["job_id"] == "job-1"
    assert enqueue_called["count"] == 1


def test_prepare_step_rejects_index_before_parse(tmp_path):
    from app.routers.company_v2_financial_fusion import PrepareStepRequest, prepare_company_v2_financial_fusion_step

    doc = _make_doc(tmp_path)
    doc.download_status = "downloaded"
    doc.local_path = str(tmp_path / "report.pdf")
    db = _FakeDb(doc)
    response = asyncio.run(
        prepare_company_v2_financial_fusion_step(
            body=PrepareStepRequest(step="index"),
            market="CN",
            symbol="601686",
            report_id=1,
            db=db,
        )
    )
    payload = json.loads(response.body)
    assert response.status_code == 412
    assert payload["error_code"] == "PDF_NOT_PARSED"
