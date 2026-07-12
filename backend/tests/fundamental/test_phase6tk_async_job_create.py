from __future__ import annotations

import asyncio
import json

from .phase6tk_helpers import FakeBackgroundTasks, FakeDb, make_doc


def test_job_create_fast_response_and_background_task(tmp_path, monkeypatch):
    from app.routers.company_v2_financial_fusion import FinancialFusionJobRequest, create_company_v2_financial_fusion_job
    from app.services.company_v2_financial_fusion_job_service import company_v2_financial_fusion_job_service

    async def fake_create_job(**_kwargs):
        return {"ok": True, "job_id": "job-1", "status": "queued", "cache_hit": False, "poll_after_ms": 1000, "estimated_wait_seconds": 30}

    async def fake_run_job(_job_id):
        return None

    monkeypatch.setattr(company_v2_financial_fusion_job_service, "create_job", fake_create_job)
    monkeypatch.setattr(company_v2_financial_fusion_job_service, "run_job", fake_run_job)
    bg = FakeBackgroundTasks()
    response = asyncio.run(
        create_company_v2_financial_fusion_job(
            background_tasks=bg,
            body=FinancialFusionJobRequest(report_id=2, fields=["net_profit"], refresh=False),
            market="CN",
            symbol="600519",
            db=FakeDb(make_doc(tmp_path, symbol="600519", report_id=2)),
        )
    )
    body = json.loads(response.body)
    assert response.status_code == 202
    assert body["job_id"] == "job-1"
    assert body["status"] == "queued"
    assert body["poll_after_ms"] == 1000
    assert len(bg.tasks) == 1
