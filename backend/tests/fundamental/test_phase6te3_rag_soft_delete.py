from __future__ import annotations

from .phase6te3_helpers import index_three_reports


def test_soft_delete_does_not_delete_pdf_or_sidecar(tmp_path):
    from app.services.company_v2_report_rag_index_manager import company_v2_report_rag_index_manager

    index_three_reports(tmp_path)
    result = company_v2_report_rag_index_manager.delete_index(1)
    status = company_v2_report_rag_index_manager.get_index(1)
    rows = company_v2_report_rag_index_manager.list_indexes("601686")

    assert result["status"] == "deleted"
    assert result["pdf_deleted"] is False
    assert result["sidecar_deleted"] is False
    assert status["deleted_at"]
    assert all(row["report_id"] != 1 for row in rows)


def test_deleted_index_is_not_queryable(tmp_path):
    from app.services.company_v2_report_rag_answer_service import company_v2_report_rag_answer_service
    from app.services.company_v2_report_rag_index_manager import company_v2_report_rag_index_manager

    index_three_reports(tmp_path)
    company_v2_report_rag_index_manager.delete_index(1)
    result = company_v2_report_rag_answer_service.answer(report_id=1, question="2024年营业收入是多少？", symbol="601686", report_year=2024)

    assert result["status"] == "insufficient_evidence"
    assert "REPORT_NOT_INDEXED" in result["warnings"]
