from __future__ import annotations

import asyncio
from datetime import datetime


class _Scalars:
    def __init__(self, row):
        self.row = row

    def first(self):
        return self.row


class _Result:
    def __init__(self, row):
        self.row = row

    def scalars(self):
        return _Scalars(self.row)


class _Db:
    def __init__(self, row):
        self.row = row

    async def execute(self, _stmt):
        return _Result(self.row)

    async def commit(self):
        return None

    async def refresh(self, _row):
        return None


def test_cancel_queued_job_marks_terminal():
    from app.models.company_v2_financial_fusion_job import CompanyV2FinancialFusionJob
    from app.services.company_v2_financial_fusion_job_service import company_v2_financial_fusion_job_service

    row = CompanyV2FinancialFusionJob(
        job_id="job-cancel",
        market="CN",
        symbol="600519",
        report_id=2,
        requested_fields_json="[]",
        request_fingerprint="fp",
        status="queued",
        progress=0.0,
        current_stage="queued",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    payload = asyncio.run(company_v2_financial_fusion_job_service.cancel_job(db=_Db(row), job_id="job-cancel", symbol="600519"))
    assert payload["status"] == "cancelled"
    assert payload["terminal"] is True
