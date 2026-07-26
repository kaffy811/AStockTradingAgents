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


def test_prepare_status_endpoint_returns_job_and_next_action(monkeypatch, tmp_path):
    from app.models.report_document import ReportDocument
    from app.routers.company_v2_financial_fusion import get_company_v2_financial_fusion_prepare_status
    from app.services.company_v2_financial_fusion_stage2_plan import company_v2_financial_fusion_stage2_plan_service
    from app.services.company_v2_report_rag_index_manager import company_v2_report_rag_index_manager
    from app.services.company_v2_report_rag_index_service import company_v2_report_rag_index_service

    pdf = tmp_path / "report.pdf"
    pdf.write_bytes(b"%PDF-1.4\n%%EOF")
    pdf.with_suffix(".pages.json").write_text(json.dumps({"page_count": 1, "parse_status": "parsed", "warnings": [], "text_pages": []}), encoding="utf-8")
    doc = ReportDocument(
        id=9,
        ts_code="600519.SH",
        report_type="annual",
        report_year=2024,
        title="2024 annual",
        pdf_url="https://static.cninfo.com.cn/9.pdf",
        local_path=str(pdf),
        download_status="downloaded",
        parse_status="parsed",
        parsed=True,
        file_sha256="sha",
    )
    monkeypatch.setattr(company_v2_report_rag_index_service, "status", lambda report_id: {"status": "indexed", "last_error": None})
    monkeypatch.setattr(company_v2_report_rag_index_manager, "get_index_progress", lambda report_id: {"status": "running", "report_id": report_id, "percent": 40})
    monkeypatch.setattr(
        company_v2_financial_fusion_stage2_plan_service,
        "get_report_prepare_status",
        lambda market, symbol, report_id, db: asyncio.sleep(0, result={
            "ok": True,
            "market": market,
            "symbol": symbol,
            "report_id": report_id,
            "report_year": 2024,
            "report_type": "annual",
            "title": "2024 annual",
            "discovery_status": "report_discovered",
            "download_status": "downloaded",
            "parse_status": "parsed",
            "index_status": "indexed",
            "fusion_readiness": "ready",
            "current_job": {"status": "running", "report_id": report_id, "percent": 40},
            "last_error": None,
            "next_manual_action": "run_fusion",
            "steps": [],
            "readiness": {"status": "ready", "fusion_ready": True},
        }),
    )

    payload = asyncio.run(get_company_v2_financial_fusion_prepare_status("CN", "600519", 9, _FakeDb(doc)))
    body = json.loads(payload.body)
    assert body["ok"] is True
    assert body["current_job"]["status"] == "running"
    assert body["next_manual_action"] == "run_fusion"
    assert "local_path" not in body
