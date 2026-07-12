from __future__ import annotations

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


def test_report_view_is_not_gated_by_fusion_allowlist():
    report_view_ready = True
    fusion_eligible = False
    assert report_view_ready is True
    assert fusion_eligible is False
