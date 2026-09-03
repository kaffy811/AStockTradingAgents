"""
backend/tests/fundamental/test_phase6te_cross_stock_history_acceptance.py
Phase 6T-E: 跨股票历史数据验收（分类器/审计/范围语义/行级口径）
"""
from __future__ import annotations

from datetime import date

import pytest


# ── 验收样本定义 ──────────────────────────────────────────────────────────────

def test_acceptance_universe_definition():
    from app.services.company_v2_acceptance_universe import (
        ACCEPTANCE_UNIVERSE,
        ACCEPTANCE_SYMBOLS,
        get_acceptance_stock,
    )
    assert len(ACCEPTANCE_UNIVERSE) >= 8
    for required in ("600519", "000725", "601686", "300750", "688981", "601318", "000001"):
        assert required in ACCEPTANCE_SYMBOLS
    # 至少一只上市不足5年（601728 中国电信 2021-08）
    assert "601728" in ACCEPTANCE_SYMBOLS
    bank = get_acceptance_stock("000001")
    assert bank.special_accounting_type == "bank"
    insurer = get_acceptance_stock("601318")
    assert insurer.special_accounting_type == "insurer"


def test_acceptance_universe_invalid_accounting_type_rejected():
    from app.services.company_v2_acceptance_universe import AcceptanceStock
    with pytest.raises(ValueError):
        AcceptanceStock(
            symbol="000000", market="CN",
            expected_exchange="上交所", expected_industry_type="x",
            expected_min_annual_periods=1, expected_min_quarterly_periods=1,
            special_accounting_type="not_a_type",
        )


# ── 权威期间分类器 ────────────────────────────────────────────────────────────

def test_period_classifier_valid_dates():
    from app.services.company_v2_period_classifier import (
        classify_period_date,
        is_valid_period,
    )
    assert is_valid_period("2024-12-31")
    assert not is_valid_period("")
    assert not is_valid_period("2024/12/31")
    assert classify_period_date("2024-12-31") == "annual_end"
    assert classify_period_date("2024-09-30") == "quarter_end"
    assert classify_period_date("2024-07-15") == "daily"
    assert classify_period_date("bad") == "invalid"


def test_period_classifier_rows_types():
    from app.services.company_v2_period_classifier import classify_rows_period_type
    assert classify_rows_period_type([]) == "unknown"
    assert classify_rows_period_type([{"period": "2024-12-31"}]) == "point_in_time"
    assert classify_rows_period_type(
        [{"period": "2022-12-31"}, {"period": "2023-12-31"}]
    ) == "annual"
    assert classify_rows_period_type(
        [{"period": "2024-03-31"}, {"period": "2024-06-30"}]
    ) == "quarterly"
    # 报告期与日频混合 → mixed
    assert classify_rows_period_type(
        [{"period": "2024-12-31"}, {"period": "2024-07-15"}]
    ) == "mixed"


def test_value_basis_distinction_annual_vs_quarterly():
    """YYYY-12-31 与季度末靠 value_basis 区分，不能只看日期。"""
    from app.services.company_v2_period_classifier import infer_value_basis
    assert infer_value_basis("2024-12-31", module_key="profitability") == "annual_cumulative"
    assert infer_value_basis("2024-09-30", module_key="profitability") == "quarterly_cumulative"
    # 资产负债表 → 时点
    assert infer_value_basis("2024-12-31", module_key="solvency") == "point_in_time"
    # 估值 → 当前行情
    assert infer_value_basis("2026-07-10", module_key="valuation") == "current_market"


def test_enrich_row_fields():
    from app.services.company_v2_period_classifier import enrich_row
    row = {"period": "2024-09-30", "roe": 0.1}
    enrich_row(row, module_key="profitability", source_table="profit")
    assert row["report_year"] == 2024
    assert row["quarter"] == 3
    assert row["report_period_type"] == "quarterly"
    assert row["value_basis"] == "quarterly_cumulative"
    assert row["source_provider"] == "baostock"


# ── 历史完整性审计 ────────────────────────────────────────────────────────────

def _module(rows, latest=None, period_type="annual"):
    return {
        "history": rows,
        "latest": latest if latest is not None else (rows[-1] if rows else {}),
        "period_type": period_type,
    }


def test_audit_history_period_order():
    from app.services.company_v2_history_completeness_audit import audit_module_history
    rows = [
        {"period": "2023-12-31", "roe": 0.1},
        {"period": "2022-12-31", "roe": 0.2},
    ]
    audit = audit_module_history(
        "profitability", _module(rows, latest=rows[0]),
        requested_period="annual", start_year=2022, end_year=2023,
        today=date(2026, 7, 10),
    )
    assert audit["period_order_valid"] is False
    assert audit["status"] == "fail"


def test_audit_duplicate_period_detection():
    from app.services.company_v2_history_completeness_audit import audit_module_history
    rows = [
        {"period": "2023-12-31", "roe": 0.1},
        {"period": "2023-12-31", "roe": 0.1},
    ]
    audit = audit_module_history(
        "profitability", _module(rows),
        requested_period="annual", start_year=2023, end_year=2023,
        today=date(2026, 7, 10),
    )
    assert audit["duplicate_period_count"] == 1
    assert audit["status"] == "fail"


def test_audit_future_period_detection():
    from app.services.company_v2_history_completeness_audit import audit_module_history
    rows = [
        {"period": "2025-12-31", "roe": 0.1},
        {"period": "2027-12-31", "roe": 0.2},   # 未来报告期
    ]
    audit = audit_module_history(
        "profitability", _module(rows),
        requested_period="annual", start_year=2025, end_year=2027,
        today=date(2026, 7, 10),
    )
    assert "2027-12-31" in audit["future_periods"]
    assert audit["status"] == "fail"


def test_audit_pre_listing_period_detection():
    from app.services.company_v2_history_completeness_audit import audit_module_history
    rows = [
        {"period": "2014-12-31", "roe": 0.1},   # 早于上市（2016）
        {"period": "2023-12-31", "roe": 0.2},
    ]
    audit = audit_module_history(
        "profitability", _module(rows),
        list_date="2016-06-17",
        requested_period="annual", start_year=2016, end_year=2023,
        today=date(2026, 7, 10),
    )
    assert "2014-12-31" in audit["pre_listing_periods"]
    assert audit["status"] == "fail"


def test_audit_latest_matches_history():
    from app.services.company_v2_history_completeness_audit import audit_module_history
    rows = [
        {"period": "2022-12-31", "roe": 0.1},
        {"period": "2023-12-31", "roe": 0.2},
    ]
    good = audit_module_history(
        "profitability", _module(rows, latest=rows[-1]),
        requested_period="annual", start_year=2022, end_year=2023,
        today=date(2026, 7, 10),
    )
    assert good["latest_matches_history"] is True
    bad = audit_module_history(
        "profitability", _module(rows, latest=rows[0]),
        requested_period="annual", start_year=2022, end_year=2023,
        today=date(2026, 7, 10),
    )
    assert bad["latest_matches_history"] is False
    assert bad["status"] == "fail"


def test_audit_invalid_values_not_counted_as_valid():
    """空字符串 / NaN / Infinity 不得当成有效数据。"""
    from app.services.company_v2_history_completeness_audit import audit_module_history
    rows = [
        {"period": "2022-12-31", "roe": float("nan")},
        {"period": "2023-12-31", "roe": ""},
    ]
    audit = audit_module_history(
        "profitability", _module(rows, latest={}),
        requested_period="annual", start_year=2022, end_year=2023,
        today=date(2026, 7, 10),
    )
    assert any(w.startswith("rows_with_invalid_values") for w in audit["warnings"])


def test_audit_missing_periods_not_include_future():
    """expected_periods 不得要求尚未披露的未来报告期。"""
    from app.services.company_v2_history_completeness_audit import audit_module_history
    rows = [{"period": f"{y}-12-31", "roe": 0.1} for y in range(2022, 2026)]
    audit = audit_module_history(
        "profitability", _module(rows),
        requested_period="annual", start_year=2022, end_year=2026,
        today=date(2026, 7, 10),
    )
    # 2026-12-31 尚未到期，不应计入缺失
    assert "2026-12-31" not in audit["missing_periods"]
    assert audit["completeness_pct"] == 100


# ── 历史范围语义 ──────────────────────────────────────────────────────────────

def _range_modules(start, end, truncated, rows_count=12):
    return {
        "profitability": {
            "history": [{"period": start}] * rows_count,
            "history_coverage": {
                "start_period": start,
                "end_period": end,
                "history_truncated": truncated,
            },
        }
    }


def test_history_range_full_since_listing():
    from app.services.company_v2_history_service import _build_history_range
    result = _build_history_range(
        _range_modules("2016-12-31", "2025-12-31", False),
        list_date="2016-06-17", list_date_status="exact", period="annual",
    )
    assert result["history_is_full_since_listing"] is True
    assert result["history_range_label"] == "上市以来"
    assert result["history_truncated"] is False


def test_history_range_truncated_not_claim_full():
    """provider 只返回部分历史时，不得声称"上市以来"。"""
    from app.services.company_v2_history_service import _build_history_range
    result = _build_history_range(
        _range_modules("2015-12-31", "2025-12-31", True),
        list_date="2001-08-27", list_date_status="exact", period="annual",
    )
    assert result["history_is_full_since_listing"] is False
    assert result["history_range_label"] != "上市以来"
    assert "2015" in result["history_range_label"]
    assert result["truncation_reason"] == "PROVIDER_HISTORY_LIMIT"


def test_history_range_unknown_list_date():
    from app.services.company_v2_history_service import _build_history_range
    result = _build_history_range(
        _range_modules("2020-12-31", "2025-12-31", False),
        list_date="", list_date_status="unknown", period="annual",
    )
    assert result["history_range_label"] == "历史数据范围未知"


def test_history_range_few_periods():
    from app.services.company_v2_history_service import _build_history_range
    result = _build_history_range(
        _range_modules("2023-12-31", "2025-12-31", True, rows_count=3),
        list_date="2010-01-01", list_date_status="exact", period="annual",
    )
    assert "最近 3 期" == result["history_range_label"]


# ── 金融行业适用性 ────────────────────────────────────────────────────────────

def test_bank_inventory_turnover_not_applicable():
    from app.services.company_v2_industry_metric_applicability import (
        check_field_applicability,
    )
    result = check_field_applicability("inventory_turnover", "bank")
    assert result["applicable"] is False
    assert result["reason"] == "NOT_APPLICABLE_FOR_BANK"
    assert result["display_value"] == "N/A"


def test_bank_current_ratio_not_general_meaning():
    from app.services.company_v2_industry_metric_applicability import (
        check_field_applicability,
    )
    for field in ("current_ratio", "quick_ratio", "cash_ratio"):
        result = check_field_applicability(field, "bank")
        assert result["applicable"] is False


def test_general_industrial_metrics_applicable():
    from app.services.company_v2_industry_metric_applicability import (
        check_field_applicability,
    )
    result = check_field_applicability("inventory_turnover", "general_industrial")
    assert result["applicable"] is True


def test_infer_accounting_type_from_universe_and_industry():
    from app.services.company_v2_industry_metric_applicability import (
        infer_accounting_type,
    )
    assert infer_accounting_type("", "000001") == "bank"
    assert infer_accounting_type("", "601318") == "insurer"
    assert infer_accounting_type("银行", "999999") == "bank"
    assert infer_accounting_type("白酒", "999999") == "general_industrial"


def test_module_applicability_na_not_module_failure():
    """全部字段不适用 → module_applicable=False，但不是数据错误。"""
    from app.services.company_v2_industry_metric_applicability import (
        build_module_applicability,
    )
    result = build_module_applicability(
        "operation_capability",
        ["asset_turnover", "inventory_turnover", "receivable_turnover"],
        "bank",
    )
    assert "inventory_turnover" in result["not_applicable_fields"]
    assert "asset_turnover" not in result["not_applicable_fields"]
    assert result["module_applicable"] is True


# ── growth 字段口径修复 ───────────────────────────────────────────────────────

def test_growth_chart_contract_uses_real_provider_fields():
    """growth 契约不得引用 provider 不存在的"营业收入/归母净利润"字段。"""
    from app.datasource.history_financial_provider import _CHART_CONTRACTS
    fields = [s["field"] for s in _CHART_CONTRACTS["growth"]["series"]]
    assert "revenue_yoy" not in fields          # BaoStock 无营收同比
    assert "main_business_revenue" in fields    # 主营业务收入（真实口径）
    assert "net_profit_yoy" in fields
    assert "net_profit_parent_yoy" in fields
    names = [s["display_name"] for s in _CHART_CONTRACTS["growth"]["series"]]
    assert "营业收入" not in names
    assert "归母净利润" not in names


def test_growth_rows_join_absolute_values_from_profit_table():
    from app.datasource.history_financial_provider import _build_module_history_from_rows
    growth_raw = [
        {"stat_date": "2023-12-31", "yoy_ni": "0.10", "yoy_pni": "0.12"},
        {"stat_date": "2024-12-31", "yoy_ni": "0.15", "yoy_pni": "0.18"},
    ]
    profit_raw = [
        {"stat_date": "2023-12-31", "mb_revenue": "900000000.0", "net_profit": "90000000.0"},
        {"stat_date": "2024-12-31", "mb_revenue": "1000000000.0", "net_profit": "100000000.0"},
    ]
    result = _build_module_history_from_rows(
        "growth", growth_raw,
        ts_code="601686.SH", start_year=2023, end_year=2024,
        period="annual", data_success=True,
        aux_profit_rows=profit_raw,
    )
    latest = result["latest"]
    assert latest["main_business_revenue"] == pytest.approx(1e9)
    assert latest["net_profit"] == pytest.approx(1e8)
    assert latest["net_profit_yoy"] == pytest.approx(0.15)
    # 行级口径字段
    assert latest["value_basis"] == "annual_cumulative"
    assert latest["report_year"] == 2024
    assert latest["source_provider"] == "baostock"
