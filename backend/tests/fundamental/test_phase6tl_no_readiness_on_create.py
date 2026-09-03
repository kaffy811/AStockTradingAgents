from __future__ import annotations

import asyncio

from app.routers.company_v2_financial_fusion import FinancialFusionJobRequest, create_company_v2_financial_fusion_job
from app.services.company_v2_financial_fusion_job_service import company_v2_financial_fusion_job_service

from .phase6tk_helpers import FakeBackgroundTasks, FakeDb, make_doc


def test_post_job_create_returns_queue_payload_without_readiness_hydration(tmp_path, monkeypatch):
    doc = make_doc(tmp_path, symbol="300750", report_id=3)

    async def fake_create_job(**_kwargs):
        return {"ok": True, "job_id": "job-1", "status": "queued", "cache_hit": False, "estimated_wait_seconds": 30, "poll_after_ms": 1000}

    monkeypatch.setattr(company_v2_financial_fusion_job_service, "create_job", fake_create_job)

    response = asyncio.run(
        create_company_v2_financial_fusion_job(
            background_tasks=FakeBackgroundTasks(),
            body=FinancialFusionJobRequest(report_id=3, fields=["revenue"], refresh=False),
            market="CN",
            symbol="300750",
            db=FakeDb(doc),
        )
    )

    assert response.status_code == 202
    payload = response.body.decode("utf-8")
    assert '"job_id":"job-1"' in payload
    assert '"status":"queued"' in payload
    assert '"poll_after_ms":1000' in payload
