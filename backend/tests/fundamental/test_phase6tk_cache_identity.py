from __future__ import annotations


def test_field_order_normalized_but_field_set_changes_identity():
    from app.services.company_v2_financial_fusion_job_service import _fingerprint

    a = _fingerprint(symbol="600519", report_id=2, fields=["revenue", "net_profit"], refresh=False)
    b = _fingerprint(symbol="600519", report_id=2, fields=["net_profit", "revenue"], refresh=False)
    c = _fingerprint(symbol="600519", report_id=2, fields=["revenue"], refresh=False)
    d = _fingerprint(symbol="600519", report_id=2, fields=["revenue", "net_profit"], refresh=True)
    assert a == b
    assert a != c
    assert a != d
