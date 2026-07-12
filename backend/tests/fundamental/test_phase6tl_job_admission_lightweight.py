from __future__ import annotations

import asyncio

from app.services.company_v2_financial_fusion_job_service import company_v2_financial_fusion_job_service
from app.services.company_v2_financial_fusion_rollout_service import company_v2_financial_fusion_rollout_service
from app.services.company_v2_financial_evidence_fusion_service import company_v2_financial_evidence_fusion_service
from app.services.company_v2_report_rag_index_service import company_v2_report_rag_index_service

from .phase6tk_helpers import make_doc


class _AdmissionResult:
    def __init__(self, item):
        self._item = item

    def scalars(self):
        return self

    def first(self):
        return self._item


class _AdmissionDb:
    def __init__(self):
        self.added = []
        self.committed = False
        self.executed = 0

    async def execute(self, _stmt):
        self.executed += 1
        return _AdmissionResult(None)

    async def commit(self):
        self.committed = True


def test_job_admission_does_not_trigger_rag_or_structured_load(tmp_path, monkeypatch):
    doc = make_doc(tmp_path, symbol="600519", report_id=2)
    db = _AdmissionDb()
    calls = {"rollout": 0}

    def _fail_status(*_args, **_kwargs):
        raise AssertionError("RAG status lookup must not happen during admission")

    def _fail_load_structured(*_args, **_kwargs):
        raise AssertionError("Structured load must not happen during admission")

    def _evaluate(*args, **kwargs):
        calls["rollout"] += 1
        assert kwargs["report_ready"] is True
        assert kwargs["rag_ready"] is True
        assert kwargs["structured_ready"] is True
        return {
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
        }

    monkeypatch.setattr(company_v2_report_rag_index_service, "status", _fail_status)
    monkeypatch.setattr(company_v2_financial_evidence_fusion_service, "_load_structured", _fail_load_structured)
    monkeypatch.setattr(company_v2_financial_fusion_rollout_service, "evaluate", _evaluate)
    async def _noop_schema():
        return None

    monkeypatch.setattr(company_v2_financial_fusion_job_service, "ensure_schema", _noop_schema)

    payload = asyncio.run(
        company_v2_financial_fusion_job_service.create_job(
            db=db,
            market="CN",
            symbol="600519",
            report=doc,
            fields=["revenue", "net_profit"],
            refresh=False,
            requester_scope="manual",
        )
    )

    assert payload["ok"] is True
    assert payload["status"] == "queued"
    assert db.committed is True
    assert db.executed == 1
    assert calls["rollout"] == 1
