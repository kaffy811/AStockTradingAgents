"""
backend/tests/fundamental/test_phase6te_page_profile_performance.py
Phase 6T-E: page/debug 响应 Profile 与性能摘要
"""
from __future__ import annotations

import json

import pytest

from app.services.company_v2_response_profile import apply_response_profile


def _sample_payload():
    return {
        "schema_version": "2.0",
        "market": "CN",
        "symbol": "601686",
        "summary": {"baostock_aggregate_calls": 1},
        "validation_summary": {"status": "pass"},
        "validation_checks": [{"check_id": "x"} for _ in range(50)],
        "modules": {
            "profitability": {
                "ok": True,
                "raw": {"huge": "x" * 1000},
                "field_trace": {"roe": {"raw_field": "roe_avg"}},
                "validation_checks": [{"check_id": "roe_formula"}],
                "debug": {"elapsed_ms": 10},
                "source_chain": [
                    {"provider": "baostock", "endpoint": "get_all_financial_indicators",
                     "success": True, "error_code": "", "raw_sample": "x" * 500},
                ],
                "errors": [{"error_code": "E1", "message": "m" * 500, "stack": "trace" * 100}],
                "diagnosis": {"primary_issue": "OK", "tags": ["OK"], "internal_detail": {"a": 1}},
                "normalized": {"rows": [{"roe": 0.1}], "fields": {"roe": {"value": 0.1}}, "raw_sample": "y" * 500},
                "latest": {"period": "2024-12-31", "roe": 0.1},
                "history": [{"period": "2024-12-31", "roe": 0.1}],
                "chart_contract": {"preferred_chart": "multi_line"},
                "history_coverage": {"periods_count": 1},
                "history_quality": {"status": "pass"},
                "coverage": {"coverage_pct": 90},
                "render": {"has_displayable_data": True},
                "validation_summary": {"status": "pass"},
            },
            "report_documents": {
                "ok": True,
                "normalized": {"rows": [{"local_path": "/tmp/secret.pdf", "title": "年报"}]},
            },
        },
        "history": {"modules": {}, "performance_summary": {"total_latency_ms": 100}},
    }


def test_page_profile_excludes_raw_and_debug_internals():
    result = apply_response_profile(_sample_payload(), "page")
    mod = result["modules"]["profitability"]
    assert "raw" not in mod
    assert "field_trace" not in mod
    assert "validation_checks" not in mod
    assert "debug" not in mod
    assert "raw_sample" not in mod.get("normalized", {})
    assert "validation_checks" not in result
    assert result["response_profile"] == "page"


def test_page_profile_keeps_render_essentials():
    result = apply_response_profile(_sample_payload(), "page")
    mod = result["modules"]["profitability"]
    assert mod["latest"]["period"] == "2024-12-31"
    assert mod["history"]
    assert mod["chart_contract"]["preferred_chart"] == "multi_line"
    assert mod["history_quality"]["status"] == "pass"
    assert mod["coverage"]["coverage_pct"] == 90
    assert mod["validation_summary"]["status"] == "pass"
    assert mod["normalized"]["fields"]["roe"]["value"] == 0.1
    # source badge 压缩保留
    assert mod["source_chain"] == [{"provider": "baostock", "success": True, "error_code": ""}]
    # diagnosis 只保留 primary_issue/tags
    assert mod["diagnosis"] == {"primary_issue": "OK", "tags": ["OK"]}
    # errors 压缩且截断
    assert mod["errors"][0]["error_code"] == "E1"
    assert len(mod["errors"][0]["message"]) <= 120
    assert "stack" not in mod["errors"][0]


def test_page_profile_strips_local_path():
    result = apply_response_profile(_sample_payload(), "page")
    assert "local_path" not in json.dumps(result, ensure_ascii=False)


def test_debug_profile_retains_raw():
    result = apply_response_profile(_sample_payload(), "debug")
    mod = result["modules"]["profitability"]
    assert "raw" in mod
    assert "field_trace" in mod
    assert "validation_checks" in result


def test_debug_profile_also_strips_local_path():
    result = apply_response_profile(_sample_payload(), "debug")
    assert "local_path" not in json.dumps(result, ensure_ascii=False)


def test_page_profile_smaller_than_debug():
    payload = _sample_payload()
    page = json.dumps(apply_response_profile(payload, "page"), ensure_ascii=False)
    debug = json.dumps(apply_response_profile(payload, "debug"), ensure_ascii=False)
    assert len(page) < len(debug)


def test_page_profile_does_not_mutate_input():
    payload = _sample_payload()
    before = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    apply_response_profile(payload, "page")
    # local_path 剥离作用于返回值，原对象不变
    assert json.dumps(payload, ensure_ascii=False, sort_keys=True) == before


# ── performance summary ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_history_dashboard_performance_summary():
    from unittest.mock import AsyncMock, patch
    from app.services.company_v2_history_service import build_company_history_dashboard

    mock_modules = {
        "profitability": {
            "history": [
                {"period": "2023-12-31", "roe": 0.12},
                {"period": "2024-12-31", "roe": 0.13},
            ],
            "latest": {"period": "2024-12-31", "roe": 0.13},
            "period_type": "annual",
            "chart_contract": {"preferred_chart": "multi_line", "series": [{"field": "roe", "display_type": "percent"}]},
            "history_coverage": {"start_period": "2023-12-31", "end_period": "2024-12-31",
                                 "periods_count": 2, "history_truncated": False},
            "data_success": True,
            "provider": "baostock",
        }
    }
    with patch("app.services.company_v2_history_service.fetch_all_modules_history",
               new=AsyncMock(return_value=mock_modules)):
        with patch("app.services.company_v2_history_service.get_stock_basic",
                   new=AsyncMock(return_value={"list_year": 2023, "list_date": "2023-01-05",
                                               "list_date_status": "exact", "symbol": "601686"})):
            result = await build_company_history_dashboard(
                "CN", "601686", period="annual", force_refresh=True)

    perf = result["performance_summary"]
    for key in ("total_latency_ms", "provider_latency_ms", "validation_latency_ms",
                "serialization_latency_ms", "response_size_bytes", "history_rows_total",
                "baostock_aggregate_calls", "cache_hit"):
        assert key in perf
    assert perf["baostock_aggregate_calls"] <= 1
    assert perf["history_rows_total"] == 2
    assert perf["response_size_bytes"] > 0

    # Phase 6T-E: 模块级审计/契约/适用性
    mod = result["modules"]["profitability"]
    assert mod["history_quality"]["status"] in ("pass", "warning")
    assert mod["chart_contract_validation"]["valid"] is True
    assert "metric_applicability" in mod
    # 历史范围语义
    assert result["history_range_label"]
    assert "history_is_full_since_listing" in result


@pytest.mark.asyncio
async def test_partial_provider_failure_does_not_fail_all_modules():
    from unittest.mock import AsyncMock, patch
    from app.services.company_v2_history_service import build_company_history_dashboard

    mock_modules = {
        "profitability": {
            "history": [{"period": "2024-12-31", "roe": 0.13}],
            "latest": {"period": "2024-12-31", "roe": 0.13},
            "period_type": "point_in_time",
            "chart_contract": {"preferred_chart": "multi_line", "series": [{"field": "roe", "display_type": "percent"}]},
            "history_coverage": {"start_period": "2024-12-31", "end_period": "2024-12-31",
                                 "periods_count": 1, "history_truncated": True},
            "data_success": True,
            "provider": "baostock",
        },
        "growth": {
            "history": [], "latest": {}, "period_type": "unknown",
            "chart_contract": {}, "history_coverage": {"history_truncated": True},
            "data_success": False, "provider": "baostock",
        },
    }
    with patch("app.services.company_v2_history_service.fetch_all_modules_history",
               new=AsyncMock(return_value=mock_modules)):
        with patch("app.services.company_v2_history_service.get_stock_basic",
                   new=AsyncMock(return_value={"list_year": 2024, "list_date": "2024-01-05",
                                               "list_date_status": "exact"})):
            result = await build_company_history_dashboard(
                "CN", "601686", period="annual", force_refresh=True)

    assert result["data_success_count"] == 1
    assert result["modules"]["profitability"]["data_success"] is True
    assert result["modules"]["growth"]["data_success"] is False


def test_router_supports_profile_param():
    import inspect
    from app.routers import company_v2_debug as router_module
    source = inspect.getsource(router_module.debug_full)
    assert "profile" in source
    assert "apply_response_profile" in source


def test_no_investment_advice_in_new_services():
    """新增服务源码不含投资建议措辞。"""
    import inspect
    from app.services import (
        company_v2_acceptance_universe,
        company_v2_chart_contract_validator,
        company_v2_history_completeness_audit,
        company_v2_industry_metric_applicability,
        company_v2_period_classifier,
        company_v2_response_profile,
    )
    for mod in (
        company_v2_acceptance_universe,
        company_v2_chart_contract_validator,
        company_v2_history_completeness_audit,
        company_v2_industry_metric_applicability,
        company_v2_period_classifier,
        company_v2_response_profile,
    ):
        source = inspect.getsource(mod)
        for word in ("买入", "卖出", "目标价", "保证上涨"):
            assert word not in source, f"{mod.__name__} contains {word}"
