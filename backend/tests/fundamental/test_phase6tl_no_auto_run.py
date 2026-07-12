from __future__ import annotations

import asyncio

from app.services.company_v2_financial_fusion_job_service import company_v2_financial_fusion_job_service
from app.services.company_v2_financial_fusion_rollout_service import company_v2_financial_fusion_rollout_service

from .phase6tk_helpers import make_doc


class _Db:
    def __init__(self):
        self.executed = 0
        self.committed = 0

    async def execute(self, _stmt):
        self.executed += 1
        class _Result:
            def scalars(self):
                return self

            def first(self):
                return None
        return _Result()

    async def commit(self):
        self.committed += 1


def test_create_job_does_not_auto_run_before_background_dispatch(tmp_path, monkeypatch):
    doc = make_doc(tmp_path, symbol="000725", report_id=4)
    db = _Db()

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
            symbol="000725",
            report=doc,
            fields=["revenue"],
            refresh=False,
            requester_scope="manual",
        )
    )

    assert payload["status"] == "queued"
    assert db.executed == 1
    assert db.committed == 1
