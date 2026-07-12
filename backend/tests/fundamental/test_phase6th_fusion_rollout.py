from __future__ import annotations

from app.core.config import settings


def test_rollout_disabled_by_default(monkeypatch):
    from app.services.company_v2_financial_fusion_rollout_service import company_v2_financial_fusion_rollout_service

    monkeypatch.setattr(settings, "company_v2_financial_fusion_enabled", False)
    payload = company_v2_financial_fusion_rollout_service.evaluate(
        symbol="601686",
        report_id=1,
        report_ready=True,
        rag_ready=True,
        structured_ready=True,
        supported_fields=["revenue"],
    )
    assert payload["enabled"] is False
    assert payload["eligible"] is False
    assert payload["reason"] == "DISABLED"


def test_force_enabled_allows_manual_audit_without_auto_rollout(monkeypatch):
    from app.services.company_v2_financial_fusion_rollout_service import company_v2_financial_fusion_rollout_service

    monkeypatch.setattr(settings, "company_v2_financial_fusion_enabled", False)
    monkeypatch.setattr(settings, "company_v2_financial_fusion_rollout_percent", 0)
    monkeypatch.setattr(settings, "company_v2_financial_fusion_auto_run", False)
    payload = company_v2_financial_fusion_rollout_service.evaluate(
        symbol="300750",
        report_id=3,
        report_ready=True,
        rag_ready=True,
        structured_ready=True,
        supported_fields=["net_profit"],
        force_enabled=True,
    )
    assert payload["eligible"] is True
    assert payload["reason"] == "FORCE_ENABLED"
    assert payload["rollout_percent"] == 0
    assert payload["auto_run"] is False
    assert payload["force_enabled"] is True


def test_rollout_allowlist_and_bucket_are_stable(monkeypatch):
    from app.services.company_v2_financial_fusion_rollout_service import company_v2_financial_fusion_rollout_service

    monkeypatch.setattr(settings, "company_v2_financial_fusion_enabled", True)
    monkeypatch.setattr(settings, "company_v2_financial_fusion_symbol_allowlist", "601686,600519")
    monkeypatch.setattr(settings, "company_v2_financial_fusion_rollout_percent", 0)
    a = company_v2_financial_fusion_rollout_service.evaluate(symbol="601686", report_id=1, report_ready=True, rag_ready=True, structured_ready=True)
    b = company_v2_financial_fusion_rollout_service.evaluate(symbol="601686", report_id=1, report_ready=True, rag_ready=True, structured_ready=True)
    c = company_v2_financial_fusion_rollout_service.evaluate(symbol="300750", report_id=1, report_ready=True, rag_ready=True, structured_ready=True)
    assert a["eligible"] is True and a["reason"] == "ALLOWLIST"
    assert a["rollout_bucket"] == b["rollout_bucket"]
    assert c["eligible"] is False and c["reason"] == "OUTSIDE_ROLLOUT"


def test_rollout_reasons_cover_unready_states(monkeypatch):
    from app.services.company_v2_financial_fusion_rollout_service import company_v2_financial_fusion_rollout_service

    monkeypatch.setattr(settings, "company_v2_financial_fusion_enabled", True)
    assert company_v2_financial_fusion_rollout_service.evaluate(symbol="601686", report_id=1, report_ready=False, rag_ready=True, structured_ready=True)["reason"] == "REPORT_NOT_READY"
    assert company_v2_financial_fusion_rollout_service.evaluate(symbol="601686", report_id=1, report_ready=True, rag_ready=False, structured_ready=True)["reason"] == "RAG_NOT_INDEXED"
    assert company_v2_financial_fusion_rollout_service.evaluate(symbol="601686", report_id=1, report_ready=True, rag_ready=True, structured_ready=False)["reason"] == "STRUCTURED_DATA_UNAVAILABLE"
