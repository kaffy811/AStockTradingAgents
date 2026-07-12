from __future__ import annotations

from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[3]


def test_formatter_registry_formats_core_types():
    from app.services.company_v2_formatter_registry import format_field

    assert format_field("latest_price", 4.96)["display_value"] == "4.96"
    assert format_field("roe", 0.018961)["display_value"] == "1.90%"
    assert format_field("pct_chg", -1.7822)["display_value"] == "-1.78%"
    assert format_field("pe_ttm", 10.849659)["display_value"] == "10.85"
    assert format_field("turnover", 0)["display_value"] == "0.00%"
    assert format_field("latest_price", None)["display_value"] == "—"


def test_raw_numeric_display_value_not_dash():
    from app.services.company_v2_debug_service import _apply_display_metadata, _fill_fields

    rows = [{
        "latest_price": 4.96,
        "pct_chg": -1.7822,
        "turnover": 0.3237,
        "pe_ttm": 10.849659,
        "pb": 1.098548,
    }]
    fields, _, _ = _fill_fields("quote_overview", rows, rows[0])
    _apply_display_metadata("quote_overview", rows, fields)

    assert fields["latest_price"]["display_value"] == "4.96"
    assert fields["pct_chg"]["display_value"] == "-1.78%"
    assert fields["turnover"]["display_value"] == "0.32%"
    assert fields["pe_ttm"]["display_value"] == "10.85"
    assert fields["pb"]["display_value"] == "1.10"


def test_akshare_wrapper_success_business_failed_is_not_data_success():
    from app.services.company_v2_debug_service import _provider_data_success

    result = {
        "success": True,
        "status": "success",
        "rows_count": 2,
        "raw_sample": [{}, {"status": "failed", "reason_code": "NETWORK_UNAVAILABLE"}],
    }
    assert _provider_data_success(result) is False


@pytest.mark.asyncio
async def test_baostock_fallback_price_is_historical(monkeypatch):
    from app.services.company_v2_debug_service import company_v2_debug_service

    async def fake_runner(provider, endpoint, fn, args, kwargs, **options):
        if provider == "akshare":
            return {
                "provider": "akshare",
                "endpoint": endpoint,
                "attempted": True,
                "success": True,
                "status": "success",
                "rows_count": 2,
                "raw_sample": [{}, {"status": "failed", "reason_code": "NETWORK_UNAVAILABLE"}],
            }
        return {
            "provider": "baostock",
            "endpoint": endpoint,
            "attempted": True,
            "success": True,
            "status": "success",
            "rows_count": 1,
            "raw_sample": [{
                "date": "2026-07-08",
                "close": 4.96,
                "change_pct": -1.7822,
                "turnover_rate": 0.3237,
                "pe_ttm": 10.849659,
                "pb": 1.098548,
            }],
        }

    monkeypatch.setattr("app.services.company_v2_debug_service.run_provider_with_debug", fake_runner)
    env = await company_v2_debug_service.build_module(
        "CN",
        "601686",
        "quote_overview",
        providers=["akshare", "baostock"],
        force_refresh=True,
    )

    row = env.normalized.rows[0]
    assert row["price_is_realtime"] is False
    assert row["price_label"] == "最近收盘价"
    assert row["price_data_status"] == "historical_fallback"
    assert env.provider_summary["akshare"]["data_success"] is False
    assert env.normalized.fields["latest_price"]["display_value"] == "4.96"


def test_field_trace_coverage_and_computed_market_cap():
    from app.services.company_v2_debug_service import _coverage, _field_trace, _fill_fields

    rows = [{"latest_price": 4.96, "latest_price_source": "baostock_kline_fallback"}]
    context = {
        "share_capital_context": {
            "total_share": 1471547040,
            "float_share": 1471547040,
            "source": "baostock_aggregate",
            "provider": "baostock",
            "provider_method": "get_all_financial_indicators",
        }
    }
    fields, missing, computed = _fill_fields("quote_overview", rows, rows[0], context=context)
    trace = _field_trace(fields, [])
    coverage = _coverage("quote_overview", fields, missing, computed)

    assert fields["market_cap"]["computed"] is True
    assert fields["market_cap"]["computed_formula"] == "latest_price * total_share"
    assert fields["float_market_cap"]["computed"] is True
    assert trace["market_cap"]["computed"] is True
    assert coverage["computed_fields"] == 2
    assert coverage["coverage_pct"] < 100


def test_report_zero_count_status_machine_and_schema_features():
    from app.schemas.company_v2_debug import CompanyV2DebugEnvelope, CompanyV2Error
    from app.services.company_v2_debug_service import _coverage, _fill_fields, _render
    from app.services.company_v2_debug_diagnosis_service import diagnose_company_v2_envelope

    env = CompanyV2DebugEnvelope(
        request_id="r1",
        market="CN",
        symbol="601686",
        ts_code="601686.SH",
        module_key="report_documents",
        data_mode="free",
    )
    env.normalized.rows = [{"documents_count": 0, "report_status": "EMPTY"}]
    env.normalized.metrics = env.normalized.rows[0]
    fields, missing, computed = _fill_fields("report_documents", env.normalized.rows, env.normalized.metrics)
    env.normalized.fields = fields
    env.coverage = _coverage("report_documents", fields, missing, computed)
    env.render = _render("report_documents", env.normalized.rows, fields)
    env.errors.append(CompanyV2Error(layer="provider", error_code="REPORT_PDF_NOT_FOUND", message="none"))
    env.diagnosis = diagnose_company_v2_envelope(env.model_dump())

    assert env.schema_version == "2.0"
    assert "formatter_registry" in env.schema_features
    assert fields == {}
    assert env.normalized.rows[0]["documents_count"] == 0
    assert env.render.renderable is True
    assert env.render.has_displayable_data is False
    assert env.diagnosis["primary_issue"] == "REPORT_PDF_NOT_FOUND"


def test_no_sensitive_or_restricted_wording_in_company_v2_sources():
    files = [
        ROOT / "backend/app/services/company_v2_debug_service.py",
        ROOT / "frontend/src/views/CompanyV2View.vue",
        ROOT / "frontend/src/components/company-v2/CompanyV2Section.vue",
        ROOT / "frontend/src/components/company-v2/CompanyV2DebugPanel.vue",
    ]
    source = "\n".join(path.read_text(encoding="utf-8") for path in files)
    assert "local_path" not in source
    assert "DATA_MODE=free：BaoStock 和 AkShare 均未返回数据" not in source
    assert "建议买入" not in source
    assert "建议卖出" not in source
    assert "保证上涨" not in source
