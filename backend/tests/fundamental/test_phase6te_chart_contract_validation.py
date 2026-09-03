"""
backend/tests/fundamental/test_phase6te_chart_contract_validation.py
Phase 6T-E: 图表契约校验器测试
"""
from __future__ import annotations

import pytest

from app.services.company_v2_chart_contract_validator import (
    VALUATION_QUANTILE_MIN_SAMPLES,
    validate_all_chart_contracts,
    validate_chart_contract,
)


def _rows(n, fields):
    out = []
    for i in range(n):
        year = 2015 + i
        row = {"period": f"{year}-12-31"}
        row.update(fields)
        out.append(row)
    return out


def test_single_period_downgrades_to_metric_cards():
    """单期数据不得画趋势图。"""
    contract = {"preferred_chart": "multi_line", "series": [{"field": "roe", "display_type": "percent"}]}
    result = validate_chart_contract(
        "profitability", contract,
        rows=_rows(1, {"roe": 0.12}),
        period_type="point_in_time",
    )
    assert result["effective_chart"] == "metric_cards"
    assert "single_period_downgraded_to_metric_cards" in result["warnings"]


def test_series_field_must_exist_in_rows():
    contract = {"preferred_chart": "multi_line", "series": [{"field": "ghost_field"}]}
    result = validate_chart_contract(
        "profitability", contract,
        rows=_rows(3, {"roe": 0.1}),
        period_type="annual",
    )
    assert result["valid"] is False
    assert any(i.startswith("series_field_not_in_rows") for i in result["issues"])


def test_percent_scale_100x_error_detected():
    """百分比字段被放大 100 倍时必须报错（如 1050%）。"""
    contract = {"preferred_chart": "multi_line", "series": [{"field": "roe", "display_type": "percent"}]}
    result = validate_chart_contract(
        "profitability", contract,
        rows=_rows(3, {"roe": 1050.0}),
        period_type="annual",
    )
    assert result["valid"] is False
    assert any("percent_field_scale_suspicious" in i for i in result["issues"])


def test_percent_normal_scale_passes():
    contract = {"preferred_chart": "multi_line", "series": [{"field": "roe", "display_type": "percent"}]}
    result = validate_chart_contract(
        "profitability", contract,
        rows=_rows(3, {"roe": 10.5}),
        period_type="annual",
    )
    assert result["valid"] is True


def test_extreme_scale_requires_secondary_axis():
    """量级差 >100x 时必须声明副轴/拆分。"""
    contract = {
        "preferred_chart": "grouped_bar",
        "series": [{"field": "a", "display_type": "ratio"}, {"field": "b", "display_type": "ratio"}],
    }
    result = validate_chart_contract(
        "operation_capability", contract,
        rows=_rows(3, {"a": 0.5, "b": 500.0}),
        period_type="annual",
    )
    assert result["valid"] is False
    assert any("extreme_scale_without_secondary_axis" in i for i in result["issues"])

    contract_ok = {**contract, "auto_secondary_axis": True}
    result_ok = validate_chart_contract(
        "operation_capability", contract_ok,
        rows=_rows(3, {"a": 0.5, "b": 500.0}),
        period_type="annual",
    )
    assert result_ok["valid"] is True
    assert any("secondary_axis" in w for w in result_ok["warnings"])


def test_mixed_period_must_not_use_continuous_line():
    contract = {"preferred_chart": "multi_line", "series": [{"field": "roe"}]}
    result = validate_chart_contract(
        "profitability", contract,
        rows=_rows(3, {"roe": 0.1}),
        period_type="mixed",
    )
    assert result["valid"] is False
    assert "mixed_period_must_not_use_continuous_line" in result["issues"]
    assert result["effective_chart"] == "grouped_bar"


def test_valuation_quantiles_require_min_samples():
    """估值分位默认至少 60 个有效样本；年度少量点不得计算分位。"""
    contract = {"preferred_chart": "metric_cards", "series": [{"field": "pe_ttm", "display_type": "ratio"}]}
    few = validate_chart_contract(
        "valuation", contract,
        rows=_rows(5, {"pe_ttm": 20.0}),
        period_type="annual",
    )
    assert few["quantiles_allowed"] is False
    assert any("valuation_quantiles_disabled" in w for w in few["warnings"])

    many = validate_chart_contract(
        "valuation", contract,
        rows=[{"period": f"2025-01-{(i % 28) + 1:02d}", "pe_ttm": 20.0} for i in range(VALUATION_QUANTILE_MIN_SAMPLES + 5)],
        period_type="daily",
    )
    assert many["quantiles_allowed"] is True


def test_not_applicable_fields_do_not_fail_contract():
    """银行不适用字段缺失不得判定契约失败。"""
    contract = {
        "preferred_chart": "grouped_bar",
        "series": [
            {"field": "asset_turnover", "display_type": "ratio"},
            {"field": "inventory_turnover", "display_type": "ratio"},
        ],
    }
    result = validate_chart_contract(
        "operation_capability", contract,
        rows=_rows(3, {"asset_turnover": 0.5}),  # 无 inventory_turnover
        period_type="annual",
        not_applicable_fields=["inventory_turnover"],
    )
    assert result["valid"] is True


def test_all_series_not_applicable_downgrades():
    contract = {"preferred_chart": "multi_line", "series": [{"field": "current_ratio"}]}
    result = validate_chart_contract(
        "solvency", contract,
        rows=_rows(3, {"current_ratio": None}),
        period_type="annual",
        not_applicable_fields=["current_ratio"],
    )
    assert result["effective_chart"] == "not_applicable"


def test_missing_contract_invalid():
    result = validate_chart_contract("profitability", {}, rows=[], period_type="unknown")
    assert result["valid"] is False
    assert "missing_chart_contract" in result["issues"]


def test_validate_all_chart_contracts_bank():
    """银行股全模块校验：不适用字段不产生 issue。"""
    from app.datasource.history_financial_provider import _CHART_CONTRACTS
    modules = {
        "operation_capability": {
            "chart_contract": _CHART_CONTRACTS["operation_capability"],
            "history": _rows(3, {"asset_turnover": 0.05}),
            "period_type": "annual",
        },
    }
    result = validate_all_chart_contracts(modules, accounting_type="bank")
    assert result["all_valid"] is True
    mod = result["modules"]["operation_capability"]
    assert "inventory_turnover" in mod["not_applicable_fields"]


def test_builtin_contracts_valid_for_typical_data():
    """内置各模块契约对典型数据形态应校验通过。"""
    from app.datasource.history_financial_provider import _CHART_CONTRACTS

    typical = {
        "profitability": {"roe": 12.5, "gross_margin": 30.0, "net_margin": 8.0, "roa": 6.0},
        "growth": {
            "main_business_revenue": 1e9, "net_profit": 1e8,
            "net_profit_yoy": 0.15, "net_profit_parent_yoy": 0.12,
        },
        "cashflow_quality": {"ocf_to_np": 1.1, "ocf_to_revenue": 0.15, "cashflow_revenue_ratio": 0.12},
        "solvency": {"current_ratio": 2.0, "quick_ratio": 1.5, "cash_ratio": 0.8, "debt_ratio": 45.0},
        "operation_capability": {"asset_turnover": 0.8, "inventory_turnover": 5.0, "receivable_turnover": 8.0},
        "dupont": {"roe": 12.0, "net_margin": 8.0, "asset_turnover": 0.8, "equity_multiplier": 1.8},
    }
    for mk, fields in typical.items():
        result = validate_chart_contract(
            mk, _CHART_CONTRACTS[mk],
            rows=_rows(5, fields),
            period_type="annual",
        )
        assert result["valid"] is True, f"{mk}: {result['issues']}"
