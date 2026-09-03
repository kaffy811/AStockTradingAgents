from __future__ import annotations

import asyncio

from app.services.company_v2_financial_fusion_job_service import company_v2_financial_fusion_job_service


class _JobRow:
    def __init__(self):
        self.job_id = "job-1"
        self.symbol = "600519"
        self.report_id = 2
        self.report_year = 2025
        self.requested_fields_json = '["revenue"]'
        self.requester_scope = "manual"
        self.created_at = None
        self.started_at = None
        self.completed_at = None
        self.status = "running"
        self.progress = 0.42
        self.current_stage = "cache_lookup"
        self.cache_hit = 0
        self.result_id = "result-1"
        self.error_code = None
        self.retryable = 1
        self.repository_backend = "database"
        self.extractor_version = "v1"
        self.active_generation = 1


class _StatusResult:
    def __init__(self, item):
        self._item = item

    def scalars(self):
        return self

    def first(self):
        return self._item


class _StatusDb:
    def __init__(self, item):
        self.item = item

    async def execute(self, _stmt):
        return _StatusResult(self.item)


def test_status_api_contract_does_not_hydrate_result_payload():
    payload = asyncio.run(
        company_v2_financial_fusion_job_service.get_job(
            db=_StatusDb(_JobRow()),
            job_id="job-1",
            symbol="600519",
            report_id=2,
        )
    )

    assert payload["job_id"] == "job-1"
    assert payload["status"] == "running"
    assert "result" not in payload
    assert payload["terminal"] is False
