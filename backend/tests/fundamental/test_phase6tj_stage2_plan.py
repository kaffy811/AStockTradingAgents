from __future__ import annotations

import asyncio


class _FakeScalars:
    def __init__(self, docs):
        self._docs = docs

    def all(self):
        return list(self._docs)

    def first(self):
        return self._docs[0] if self._docs else None


class _FakeResult:
    def __init__(self, docs):
        self._docs = docs

    def scalars(self):
        return _FakeScalars(self._docs)


class _FakeDb:
    def __init__(self, docs):
        self.docs = list(docs)

    async def execute(self, _stmt):
        return _FakeResult(self.docs)


def test_stage2_plan_selects_latest_annual_and_step_state(tmp_path, monkeypatch):
    from app.models.report_document import ReportDocument
    from app.services.company_v2_financial_fusion_stage2_plan import company_v2_financial_fusion_stage2_plan_service
    from app.services.company_v2_financial_fusion_report_readiness import company_v2_financial_fusion_report_readiness_service
    from app.services.company_v2_report_rag_index_service import company_v2_report_rag_index_service

    docs = [
        ReportDocument(id=1, ts_code="600519.SH", report_type="annual", report_year=2023, title="2023 annual", pdf_url="https://static.cninfo.com.cn/1.pdf", local_path=str(tmp_path / "1.pdf"), download_status="downloaded", parse_status="parsed", parsed=True),
        ReportDocument(id=2, ts_code="600519.SH", report_type="annual", report_year=2024, title="2024 annual", pdf_url="https://static.cninfo.com.cn/2.pdf", local_path=str(tmp_path / "2.pdf"), download_status="downloaded", parse_status="parsed", parsed=True),
    ]
    (tmp_path / "2.pages.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(
        company_v2_report_rag_index_service,
        "status",
        lambda report_id: {"status": "indexed" if report_id == 2 else "pending"},
    )
    monkeypatch.setattr(
        company_v2_financial_fusion_report_readiness_service,
        "get_report_readiness",
        lambda market, symbol, report_id, db: asyncio.sleep(
            0,
            result={
                "ok": True,
                "report_view_ready": True,
                "pdf_url_ready": True,
                "source_url": "https://static.cninfo.com.cn/2.pdf",
                "url_whitelist_valid": True,
                "canonical_report": True,
                "qa_ready": report_id == 2,
                "fusion_ready": report_id == 2,
                "status": "ready" if report_id == 2 else "pdf_not_downloaded",
                "next_manual_action": "run_fusion" if report_id == 2 else "download_report",
                "next_manual_action_for_view": None,
                "next_manual_action_for_rag": "run_fusion" if report_id == 2 else "download_report",
                "next_manual_action_for_fusion": "run_fusion" if report_id == 2 else "download_report",
                "reason": None,
            },
        ),
    )

    payload = asyncio.run(company_v2_financial_fusion_stage2_plan_service.get_symbol_stage2_plan("CN", "600519", _FakeDb(docs)))
    assert payload["report_id"] == 2
    assert payload["current_status"] == "ready"
    assert payload["report_view_ready"] is True
    assert payload["steps"][0]["status"] == "ready"
    assert payload["steps"][-1]["status"] == "pending"


def test_stage2_plan_reports_not_discovered_when_empty():
    from app.services.company_v2_financial_fusion_stage2_plan import company_v2_financial_fusion_stage2_plan_service

    payload = asyncio.run(company_v2_financial_fusion_stage2_plan_service.get_symbol_stage2_plan("CN", "300750", _FakeDb([])))
    assert payload["current_status"] == "report_not_discovered"
    assert payload["next_manual_action"] == "discover_report"
