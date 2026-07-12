from __future__ import annotations


def test_latency_metrics_report_no_samples_as_insufficient_data():
    from app.services.company_v2_financial_fusion_health_service import company_v2_financial_fusion_health_service
    from app.services.company_v2_financial_fusion_metrics import company_v2_financial_fusion_metrics

    company_v2_financial_fusion_metrics.clear()
    snapshot = company_v2_financial_fusion_metrics.snapshot()
    health = company_v2_financial_fusion_health_service.health()

    assert snapshot["latency_sample_count"] == 0
    assert snapshot["latency_status"] == "insufficient_samples"
    assert snapshot["p50_latency_ms"] is None
    assert snapshot["p95_latency_ms"] is None
    assert health["status"] == "insufficient_data"
    assert health["p50_latency_ms"] is None
    assert health["p95_latency_ms"] is None


def test_latency_metrics_compute_percentiles_with_samples():
    from app.services.company_v2_financial_fusion_health_service import company_v2_financial_fusion_health_service
    from app.services.company_v2_financial_fusion_metrics import company_v2_financial_fusion_metrics

    company_v2_financial_fusion_metrics.clear()
    company_v2_financial_fusion_metrics.inc("fusion_requests_total", 2)
    company_v2_financial_fusion_metrics.inc("fusion_success_total", 2)
    company_v2_financial_fusion_metrics.inc("fusion_cache_hits_total", 1)
    company_v2_financial_fusion_metrics.inc("fusion_cache_misses_total", 1)
    company_v2_financial_fusion_metrics.observe_latency("total_latency_ms", 100.0)
    company_v2_financial_fusion_metrics.observe_latency("total_latency_ms", 300.0)

    snapshot = company_v2_financial_fusion_metrics.snapshot()
    health = company_v2_financial_fusion_health_service.health()

    assert snapshot["latency_sample_count"] == 2
    assert snapshot["latency_status"] == "ready"
    assert snapshot["p50_latency_ms"] == 200.0
    assert snapshot["p95_latency_ms"] == 300.0
    assert health["status"] == "healthy"
