from __future__ import annotations


def test_circuit_breaker_transitions():
    from app.services.company_v2_financial_fusion_circuit_breaker import company_v2_financial_fusion_circuit_breaker

    company_v2_financial_fusion_circuit_breaker.reset()
    assert company_v2_financial_fusion_circuit_breaker.allow() is True
    company_v2_financial_fusion_circuit_breaker.trip("test")
    assert company_v2_financial_fusion_circuit_breaker.allow() is False
    company_v2_financial_fusion_circuit_breaker.half_open("smoke")
    assert company_v2_financial_fusion_circuit_breaker.snapshot()["state"] == "half_open"
    company_v2_financial_fusion_circuit_breaker.reset()
    assert company_v2_financial_fusion_circuit_breaker.snapshot()["state"] == "closed"
