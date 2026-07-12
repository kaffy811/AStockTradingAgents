from __future__ import annotations


def test_metrics_snapshot_exposes_expected_fields():
    from app.services.company_v2_financial_fusion_metrics import company_v2_financial_fusion_metrics

    company_v2_financial_fusion_metrics.clear()
    company_v2_financial_fusion_metrics.inc("fusion_requests_total", 3)
    company_v2_financial_fusion_metrics.inc("fusion_cache_hits_total", 2)
    company_v2_financial_fusion_metrics.inc("fusion_cache_misses_total", 1)
    company_v2_financial_fusion_metrics.observe_latency("fusion_latency_ms", 100)
    company_v2_financial_fusion_metrics.observe_latency("fusion_latency_ms", 200)
    snapshot = company_v2_financial_fusion_metrics.snapshot()
    assert snapshot["fusion_requests_total"] == 3
    assert snapshot["cache_hit_ratio"] == 2 / 3
    assert snapshot["fields_per_request"] == 0
    assert snapshot["p50_latency_ms"] == 150
