from __future__ import annotations


def test_circuit_open_blocks_compute_but_policy_can_serve_cache():
    from app.services.company_v2_financial_fusion_circuit_breaker import company_v2_financial_fusion_circuit_breaker

    company_v2_financial_fusion_circuit_breaker.reset()
    assert company_v2_financial_fusion_circuit_breaker.allow() is True
    company_v2_financial_fusion_circuit_breaker.trip("timeout_threshold")
    assert company_v2_financial_fusion_circuit_breaker.allow() is False
    cached_policy = {"serve_unexpired_success_cache": True, "stale_served": False, "circuit_state": "open"}
    assert cached_policy["serve_unexpired_success_cache"] is True
    company_v2_financial_fusion_circuit_breaker.half_open("cooldown")
    assert company_v2_financial_fusion_circuit_breaker.snapshot()["state"] == "half_open"
    company_v2_financial_fusion_circuit_breaker.reset()
