from __future__ import annotations


def test_calculator_handles_period_warnings_and_percentage_points():
    from app.services.company_v2_report_comparison_calculator import calculate_comparison_change

    item = {
        "topic": "营业收入",
        "reports": [
            {"report_id": 2, "report_year": 2024, "report_type": "q3", "numeric_value": 40.0, "unit": "元"},
            {"report_id": 1, "report_year": 2024, "report_type": "annual", "numeric_value": 54.0, "unit": "元"},
        ],
    }
    result = calculate_comparison_change(item)
    assert result["computed"] is True
    assert result["comparable"] is True
    assert "period_basis_warning" in result["warnings"]
    assert result["absolute_change"] == 14.0

    percent_item = {
        "topic": "毛利率",
        "reports": [
            {"report_id": 3, "report_year": 2023, "report_type": "annual", "numeric_value": 10.0, "unit": "%"},
            {"report_id": 1, "report_year": 2024, "report_type": "annual", "numeric_value": 12.0, "unit": "%"},
        ],
    }
    percent_result = calculate_comparison_change(percent_item)
    assert percent_result["change_unit"] == "percentage_points"
    assert percent_result["absolute_change"] == 2.0


def test_calculator_rejects_unit_mismatch_and_missing_values():
    from app.services.company_v2_report_comparison_calculator import calculate_comparison_change

    unit_item = {
        "topic": "营业收入",
        "reports": [
            {"report_id": 3, "report_year": 2023, "report_type": "annual", "numeric_value": 10.0, "unit": "万元"},
            {"report_id": 1, "report_year": 2024, "report_type": "annual", "numeric_value": 12.0, "unit": "元"},
        ],
    }
    unit_result = calculate_comparison_change(unit_item)
    assert unit_result["computed"] is False
    assert "unit_mismatch" in unit_result["warnings"]

    zero_item = {
        "topic": "营业收入",
        "reports": [
            {"report_id": 3, "report_year": 2023, "report_type": "annual", "numeric_value": 0.0, "unit": "元"},
            {"report_id": 1, "report_year": 2024, "report_type": "annual", "numeric_value": 12.0, "unit": "元"},
        ],
    }
    zero_result = calculate_comparison_change(zero_item)
    assert zero_result["computed"] is True
    assert zero_result["percentage_change"] is None

