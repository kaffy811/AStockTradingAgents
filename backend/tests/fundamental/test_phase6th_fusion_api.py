from __future__ import annotations

import asyncio
import json

from app.core.config import settings


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


def _doc(tmp_path):
    from app.models.report_document import ReportDocument

    pdf = tmp_path / "company_v2_report_1_hash.pdf"
    pdf.write_bytes(b"%PDF-1.4\n%%EOF")
    sidecar = pdf.with_suffix(".pages.json")
    sidecar.write_text(
        json.dumps(
            {
                "page_count": 265,
                "parse_status": "parsed",
                "warnings": [],
                "text_pages": [
                    {"page": 6, "text": "主要会计数据 营业收入 54,822,111,649.52 归属于上市公司股东的净利润 424,777,342.95"},
                    {"page": 54, "text": "截至 2024 年 12 月 12 日，公司总股本1,432,296,037股"},
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return ReportDocument(
        id=1,
        ts_code="601686.SH",
        report_type="annual",
        report_year=2024,
        title="2024 annual",
        disclosure_date="2025-04-25",
        pdf_url="https://static.cninfo.com.cn/finalpage/2025-04-25/1223277982.PDF",
        local_path=str(pdf),
        file_sha256="hash-1",
        parsed=True,
        parse_status="parsed",
    )


def test_financial_fusion_eligibility_and_health_endpoints(tmp_path, monkeypatch):
    from app.routers.company_v2_report_rag import (
        get_company_v2_financial_fusion_eligibility,
        get_company_v2_financial_fusion_health,
    )
    from app.services.company_v2_report_rag_index_service import company_v2_report_rag_repository as rag_repo

    monkeypatch.setattr(settings, "company_v2_financial_fusion_enabled", True)
    monkeypatch.setattr(settings, "company_v2_financial_fusion_symbol_allowlist", "601686")
    rag_repo.clear()
    response = json.loads((asyncio.run(get_company_v2_financial_fusion_eligibility("CN", "601686", 1, _FakeDb(_doc(tmp_path))))).body)
    health = json.loads((asyncio.run(get_company_v2_financial_fusion_health("CN", "601686", 1, _FakeDb(_doc(tmp_path))))).body)
    assert response["ok"] is True
    assert response["eligible"] in {True, False}
    assert health["ok"] is True
    assert "status" in health


def test_financial_fusion_run_rejects_when_disabled(tmp_path, monkeypatch):
    from app.routers.company_v2_report_rag import FinancialFusionRunRequest, run_company_v2_financial_fusion

    monkeypatch.setattr(settings, "company_v2_financial_fusion_enabled", False)
    response = asyncio.run(
        run_company_v2_financial_fusion(
            body=FinancialFusionRunRequest(fields=["net_profit"]),
            market="CN",
            symbol="601686",
            report_id=1,
            x_idempotency_key="abc",
            db=_FakeDb(_doc(tmp_path)),
        )
    )
    payload = json.loads(response.body)
    assert payload["status"] == "ineligible"
    assert payload["reason"] == "DISABLED"
