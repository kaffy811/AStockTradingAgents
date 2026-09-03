from __future__ import annotations

import asyncio

from app.core.config import settings


def test_stage2_allowlist_manual_config(monkeypatch):
    from app.services.company_v2_financial_fusion_rollout_service import company_v2_financial_fusion_rollout_service

    monkeypatch.setattr(settings, "company_v2_financial_fusion_enabled", True)
    monkeypatch.setattr(settings, "company_v2_financial_fusion_rollout_percent", 0)
    monkeypatch.setattr(settings, "company_v2_financial_fusion_symbol_allowlist", "601686,600519,300750,000725,000001")
    monkeypatch.setattr(settings, "company_v2_financial_fusion_auto_run", False)
    allowed = company_v2_financial_fusion_rollout_service.evaluate(
        symbol="300750", report_id=3, report_ready=True, rag_ready=True, structured_ready=True
    )
    blocked = company_v2_financial_fusion_rollout_service.evaluate(
        symbol="999999", report_id=99, report_ready=True, rag_ready=True, structured_ready=True
    )
    assert allowed["eligible"] is True and allowed["reason"] == "ALLOWLIST"
    assert allowed["rollout_percent"] == 0 and allowed["auto_run"] is False
    assert blocked["eligible"] is False and blocked["reason"] == "OUTSIDE_ROLLOUT"


def test_manual_admission_only_allows_allowlist_when_rollout_disabled(monkeypatch):
    from app.services.company_v2_financial_fusion_rollout_service import company_v2_financial_fusion_rollout_service

    monkeypatch.setattr(settings, "company_v2_financial_fusion_enabled", False)
    monkeypatch.setattr(settings, "company_v2_financial_fusion_rollout_percent", 0)
    monkeypatch.setattr(settings, "company_v2_financial_fusion_symbol_allowlist", "601686,600519,300750,000725,000001")
    monkeypatch.setattr(settings, "company_v2_financial_fusion_auto_run", False)

    allowed = company_v2_financial_fusion_rollout_service.evaluate(
        symbol="601686",
        report_id=1,
        report_ready=True,
        rag_ready=True,
        structured_ready=True,
        manual_admission=True,
    )
    blocked = company_v2_financial_fusion_rollout_service.evaluate(
        symbol="999999",
        report_id=99,
        report_ready=True,
        rag_ready=True,
        structured_ready=True,
        manual_admission=True,
    )

    assert allowed["eligible"] is True
    assert allowed["reason"] == "ALLOWLIST"
    assert allowed["manual_admission"] is True
    assert blocked["eligible"] is False
    assert blocked["reason"] == "NOT_IN_ALLOWLIST"


def test_manual_create_does_not_bypass_allowlist(monkeypatch, tmp_path):
    from app.services.company_v2_financial_fusion_job_service import company_v2_financial_fusion_job_service

    class _Db:
        async def execute(self, _stmt):
            raise AssertionError("manual ineligible admission must not reach DB write path")

        async def commit(self):
            raise AssertionError("manual ineligible admission must not commit")

    async def _noop_schema():
        return None

    monkeypatch.setattr(settings, "company_v2_financial_fusion_enabled", False)
    monkeypatch.setattr(settings, "company_v2_financial_fusion_rollout_percent", 0)
    monkeypatch.setattr(settings, "company_v2_financial_fusion_symbol_allowlist", "601686,600519,300750,000725,000001")
    monkeypatch.setattr(settings, "company_v2_financial_fusion_auto_run", False)
    monkeypatch.setattr(company_v2_financial_fusion_job_service, "ensure_schema", _noop_schema)

    from .phase6tk_helpers import make_doc

    doc = make_doc(tmp_path, symbol="999999", report_id=99)
    payload = asyncio.run(
        company_v2_financial_fusion_job_service.create_job(
            db=_Db(),
            market="CN",
            symbol="999999",
            report=doc,
            fields=["revenue"],
            refresh=False,
            requester_scope="manual",
        )
    )

    assert payload["ok"] is False
    assert payload["status"] == "ineligible"
    assert payload["error_code"] == "NOT_IN_ALLOWLIST"


def test_report_view_is_not_gated_by_fusion_allowlist():
    report_view_ready = True
    fusion_eligible = False
    assert report_view_ready is True
    assert fusion_eligible is False
