from __future__ import annotations

import asyncio
from types import SimpleNamespace

from app.services.company_v2_financial_fusion_job_service import company_v2_financial_fusion_job_service
from app.services.company_v2_financial_fusion_rollout_service import company_v2_financial_fusion_rollout_service

from .phase6tk_helpers import make_doc


class _QueryResult:
    def __init__(self, item=None):
        self._item = item

    def scalars(self):
        return self

    def first(self):
        return self._item

    def scalar_one_or_none(self):
        return self._item


class _QueryDb:
    def __init__(self):
        self.execute_count = 0
        self.commit_count = 0
        self.refresh_count = 0
        self.bind = SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))

    async def execute(self, _stmt):
        self.execute_count += 1
        return _QueryResult("job-1")

    async def commit(self):
        self.commit_count += 1

    async def refresh(self, _row):
        self.refresh_count += 1


def test_job_create_only_runs_the_duplicate_check_query(tmp_path, monkeypatch):
    doc = make_doc(tmp_path, symbol="000001", report_id=5)
    db = _QueryDb()

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
            symbol="000001",
            report=doc,
            fields=["revenue"],
            refresh=False,
            requester_scope="manual",
        )
    )

    assert payload["ok"] is True
    assert db.execute_count == 1
    assert db.commit_count == 1
    assert db.refresh_count == 0
