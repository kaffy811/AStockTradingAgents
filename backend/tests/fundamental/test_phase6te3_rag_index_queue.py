from __future__ import annotations

import time

import pytest

from .phase6te3_helpers import descriptor, sidecar


@pytest.mark.asyncio
async def test_queue_rejects_duplicate_active_job(tmp_path):
    from app.services.company_v2_report_rag_index_manager import company_v2_report_rag_index_manager
    from app.services.company_v2_report_rag_index_queue import company_v2_report_rag_index_queue
    from app.services.company_v2_report_rag_index_service import company_v2_report_rag_repository

    company_v2_report_rag_repository.clear()
    company_v2_report_rag_index_queue.clear()
    d = descriptor(1, 2024, "annual", "友发集团2024年年度报告")
    s = sidecar(tmp_path, 1, 2024, "annual")
    first = company_v2_report_rag_index_queue.submit(
        report_id=1,
        operation="index",
        work=lambda: company_v2_report_rag_index_manager.create_index(d, s),
        run_background=False,
    )
    assert first["status"] == "succeeded"
    def slow_work():
        time.sleep(0.2)
        return {"ok": True}

    running = company_v2_report_rag_index_queue.submit(report_id=2, operation="index", work=slow_work, run_background=True)
    duplicate = company_v2_report_rag_index_queue.submit(report_id=2, operation="index", work=slow_work, run_background=True)

    assert running["job_id"] == duplicate["job_id"]
    assert duplicate["duplicate"] is True


def test_queue_progress_has_counts(tmp_path):
    from app.services.company_v2_report_rag_index_manager import company_v2_report_rag_index_manager
    from app.services.company_v2_report_rag_index_queue import company_v2_report_rag_index_queue

    company_v2_report_rag_index_queue.clear()
    d = descriptor(1, 2024, "annual", "友发集团2024年年度报告")
    s = sidecar(tmp_path, 1, 2024, "annual")
    job = company_v2_report_rag_index_queue.submit(
        report_id=1,
        operation="index",
        work=lambda: company_v2_report_rag_index_manager.create_index(d, s),
        run_background=False,
    )
    progress = company_v2_report_rag_index_manager.get_index_progress(1, job["job_id"])

    assert progress["status"] == "succeeded"
    assert progress["pages_processed"] > 0
    assert progress["chunks_created"] > 0
    assert progress["percent"] == 100
