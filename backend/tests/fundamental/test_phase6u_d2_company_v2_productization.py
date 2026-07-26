from __future__ import annotations

from pathlib import Path

import pytest


def test_phase6u_d2_field_metadata_units():
    from app.services.company_v2_formatter_registry import format_field

    assert format_field("parent_net_profit_yoy", 0.057758)["display_value"] == "5.78%"
    assert format_field("pct_chg", 25.0)["display_value"] == "25.00%"
    assert format_field("asset_turnover", 0.12)["display_value"] == "0.12"


def test_phase6u_d2_cashflow_alias_and_warning():
    from app.datasource.history_financial_provider import _build_module_history_from_rows

    result = _build_module_history_from_rows(
        "cashflow_quality",
        [
            {"stat_date": "2024-12-31", "cfo_to_np": 7.1965, "cfo_to_or": 0.2412, "cfo_to_gr": 0.2412},
        ],
        ts_code="000725.SZ",
        start_year=2024,
        end_year=2024,
        period="annual",
        data_success=True,
    )
    latest = result["latest"]
    assert latest["ocf_to_revenue"] == pytest.approx(0.2412)
    assert latest["cashflow_revenue_ratio"] == pytest.approx(0.2412)
    assert latest["aliases"]["cashflow_revenue_ratio"] == "ocf_to_revenue"
    assert latest["warnings"][0]["code"] == "CFO_TO_NP_DENOMINATOR_SENSITIVE"


def test_phase6u_d2_dupont_formula_match_and_mismatch():
    from app.datasource.history_financial_provider import _build_module_history_from_rows

    matched = _build_module_history_from_rows(
        "dupont",
        [{
            "stat_date": "2024-12-31",
            "dupont_roe": 0.040579,
            "dupont_npi": 1.284173,
            "dupont_nitogr": 0.020896,
            "dupont_at": 0.467237,
            "dupont_am": 3.236569,
        }],
        ts_code="000725.SZ",
        start_year=2024,
        end_year=2024,
        period="annual",
        data_success=True,
    )
    assert matched["latest"]["net_margin"] == pytest.approx(1.284173 * 0.020896, rel=1e-5)
    assert matched["latest"]["dupont_formula_status"] == "match"

    mismatched = _build_module_history_from_rows(
        "dupont",
        [{
            "stat_date": "2024-12-31",
            "dupont_roe": 0.0126,
            "dupont_npi": 0.9989,
            "dupont_nitogr": 0.9989,
            "dupont_at": 0.12,
            "dupont_am": 3.23,
        }],
        ts_code="000725.SZ",
        start_year=2024,
        end_year=2024,
        period="annual",
        data_success=True,
    )
    assert mismatched["latest"]["dupont_formula_status"] == "mismatch"
    assert mismatched["chart_contract"]["preferred_chart"] == "metric_cards"
    assert mismatched["latest"]["warnings"][0]["code"] == "DUPONT_FORMULA_MISMATCH"


def test_phase6u_d2_history_keeps_rows_with_missing_fields():
    from app.datasource.history_financial_provider import _build_module_history_from_rows

    result = _build_module_history_from_rows(
        "growth",
        [
            {"stat_date": "2023-12-31", "yoy_ni": 0.1, "yoy_pni": None},
            {"stat_date": "2024-12-31", "yoy_ni": None, "yoy_pni": 0.2},
        ],
        ts_code="000725.SZ",
        start_year=2023,
        end_year=2024,
        period="annual",
        data_success=True,
    )
    assert [row["period"] for row in result["history"]] == ["2023-12-31", "2024-12-31"]
    assert result["latest"]["period"] == "2024-12-31"


def test_phase6u_d2_report_get_prefers_persisted_route_contract():
    source = (Path(__file__).resolve().parents[2] / "app/routers/company_v2_debug.py").read_text(encoding="utf-8")
    assert "_list_persisted_report_documents" in source
    assert "if persisted:" in source
