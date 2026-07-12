from __future__ import annotations

import asyncio
from datetime import datetime
from types import SimpleNamespace

from app.services.company_v2_financial_fusion_job_service import company_v2_financial_fusion_job_service
from app.services.company_v2_financial_fusion_rollout_service import company_v2_financial_fusion_rollout_service

from .phase6tk_helpers import make_doc


class _Result:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value

    def first(self):
        return self._value


class _DedupDb:
    def __init__(self, existing_row):
        self._responses = [None, existing_row]
        self.execute_count = 0
        self.commit_count = 0
        self.refresh_count = 0
        self.bind = SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))

    async def execute(self, _stmt):
        self.execute_count += 1
        return _Result(self._responses[self.execute_count - 1])

    async def commit(self):
        self.commit_count += 1

    async def refresh(self, _row):
        self.refresh_count += 1


def test_duplicate_create_returns_existing_job_without_reinsert(tmp_path, monkeypatch):
    doc = make_doc(tmp_path, symbol="300750", report_id=4)
    existing = SimpleNamespace(
        job_id="existing-job",
        symbol="300750",
        report_id=4,
        report_year=2025,
        requested_fields_json='["revenue"]',
        requester_scope="manual",
        created_at=datetime(2026, 7, 12, 12, 0, 0),
        started_at=None,
        completed_at=None,
        status="queued",
        progress=0.0,
        current_stage="queued",
        cache_hit=0,
        result_id=None,
        error_code=None,
        retryable=0,
        repository_backend="database",
        extractor_version="v1",
        active_generation=None,
    )
    db = _DedupDb(existing)

    async def _noop_schema():
        return None

    monkeypatch.setattr(company_v2_financial_fusion_job_service, "ensure_schema", _noop_schema)
    monkeypatch.setattr(
        company_v2_financial_fusion_rollout_service,
        "evaluate",
        lambda **kwargs: {
            "enabled": True,
            "eligible": True,
            "reason": "ALLOWLIST",
            "rollout_bucket": 1,
            "rollout_percent": 0,
            "auto_run": False,
            "report_ready": True,
            "rag_ready": True,
            "structured_ready": True,
            "supported_fields": kwargs["supported_fields"],
            "cached": False,
            "last_run_at": None,
            "force_enabled": kwargs["force_enabled"],
        },
    )

    payload = asyncio.run(
        company_v2_financial_fusion_job_service.create_job(
            db=db,
            market="CN",
            symbol="300750",
            report=doc,
            fields=["revenue"],
            refresh=False,
            requester_scope="manual",
        )
    )

    assert payload["ok"] is True
    assert payload["duplicate"] is True
    assert payload["job_id"] == "existing-job"
    assert db.execute_count == 2
    assert db.commit_count == 1
    assert db.refresh_count == 0
