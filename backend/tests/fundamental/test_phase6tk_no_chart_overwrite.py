from __future__ import annotations


def test_fusion_result_does_not_overwrite_chart_values():
    chart_value_before = {"net_profit": 100}
    fusion_result = {"field_name": "net_profit", "official_value": 101, "fusion_status": "value_conflict"}
    chart_value_after = dict(chart_value_before)
    assert fusion_result["official_value"] != chart_value_after["net_profit"]
    assert chart_value_after == chart_value_before
