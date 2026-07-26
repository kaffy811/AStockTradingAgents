from __future__ import annotations

import json

import pytest

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
                    {"page": 6, "text": "主要会计数据 营业收入 54,822,111,649.52 归属于上市公司股东的净利润 424,777,342.95 基本每股收益（元／股） 0.30 加权平均净资产收益率（%） 6.54 归属于上市公司股东的净资产 6,760,918,501.91"},
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


@pytest.mark.asyncio
async def test_fusion_api_runs_and_returns_statuses(tmp_path, monkeypatch):
    from app.routers.company_v2_report_rag import FinancialFusionRunRequest, get_company_v2_financial_fusion, run_company_v2_financial_fusion
    from app.services.company_v2_report_rag_index_service import company_v2_report_rag_index_service

    monkeypatch.setattr(settings, "company_v2_financial_fusion_enabled", True)
    monkeypatch.setattr(settings, "company_v2_financial_fusion_symbol_allowlist", "601686")
    monkeypatch.setattr(company_v2_report_rag_index_service, "status", lambda report_id: {"status": "indexed", "embedding_version": "v1"})

    response = await run_company_v2_financial_fusion(
        body=FinancialFusionRunRequest(fields=[
            "revenue",
            "net_profit",
            "net_profit_parent",
            "operating_cashflow",
            "total_assets",
            "equity_parent",
            "eps_basic",
            "roe_weighted",
            "total_share",
            "float_share",
        ], refresh=True),
        market="CN",
        symbol="601686",
        report_id=1,
        x_idempotency_key="test-idempotency-key",
        db=_FakeDb(_doc(tmp_path)),
    )
    payload = json.loads(response.body)
    assert payload["ok"] is True
    assert payload["summary"]["fields_total"] == 10
    assert "local_path" not in json.dumps(payload, ensure_ascii=False)

    get_payload = json.loads((await get_company_v2_financial_fusion("CN", "601686", 1, _FakeDb(_doc(tmp_path)))).body)
    assert get_payload["ok"] is True
    assert get_payload["report_id"] == 1


@pytest.mark.asyncio
async def test_fusion_api_requires_parsed_report(tmp_path, monkeypatch):
    from app.routers.company_v2_report_rag import FinancialFusionRunRequest, run_company_v2_financial_fusion

    monkeypatch.setattr(settings, "company_v2_financial_fusion_enabled", False)
    doc = _doc(tmp_path)
    doc.parsed = False
    doc.parse_status = "failed"
    response = await run_company_v2_financial_fusion(
        body=FinancialFusionRunRequest(fields=["revenue"]),
        market="CN",
        symbol="601686",
        report_id=1,
        db=_FakeDb(doc),
    )
    payload = json.loads(response.body)
    assert payload["error_code"] == "PDF_NOT_PARSED"
