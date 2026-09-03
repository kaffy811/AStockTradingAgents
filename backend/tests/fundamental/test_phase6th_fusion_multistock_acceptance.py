from __future__ import annotations

def test_rollout_audit_handles_multiple_symbols(monkeypatch):
    from app.services.company_v2_financial_fusion_rollout_service import company_v2_financial_fusion_rollout_service

    monkeypatch.setattr("app.core.config.settings.company_v2_financial_fusion_enabled", True)
    monkeypatch.setattr("app.core.config.settings.company_v2_financial_fusion_symbol_allowlist", "601686,600519,300750")
    symbols = ["601686", "600519", "300750", "000725", "000001"]
    results = [
        company_v2_financial_fusion_rollout_service.evaluate(
            symbol=symbol,
            report_id=1,
            report_ready=symbol == "601686",
            rag_ready=symbol == "601686",
            structured_ready=symbol == "601686",
        )
        for symbol in symbols
    ]
    assert len(results) == 5
    assert results[0]["reason"] in {"DISABLED", "ALLOWLIST", "OUTSIDE_ROLLOUT"}
