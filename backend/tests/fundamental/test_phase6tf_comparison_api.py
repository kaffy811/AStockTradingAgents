from __future__ import annotations

import json

import pytest

from .phase6te3_helpers import index_three_reports


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
    def __init__(self, docs):
        self.docs = docs

    async def execute(self, stmt):
        params = stmt.compile().params
        report_id = params.get("id_1")
        return _FakeResult(self.docs.get(report_id))


def _doc(report_id: int, symbol: str = "601686", year: int = 2024, report_type: str = "annual"):
    from app.models.report_document import ReportDocument

    return ReportDocument(
        id=report_id,
        ts_code=f"{symbol}.SH",
        report_type=report_type,
        report_year=year,
        title=f"{year}{report_type}",
        disclosure_date="2025-04-25",
        pdf_url="https://static.cninfo.com.cn/finalpage/2025-04-25/1223277982.PDF",
        local_path=None,
        file_sha256=f"hash-{report_id}",
        parsed=True,
        parse_status="parsed",
    )


@pytest.mark.asyncio
async def test_comparison_api_rejects_unindexed_reports(tmp_path):
    from app.routers.company_v2_report_rag import ReportComparisonRequest, compare_company_v2_report_rag
    from app.services.company_v2_report_rag_index_service import company_v2_report_rag_repository

    index_three_reports(tmp_path)
    company_v2_report_rag_repository.clear()
    db = _FakeDb({
        1: _doc(1, year=2024, report_type="annual"),
        2: _doc(2, year=2024, report_type="q3"),
        3: _doc(3, year=2023, report_type="annual"),
    })

    response = await compare_company_v2_report_rag(
        body=ReportComparisonRequest(report_ids=[3, 1], question="比较 2023 和 2024 年营业收入变化", comparison_mode="generic_comparison", top_k_per_report=4, answer_style="concise"),
        market="CN",
        symbol="601686",
        db=db,
    )
    payload = json.loads(response.body)
    assert payload["error_code"] == "REPORT_NOT_INDEXED"


@pytest.mark.asyncio
async def test_comparison_api_enforces_selection_and_symbol(tmp_path):
    from app.routers.company_v2_report_rag import ReportComparisonRequest, compare_company_v2_report_rag

    index_three_reports(tmp_path)
    db = _FakeDb({
        1: _doc(1, year=2024, report_type="annual"),
        2: _doc(2, year=2024, report_type="q3"),
        3: _doc(3, year=2023, report_type="annual"),
    })

    response = await compare_company_v2_report_rag(
        body=ReportComparisonRequest(report_ids=[3, 1], question="比较 2023 和 2024 年营业收入变化", comparison_mode="generic_comparison", top_k_per_report=4, answer_style="concise"),
        market="CN",
        symbol="601686",
        db=db,
    )
    payload = json.loads(response.body)

    assert payload["status"] == "answered"
    assert payload["selected_report_ids"] == [3, 1]
    assert len(payload["citations"]) >= 2
    assert "local_path" not in json.dumps(payload, ensure_ascii=False)


@pytest.mark.asyncio
async def test_comparison_api_rejects_cross_symbol_and_duplicate_selection(tmp_path):
    from app.routers.company_v2_report_rag import ReportComparisonRequest, compare_company_v2_report_rag

    index_three_reports(tmp_path)
    db = _FakeDb({1: _doc(1), 2: _doc(2), 3: _doc(3)})

    duplicate = await compare_company_v2_report_rag(
        body=ReportComparisonRequest(report_ids=[1, 1], question="x", comparison_mode="generic_comparison", top_k_per_report=4, answer_style="concise"),
        market="CN",
        symbol="601686",
        db=db,
    )
    duplicate_payload = json.loads(duplicate.body)
    assert duplicate_payload["error_code"] == "DUPLICATE_REPORT_ID"

    cross_symbol_db = _FakeDb({1: _doc(1, symbol="600519"), 2: _doc(2), 3: _doc(3)})
    cross_symbol = await compare_company_v2_report_rag(
        body=ReportComparisonRequest(report_ids=[3, 1], question="x", comparison_mode="generic_comparison", top_k_per_report=4, answer_style="concise"),
        market="CN",
        symbol="601686",
        db=cross_symbol_db,
    )
    cross_symbol_payload = json.loads(cross_symbol.body)
    assert cross_symbol_payload["error_code"] == "REPORT_SYMBOL_MISMATCH"
