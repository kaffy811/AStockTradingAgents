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


def _doc(tmp_path, report_id=1, symbol="601686", year=2024, report_type="annual"):
    from app.models.report_document import ReportDocument

    pdf = tmp_path / f"company_v2_report_{report_id}_hash.pdf"
    pdf.write_bytes(b"%PDF-1.4\n%%EOF")
    sidecar = pdf.with_suffix(".pages.json")
    sidecar.write_text(
        json.dumps(
            {
                "page_count": 1,
                "parse_status": "parsed",
                "warnings": [],
                "text_pages": [{"page": 6, "text": "第二节 主要会计数据\n单位：元\n营业收入 100 元\n" + "主要会计数据 " * 80}],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return ReportDocument(
        id=report_id,
        ts_code=f"{symbol}.SH",
        report_type=report_type,
        report_year=year,
        title=f"{year}{report_type}",
        disclosure_date="2025-04-25",
        pdf_url="https://static.cninfo.com.cn/finalpage/2025-04-25/1223277982.PDF",
        local_path=str(pdf),
        file_sha256=f"hash-{report_id}",
        parsed=True,
        parse_status="parsed",
    )


@pytest.mark.asyncio
async def test_index_api_returns_job_and_progress(tmp_path):
    from app.routers.company_v2_report_rag import get_company_v2_report_rag_job, index_company_v2_report_rag
    from app.services.company_v2_report_rag_index_queue import company_v2_report_rag_index_queue
    from app.services.company_v2_report_rag_index_service import company_v2_report_rag_repository

    company_v2_report_rag_repository.clear()
    company_v2_report_rag_index_queue.clear()
    db = _FakeDb(_doc(tmp_path))
    response = await index_company_v2_report_rag("CN", "601686", 1, db)
    payload = json.loads(response.body)
    progress = json.loads((await get_company_v2_report_rag_job("CN", "601686", 1, payload["job_id"], db)).body)

    assert payload["job_id"]
    assert payload["status"] in {"queued", "running", "succeeded"}
    assert progress["report_id"] == 1
    assert "local_path" not in json.dumps(payload, ensure_ascii=False)


@pytest.mark.asyncio
async def test_indexes_list_refresh_and_delete_api(tmp_path):
    from app.routers.company_v2_report_rag import (
        _descriptor_from_doc,
        _find_sidecar,
        delete_company_v2_report_rag_index,
        list_company_v2_report_rag_indexes,
        refresh_company_v2_report_rag,
    )
    from app.services.company_v2_report_rag_index_manager import company_v2_report_rag_index_manager
    from app.services.company_v2_report_rag_index_queue import company_v2_report_rag_index_queue
    from app.services.company_v2_report_rag_index_service import company_v2_report_rag_repository

    company_v2_report_rag_repository.clear()
    company_v2_report_rag_index_queue.clear()
    doc = _doc(tmp_path)
    db = _FakeDb(doc)
    company_v2_report_rag_index_manager.create_index(_descriptor_from_doc(doc, "CN", "601686"), _find_sidecar(doc))

    list_payload = json.loads((await list_company_v2_report_rag_indexes("CN", "601686")).body)
    refresh_payload = json.loads((await refresh_company_v2_report_rag("CN", "601686", 1, db)).body)
    delete_payload = json.loads((await delete_company_v2_report_rag_index("CN", "601686", 1, db)).body)

    assert list_payload["indexes"][0]["report_id"] == 1
    assert refresh_payload["job_id"]
    assert delete_payload["status"] == "deleted"
    assert delete_payload["pdf_deleted"] is False


@pytest.mark.asyncio
async def test_api_symbol_mismatch_rejected(tmp_path):
    from fastapi import HTTPException
    from app.routers.company_v2_report_rag import get_company_v2_report_rag_job

    with pytest.raises(HTTPException) as exc:
        await get_company_v2_report_rag_job("CN", "600519", 1, None, _FakeDb(_doc(tmp_path)))
    assert exc.value.status_code == 409
