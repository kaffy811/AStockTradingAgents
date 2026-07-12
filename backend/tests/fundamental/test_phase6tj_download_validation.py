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


def test_download_step_does_not_expose_local_path(tmp_path, monkeypatch):
    from app.models.report_document import ReportDocument
    import app.routers.company_v2_financial_fusion as router

    pdf = tmp_path / "report.pdf"
    doc = ReportDocument(
        id=1,
        ts_code="600519.SH",
        report_type="annual",
        report_year=2024,
        title="2024 annual",
        pdf_url="https://static.cninfo.com.cn/report.pdf",
        local_path=str(pdf),
        download_status="pending",
        parse_status="pending",
        parsed=False,
    )

    monkeypatch.setattr(
        router.report_pdf_download_service,
        "download",
        lambda report_id, db: asyncio.sleep(0, result={"status": "downloaded", "report_id": report_id, "reason": "ok", "local_path": str(pdf), "file_size": 3, "sha256": "abc"}),
    )

    payload = asyncio.run(
        router.prepare_company_v2_financial_fusion_step(
            body=router.PrepareStepRequest(step="download"),
            market="CN",
            symbol="600519",
            report_id=1,
            db=_FakeDb(doc),
        )
    )
    body = json.loads(payload.body)
    assert body["ok"] is True
    assert body["status"] == "downloaded"
    assert "local_path" not in body
