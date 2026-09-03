from __future__ import annotations

import json

import pytest


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


def _doc(tmp_path, *, symbol="601686", parsed=True):
    from app.models.report_document import ReportDocument

    pdf = tmp_path / "company_v2_report_1_hash.pdf"
    pdf.write_bytes(b"%PDF-1.4\n%%EOF")
    sidecar = pdf.with_suffix(".pages.json")
    sidecar.write_text(
        json.dumps(
            {
                "page_count": 1,
                "parse_status": "parsed",
                "warnings": [],
                "text_pages": [{
                    "page": 12,
                    "text": (
                        "第二节 财务指标\n单位：元\n营业收入 600 亿元\n归属于上市公司股东的净利润 5 亿元\n"
                        + "公司主营业务为焊接钢管研发、生产和销售，产品用于建筑、机械制造、能源等领域。\n" * 12
                    ),
                }],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return ReportDocument(
        id=1,
        ts_code=f"{symbol}.SH",
        report_type="annual",
        report_year=2024,
        disclosure_date="2025-04-25",
        pdf_url="https://static.cninfo.com.cn/finalpage/2025-04-25/1223277982.PDF",
        local_path=str(pdf),
        file_sha256="hash",
        parsed=parsed,
        parse_status="parsed" if parsed else "pending",
    )


@pytest.mark.asyncio
async def test_api_index_status_query_success(tmp_path):
    from app.routers.company_v2_report_rag import ReportRagQueryBody, _descriptor_from_doc, _find_sidecar, get_company_v2_report_rag_status, index_company_v2_report_rag, query_company_v2_report_rag
    from app.services.company_v2_report_rag_index_manager import company_v2_report_rag_index_manager
    from app.services.company_v2_report_rag_index_service import company_v2_report_rag_repository

    company_v2_report_rag_repository.clear()
    doc = _doc(tmp_path)
    db = _FakeDb(doc)

    index_response = await index_company_v2_report_rag("CN", "601686", 1, db)
    index_payload = json.loads(index_response.body)
    assert index_payload["status"] in {"queued", "running", "succeeded"}
    assert index_payload["job_id"]
    assert "local_path" not in json.dumps(index_payload, ensure_ascii=False)

    company_v2_report_rag_index_manager.create_index(_descriptor_from_doc(doc, "CN", "601686"), _find_sidecar(doc))

    status_response = await get_company_v2_report_rag_status("CN", "601686", 1, db)
    assert json.loads(status_response.body)["chunk_count"] >= 1

    query_response = await query_company_v2_report_rag(ReportRagQueryBody(question="营业收入是多少？"), "CN", "601686", 1, db)
    query_payload = json.loads(query_response.body)
    assert query_payload["status"] == "answered"
    assert query_payload["citations"]


@pytest.mark.asyncio
async def test_api_rejects_symbol_mismatch(tmp_path):
    from fastapi import HTTPException
    from app.routers.company_v2_report_rag import get_company_v2_report_rag_status

    with pytest.raises(HTTPException) as exc:
        await get_company_v2_report_rag_status("CN", "600519", 1, _FakeDb(_doc(tmp_path)))

    assert exc.value.status_code == 409
    assert exc.value.detail["error_code"] == "REPORT_SYMBOL_MISMATCH"


@pytest.mark.asyncio
async def test_api_precondition_pdf_not_parsed(tmp_path):
    from app.routers.company_v2_report_rag import index_company_v2_report_rag

    response = await index_company_v2_report_rag("CN", "601686", 1, _FakeDb(_doc(tmp_path, parsed=False)))
    payload = json.loads(response.body)

    assert response.status_code == 412
    assert payload["error_code"] == "PDF_NOT_PARSED"


@pytest.mark.asyncio
async def test_api_query_requires_existing_index(tmp_path):
    from app.routers.company_v2_report_rag import ReportRagQueryBody, query_company_v2_report_rag
    from app.services.company_v2_report_rag_index_service import company_v2_report_rag_repository

    company_v2_report_rag_repository.clear()
    response = await query_company_v2_report_rag(ReportRagQueryBody(question="营业收入是多少？", top_k=12), "CN", "601686", 1, _FakeDb(_doc(tmp_path)))
    payload = json.loads(response.body)

    assert response.status_code == 409
    assert payload["error_code"] == "REPORT_NOT_INDEXED"
