from __future__ import annotations

import asyncio

from app.models.report_document import ReportDocument
from app.services.company_v2_financial_evidence_fusion_service import company_v2_financial_evidence_fusion_service
from app.services.company_v2_financial_fusion_report_readiness import company_v2_financial_fusion_report_readiness_service
from app.services.company_v2_report_rag_index_service import company_v2_report_rag_index_service


class _ReadinessScalars:
    def __init__(self, items):
        self._items = items

    def first(self):
        return self._items[0] if self._items else None

    def all(self):
        return self._items


class _ReadinessResult:
    def __init__(self, items):
        self._items = items

    def scalars(self):
        return _ReadinessScalars(self._items)


class _ReadinessDb:
    def __init__(self, items):
        self.items = items

    async def execute(self, _stmt):
        return _ReadinessResult(self.items)


def test_601686_readiness_uses_normalized_symbol_and_report_id(tmp_path, monkeypatch):
    pdf = tmp_path / "report.pdf"
    pdf.write_bytes(b"%PDF-1.4\n%%EOF")
    pdf.with_suffix(".pages.json").write_text('{"page_count":1}', encoding="utf-8")
    doc = ReportDocument(
        id=1,
        ts_code="601686.SH",
        report_type="annual",
        report_year=2024,
        title="友发集团：2024年年度报告",
        disclosure_date="2025-04-24",
        pdf_url="https://static.cninfo.com.cn/finalpage/2025-04-25/1223277982.PDF",
        local_path=str(pdf),
        file_sha256="sha-test",
        parsed=True,
        parse_status="parsed",
        download_status="downloaded",
    )

    monkeypatch.setattr(
        company_v2_report_rag_index_service,
        "status",
        lambda _report_id: {
            "repository_backend": "database",
            "persistent": True,
            "status": "indexed",
            "chunk_count": 296,
            "embedding_version": "company-v2-hash-keyword-v1",
            "index_generation": 1,
        },
    )
    monkeypatch.setattr(
        company_v2_financial_evidence_fusion_service,
        "_load_structured",
        lambda *_args, **_kwargs: {"source_mode": "artifact_seed", "fields": {"revenue": {"value": 1}}},
    )

    payload = asyncio.run(
        company_v2_financial_fusion_report_readiness_service.get_report_readiness(
            "CN",
            "601686",
            1,
            _ReadinessDb([doc]),
        )
    )
    symbol_payload = asyncio.run(
        company_v2_financial_fusion_report_readiness_service.get_symbol_readiness(
            "CN",
            "601686",
            _ReadinessDb([doc]),
        )
    )

    assert payload["ok"] is True
    assert payload["report_id"] == 1
    assert payload["rag_index_status"] == "indexed"
    assert payload["fusion_ready"] is True
    assert payload["canonical_report"] is True
    assert symbol_payload["latest_report_id"] == 1
    assert symbol_payload["status"] == "ready"
