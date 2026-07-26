from __future__ import annotations

import pytest


def test_debug_envelope_schema():
    from app.schemas.company_v2_debug import CompanyV2DebugEnvelope

    env = CompanyV2DebugEnvelope(
        request_id="rid",
        market="CN",
        symbol="601686",
        ts_code="601686.SH",
        module_key="profitability",
        data_mode="free",
    )
    data = env.model_dump()
    assert data["request_id"] == "rid"
    assert data["raw"] == {}
    assert "table_renderable" in data["render"]


@pytest.mark.asyncio
async def test_provider_raw_json_sample():
    from app.datasource.debug_provider_runner import run_provider_with_debug

    result = await run_provider_with_debug(
        "dummy", "rows", lambda: [{"a": 1, "token": "secret"}, {"a": 0}], include_raw=True
    )
    assert result["success"] is True
    assert result["rows_count"] == 2
    assert result["raw_sample"][0]["token"] == "[redacted]"
    assert "a" in result["non_null_fields"]


def test_baostock_raw_to_normalized():
    from app.services.company_v2_debug_service import company_v2_debug_service

    sample = [{
        "profit": [{
            "roe_avg": 0.12,
            "gpMargin": None,
            "gross_margin": 0.55,
            "net_margin": 0.23,
        }]
    }]
    rows = company_v2_debug_service._normalize_baostock_financial("profitability", sample)
    assert rows[0]["roe"] == 0.12
    assert rows[0]["gross_margin"] == 0.55


def test_akshare_raw_to_normalized():
    from app.services.company_v2_debug_service import company_v2_debug_service

    rows = company_v2_debug_service._normalize_akshare_financial(
        "cashflow_quality",
        [{"revenue": 10, "operating_cashflow": 2, "total_assets": 100, "total_liabilities": 40}],
    )
    assert rows[0]["ocf_to_revenue"] == 0.2
    assert rows[0]["debt_ratio"] == 0.4


def test_quote_completion_chain_computed_market_cap():
    from app.services.company_v2_debug_service import _fill_fields

    rows = [{"latest_price": 10, "total_share": 1000, "latest_price_source": "baostock_kline_fallback"}]
    fields, missing, computed = _fill_fields("quote_overview", rows, {})
    assert fields["market_cap"]["value"] == 10000
    assert fields["market_cap"]["source"] == "computed"
    assert computed["market_cap"] == "latest_price * total_share"
    assert "float_market_cap" in missing


def test_financial_completion_chain_missing_reason():
    from app.services.company_v2_debug_service import _fill_fields

    fields, missing, computed = _fill_fields("profitability", [{"roe": 0}], {})
    assert fields["roe"]["value"] == 0
    assert missing["roa"] == "FIELD_MISSING"
    assert computed == {}


def test_share_capital_missing_reason():
    from app.core.error_codes import SHARE_CAPITAL_MISSING
    from app.services.company_v2_debug_service import _fill_fields

    _, missing, _ = _fill_fields("quote_overview", [{"latest_price": 10}], {})
    assert missing["market_cap"] == SHARE_CAPITAL_MISSING


def test_all_null_rows_hidden_and_zero_valid():
    from app.services.company_v2_debug_service import has_displayable_data, _render

    assert has_displayable_data([{"roe": 0}], ["roe"]) is True
    assert has_displayable_data([{"roe": "—"}], ["roe"]) is False
    render = _render("profitability", [{"roe": "—"}], {})
    assert render.has_displayable_data is False
    assert render.reason == "ALL_NULL_ROWS"


def test_error_codes_exist_and_distinct():
    from app.core import error_codes as ec

    assert ec.AUTH_REQUIRED == "AUTH_REQUIRED"
    assert ec.CACHE_UNAVAILABLE == "CACHE_UNAVAILABLE"
    assert ec.PROVIDER_NETWORK_ERROR == "PROVIDER_NETWORK_ERROR"
    assert ec.PROVIDER_SCHEMA_CHANGED == "PROVIDER_SCHEMA_CHANGED"
    assert ec.PROVIDER_TIMEOUT == "PROVIDER_TIMEOUT"
    assert ec.AUTH_REQUIRED != ec.PROVIDER_EMPTY


@pytest.mark.asyncio
async def test_pdf_discovery_attempts_cninfo_first(monkeypatch):
    from app.services.company_v2_debug_service import company_v2_debug_service

    calls = []

    class Tool:
        async def search(self, stock_code, company_name, report_type, report_year):
            calls.append(stock_code)
            return [{"title": "annual", "pdf_url": "https://example.test/a.pdf"}]

    import app.tools.reports.cninfo_report_search_tool as cninfo
    monkeypatch.setattr(cninfo, "cninfo_tool", Tool())

    attempts = await company_v2_debug_service.discover_reports("CN", "600519", db=None, force_refresh=True)
    assert attempts[0]["provider"] == "cninfo"
    assert attempts[0]["candidate_count"] == 1
    assert calls == ["600519"]


def test_include_raw_false_by_default_and_dev_only_helper():
    from app.routers.company_v2_debug import _allow_raw
    from app.core.config import settings

    old = settings.app_env
    settings.app_env = "production"
    try:
        assert _allow_raw(False, None) is False
        assert _allow_raw(True, None) is False
    finally:
        settings.app_env = old


def test_no_secret_local_path_in_raw():
    from app.core.structured_debug_logger import sanitize_debug_payload

    data = sanitize_debug_payload({"token": "x", "local_path": "/tmp/a.pdf", "ok": 1})
    assert data["token"] == "[redacted]"
    assert "local_path" not in data
    assert data["ok"] == 1


def test_render_json_contains_table_renderable():
    from app.services.company_v2_debug_service import _render

    # Phase 6T-E: growth 核心字段对齐 BaoStock 真实口径（无 revenue），改用 net_profit_yoy
    render = _render("growth", [{"net_profit_yoy": 0}], {"net_profit_yoy": {"value": 0}})
    data = render.model_dump()
    assert data["table_renderable"] is True
    assert data["has_displayable_data"] is True


@pytest.mark.asyncio
async def test_cache_first_reduces_provider_calls():
    from app.services.company_v2_debug_service import company_v2_debug_service

    key = company_v2_debug_service._cache_key("CN", "000001", "profitability")
    await company_v2_debug_service._write_cache(key, {
        "normalized": {"rows": [{"roe": 0.1}], "metrics": {"roe": 0.1}, "fields": {"roe": {"value": 0.1, "source": "cache"}}},
        "completion": {"filled_fields": {"roe": {"value": 0.1, "source": "cache"}}, "still_missing_fields": {}, "computed_fields": {}, "fallback_chain": {"roe": "cache"}},
        "render": {"renderable": True, "chart_renderable": False, "table_renderable": True, "has_displayable_data": True, "visible_fields": ["roe"], "hidden_fields": [], "reason": None},
    }, 60)
    env = await company_v2_debug_service.build_module("CN", "000001", "profitability")
    assert env.source_chain[0].provider == "cache"
    assert env.render.table_renderable is True


def test_frontend_company_v2_files_exist():
    from pathlib import Path

    root = Path(__file__).resolve().parents[3]
    assert (root / "frontend/src/views/CompanyV2View.vue").exists()
    assert (root / "frontend/src/components/company-v2/CompanyV2RawJsonDrawer.vue").exists()
    text = (root / "frontend/src/views/CompanyV2View.vue").read_text()
    assert "overflow" not in text.split("<template>")[1].split("</template>")[0]
