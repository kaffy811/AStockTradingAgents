from __future__ import annotations

from .phase6te3_helpers import descriptor, index_three_reports, sidecar


def test_three_reports_indexed_and_listed_independently(tmp_path):
    from app.services.company_v2_report_rag_index_manager import company_v2_report_rag_index_manager

    results = index_three_reports(tmp_path)
    rows = company_v2_report_rag_index_manager.list_indexes("601686")

    assert len(results) == 3
    assert all(result["status"] == "indexed" for result in results)
    assert {row["report_id"] for row in rows} == {1, 2, 3}
    assert all(row["active_index"] for row in rows)
    assert all(row["chunk_count"] > 0 for row in rows)


def test_duplicate_index_is_idempotent(tmp_path):
    from app.services.company_v2_report_rag_index_manager import company_v2_report_rag_index_manager
    from app.services.company_v2_report_rag_index_queue import company_v2_report_rag_index_queue
    from app.services.company_v2_report_rag_index_service import company_v2_report_rag_repository

    company_v2_report_rag_repository.clear()
    company_v2_report_rag_index_queue.clear()
    d = descriptor(1, 2024, "annual", "友发集团2024年年度报告")
    s = sidecar(tmp_path, 1, 2024, "annual")
    first = company_v2_report_rag_index_manager.create_index(d, s)
    second = company_v2_report_rag_index_manager.create_index(d, s)

    assert first["rag_document_id"] == second["rag_document_id"]
    assert second["index_generation"] == 1
    assert len(company_v2_report_rag_index_manager.get_index(1)["history"]) == 1


def test_mark_stale_and_get_index(tmp_path):
    from app.services.company_v2_report_rag_index_manager import company_v2_report_rag_index_manager

    index_three_reports(tmp_path)
    result = company_v2_report_rag_index_manager.mark_stale(1, "pdf_hash_changed")
    status = company_v2_report_rag_index_manager.get_index(1)

    assert result["status"] == "stale"
    assert status["status"] == "stale"
    assert status["stale_reason"] == "pdf_hash_changed"
