from __future__ import annotations


def test_health_snapshot_is_healthy_without_alerts():
    from app.services.company_v2_financial_fusion_health_service import company_v2_financial_fusion_health_service
    from app.services.company_v2_financial_fusion_metrics import company_v2_financial_fusion_metrics

    company_v2_financial_fusion_metrics.clear()
    health = company_v2_financial_fusion_health_service.health()
    assert health["status"] == "insufficient_data"
    assert health["alerts"] == []
