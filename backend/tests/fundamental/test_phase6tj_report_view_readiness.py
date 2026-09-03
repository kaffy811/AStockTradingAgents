from __future__ import annotations

import asyncio


class _FakeScalars:
    def __init__(self, doc):
        self._doc = doc

    def first(self):
        return self._doc

    def all(self):
        return [self._doc] if self._doc else []


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


def _make_doc(tmp_path, *, pdf_url: str, source_url: str | None = None):
    from app.models.report_document import ReportDocument

    return ReportDocument(
        id=1,
        ts_code="600519.SH",
        report_type="annual",
        report_year=2024,
        title="2024 annual",
        pdf_url=pdf_url,
        source_url=source_url,
        local_path=None,
        download_status="pending",
        parse_status="pending",
        parsed=False,
    )


def test_report_view_ready_without_download(monkeypatch, tmp_path):
    from app.services.company_v2_financial_evidence_fusion_service import company_v2_financial_evidence_fusion_service
    from app.services.company_v2_financial_fusion_report_readiness import company_v2_financial_fusion_report_readiness_service
    from app.services.company_v2_report_rag_index_service import company_v2_report_rag_index_service

    doc = _make_doc(tmp_path, pdf_url="https://static.cninfo.com.cn/2024.pdf")
    monkeypatch.setattr(company_v2_report_rag_index_service, "status", lambda report_id: {"status": "pending"})
    monkeypatch.setattr(company_v2_financial_evidence_fusion_service, "_load_structured", lambda *args, **kwargs: {"source_mode": "unavailable"})

    payload = asyncio.run(company_v2_financial_fusion_report_readiness_service.get_report_readiness("CN", "600519", 1, _FakeDb(doc)))
    assert payload["report_view_ready"] is True
    assert payload["pdf_url_ready"] is True
    assert payload["rag_ready"] is False
    assert payload["fusion_ready"] is False
    assert payload["next_manual_action_for_view"] is None
    assert payload["next_manual_action_for_rag"] == "download_report"


def test_invalid_pdf_url_disables_view(monkeypatch, tmp_path):
    from app.services.company_v2_financial_evidence_fusion_service import company_v2_financial_evidence_fusion_service
    from app.services.company_v2_financial_fusion_report_readiness import company_v2_financial_fusion_report_readiness_service
    from app.services.company_v2_report_rag_index_service import company_v2_report_rag_index_service

    doc = _make_doc(tmp_path, pdf_url="javascript:alert(1)")
    monkeypatch.setattr(company_v2_report_rag_index_service, "status", lambda report_id: {"status": "pending"})
    monkeypatch.setattr(company_v2_financial_evidence_fusion_service, "_load_structured", lambda *args, **kwargs: {"source_mode": "unavailable"})

    payload = asyncio.run(company_v2_financial_fusion_report_readiness_service.get_report_readiness("CN", "600519", 1, _FakeDb(doc)))
    assert payload["report_view_ready"] is False
    assert payload["url_whitelist_valid"] is False
    assert payload["source_url"] == "javascript:alert(1)"


def test_prepare_status_api_does_not_expose_local_path(monkeypatch, tmp_path):
    from app.models.report_document import ReportDocument
    from app.services.company_v2_financial_fusion_stage2_plan import company_v2_financial_fusion_stage2_plan_service
    from app.services.company_v2_financial_fusion_report_readiness import company_v2_financial_fusion_report_readiness_service
    from app.services.company_v2_report_rag_index_manager import company_v2_report_rag_index_manager
    from app.services.company_v2_report_rag_index_service import company_v2_report_rag_index_service

    doc = ReportDocument(
        id=1,
        ts_code="600519.SH",
        report_type="annual",
        report_year=2024,
        title="2024 annual",
        pdf_url="https://static.cninfo.com.cn/2024.pdf",
        local_path=str(tmp_path / "report.pdf"),
        download_status="pending",
        parse_status="pending",
        parsed=False,
    )
    monkeypatch.setattr(company_v2_financial_fusion_report_readiness_service, "get_report_readiness", lambda market, symbol, report_id, db: asyncio.sleep(0, result={
        "ok": True,
        "report_view_ready": True,
        "pdf_url_ready": True,
        "source_url": "https://static.cninfo.com.cn/2024.pdf",
        "url_whitelist_valid": True,
        "canonical_report": True,
        "qa_ready": False,
        "fusion_ready": False,
        "status": "pdf_not_downloaded",
        "next_manual_action": "download_report",
        "next_manual_action_for_view": None,
        "next_manual_action_for_rag": "download_report",
        "next_manual_action_for_fusion": "download_report",
        "reason": None,
    }))
    monkeypatch.setattr(company_v2_report_rag_index_service, "status", lambda report_id: {"status": "pending", "last_error": None})
    monkeypatch.setattr(company_v2_report_rag_index_manager, "get_index_progress", lambda report_id: {"status": "idle", "report_id": report_id})

    payload = asyncio.run(company_v2_financial_fusion_stage2_plan_service.get_report_prepare_status("CN", "600519", 1, _FakeDb(doc)))
    assert payload["report_view_ready"] is True
    assert "local_path" not in payload
    assert "sidecar_path" not in payload
