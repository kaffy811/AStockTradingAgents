from __future__ import annotations

from .phase6te3_helpers import descriptor, index_three_reports, sidecar


def test_refresh_success_switches_active_and_supersedes_old(tmp_path):
    from app.services.company_v2_report_rag_index_manager import company_v2_report_rag_index_manager

    index_three_reports(tmp_path)
    before = company_v2_report_rag_index_manager.get_index(1)
    refreshed = company_v2_report_rag_index_manager.refresh_index(
        descriptor(1, 2024, "annual", "友发集团2024年年度报告"),
        sidecar(tmp_path, 1, 2024, "annual"),
    )
    after = company_v2_report_rag_index_manager.get_index(1)

    assert refreshed["status"] == "indexed"
    assert refreshed["rag_document_id"] != before["history"][0]["rag_document_id"]
    assert refreshed["supersedes_rag_document_id"] == before["history"][0]["rag_document_id"]
    assert after["index_generation"] == 2
    assert after["history"][0]["active_index"] is True


def test_refresh_failure_preserves_old_active_index(tmp_path):
    from app.services.company_v2_report_rag_index_manager import company_v2_report_rag_index_manager

    index_three_reports(tmp_path)
    before = company_v2_report_rag_index_manager.get_index(1)
    failed = company_v2_report_rag_index_manager.refresh_index(
        descriptor(1, 2024, "annual", "友发集团2024年年度报告"),
        tmp_path / "missing.pages.json",
    )
    after = company_v2_report_rag_index_manager.get_index(1)

    assert failed["ok"] is False
    assert failed["active_index_preserved"] is True
    assert after["history"][0]["rag_document_id"] == before["history"][0]["rag_document_id"]
    assert after["status"] == "indexed"


def test_embedding_version_change_can_rebuild_active_index(tmp_path):
    from app.services.company_v2_report_embedding_service import company_v2_report_embedding_service
    from app.services.company_v2_report_rag_index_manager import company_v2_report_rag_index_manager

    index_three_reports(tmp_path)
    original = company_v2_report_embedding_service.embedding_version
    try:
        company_v2_report_embedding_service.embedding_version = "company-v2-hash-keyword-v2"
        stale = company_v2_report_rag_index_manager.mark_stale(1, "embedding_version_changed")
        refreshed = company_v2_report_rag_index_manager.rebuild_stale_index(
            descriptor(1, 2024, "annual", "友发集团2024年年度报告"),
            sidecar(tmp_path, 1, 2024, "annual"),
        )
    finally:
        company_v2_report_embedding_service.embedding_version = original

    assert stale["status"] == "stale"
    assert refreshed["embedding_version"] == "company-v2-hash-keyword-v2"
    assert refreshed["index_generation"] == 2
