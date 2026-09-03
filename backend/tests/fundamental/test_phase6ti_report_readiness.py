from __future__ import annotations

import json


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


def _make_doc(tmp_path, report_id: int, year: int, *, downloaded: bool, parsed: bool):
    from app.models.report_document import ReportDocument

    pdf = tmp_path / f"report_{report_id}.pdf"
    if downloaded:
        pdf.write_bytes(b"%PDF-1.4\n%%EOF")
    sidecar = pdf.with_suffix(".pages.json")
    if parsed:
        sidecar.write_text(
            json.dumps({"page_count": 2, "parse_status": "parsed", "warnings": [], "text_pages": [{"page": 1, "text": "收入"}]}, ensure_ascii=False),
            encoding="utf-8",
        )
    return ReportDocument(
        id=report_id,
        ts_code="601686.SH",
        report_type="annual",
        report_year=year,
        title=f"{year} annual",
        disclosure_date=f"{year + 1}-04-01",
        pdf_url=f"https://static.cninfo.com.cn/{report_id}.pdf",
        local_path=str(pdf) if downloaded else None,
        file_sha256=f"hash-{report_id}",
        parsed=parsed,
        parse_status="parsed" if parsed else ("pending" if downloaded else "pending"),
        download_status="downloaded" if downloaded else "pending",
    )


def test_symbol_readiness_reports_detail_and_manual_action(tmp_path, monkeypatch):
    from app.services.company_v2_financial_evidence_fusion_service import company_v2_financial_evidence_fusion_service
    from app.services.company_v2_financial_fusion_report_readiness import company_v2_financial_fusion_report_readiness_service
    from app.services.company_v2_report_rag_index_service import company_v2_report_rag_index_service

    ready_doc = _make_doc(tmp_path, 1, 2024, downloaded=True, parsed=True)
    not_ready_doc = _make_doc(tmp_path, 2, 2023, downloaded=False, parsed=False)

    monkeypatch.setattr(company_v2_report_rag_index_service, "status", lambda report_id: {"status": "indexed" if report_id == 1 else "pending"})
    monkeypatch.setattr(
        company_v2_financial_evidence_fusion_service,
        "_load_structured",
        lambda symbol, report_id, report_year, report_type: {"source_mode": "artifact_seed"} if report_id == 1 else {"source_mode": "unavailable"},
    )

    payload = __import__("asyncio").run(
        company_v2_financial_fusion_report_readiness_service.get_symbol_readiness("CN", "601686", _FakeDb([ready_doc, not_ready_doc]))
    )

    assert payload["status"] == "ready"
    assert payload["latest_annual_report_year"] == 2024
    assert payload["report_view_ready"] is True
    assert payload["source_url"] == ready_doc.pdf_url
    assert payload["fusion_ready"] is True
    assert any(item["status"] == "pdf_not_downloaded" for item in payload["reports"])
    assert payload["next_manual_action"] == "run_fusion"


def test_report_readiness_rejects_symbol_mismatch(tmp_path):
    from app.services.company_v2_financial_fusion_report_readiness import company_v2_financial_fusion_report_readiness_service

    doc = _make_doc(tmp_path, 1, 2024, downloaded=True, parsed=True)
    payload = __import__("asyncio").run(
        company_v2_financial_fusion_report_readiness_service.get_report_readiness("CN", "000001", 1, _FakeDb([doc]))
    )

    assert payload["ok"] is False
    assert payload["error_code"] == "REPORT_SYMBOL_MISMATCH"
