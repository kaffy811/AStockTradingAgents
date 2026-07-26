from __future__ import annotations

import json
from pathlib import Path

import pytest


FORBIDDEN_LEGACY_MESSAGE = "DATA_MODE=free：BaoStock 和 AkShare 均未返回数据，请检查 ENABLE_BAOSTOCK / ENABLE_AKSHARE 配置。"


@pytest.fixture
def fake_company_v2_builders(monkeypatch):
    from app.services.company_v2_debug_service import company_v2_debug_service

    async def fake_prepare(market, symbol, *, include_raw, force_refresh, max_raw_chars, context):
        context.setdefault("provider_calls_count", {})["baostock_aggregate"] = 1
        context["baostock_aggregate"] = {
            "result": {
                "provider": "baostock",
                "endpoint": "get_all_financial_indicators",
                "attempted": True,
                "success": True,
                "status": "success",
                "rows_count": 1,
                "columns": ["profit", "growth", "cash_flow", "balance", "operation", "dupont"],
                "raw_sample": [{"profit": [{"roe_avg": 0, "gross_margin": 0.5, "net_margin": None}]}],
            },
            "raw": {
                "profit": [{"roe_avg": 0, "gross_margin": 0.5, "net_margin": None}],
                "growth": [{"YOYEquity": 1, "YOYNI": 2, "YOYEPSBasic": 3}],
                "cash_flow": [{"CFOToOR": 0.1, "CFOToNP": 0.2, "CFOToGr": 0.3}],
                "balance": [{"currentRatio": 1.1, "quickRatio": 1.0, "cashRatio": 0.8, "liabilityToAsset": 0.4, "assetToEquity": 1.7}],
                "operation": [{"NRTurnRatio": 2, "INVTurnRatio": 3, "AssetTurnRatio": 4}],
                "dupont": [{"dupontROE": 0.1, "dupontPnitoni": 0.2, "dupontAssetTurn": 0.3, "dupontAssetStoEquity": 1.4}],
            },
            "cache_hit": False,
            "cache_stale": False,
            "cache_status": "ok",
            "aggregate_source_id": "baostock:get_all_financial_indicators:600519.SH",
        }

    async def fake_quote(env, providers, include_raw, max_raw_chars, *, context=None):
        from app.schemas.company_v2_debug import CompanyV2SourceAttempt

        quote_entry = (context or {}).get("quote_overview")
        if env.module_key == "valuation" and isinstance(quote_entry, dict):
            env.source_chain = quote_entry["source_chain"]
            env.raw = quote_entry["raw"]
            env.normalized.rows = quote_entry["rows"]
            env.normalized.metrics = env.normalized.rows[0]
            return
        env.source_chain.append(CompanyV2SourceAttempt(
            provider="baostock",
            endpoint="query_history_k_data_plus",
            attempted=True,
            success=True,
            rows_count=1,
        ))
        env.raw["baostock"] = [{
            "endpoint": "query_history_k_data_plus",
            "rows_count": 1,
            "raw_sample": [{"close": 10, "pe_ttm": 12, "pb": 1.3}],
        }]
        env.normalized.rows = [{
            "latest_price": 10,
            "recent_close": 10,
            "pe_ttm": 12,
            "pb": 1.3,
        }]
        env.normalized.metrics = env.normalized.rows[0]
        if context is not None and env.module_key == "quote_overview":
            context["quote_overview"] = {"rows": env.normalized.rows, "raw": env.raw, "source_chain": env.source_chain}

    async def fake_report(env, *, db, include_raw, max_raw_chars, force_refresh):
        from app.schemas.company_v2_debug import CompanyV2SourceAttempt

        env.source_chain.append(CompanyV2SourceAttempt(
            provider="pdf_metrics",
            endpoint="unit",
            attempted=True,
            success=True,
            rows_count=1,
        ))
        row = {"documents_count": 1, "chunks_count": 1, "embedding_count": 1}
        env.normalized.rows = [row]
        env.normalized.metrics = row

    monkeypatch.setattr(company_v2_debug_service, "_prepare_baostock_aggregate", fake_prepare)
    monkeypatch.setattr(company_v2_debug_service, "_build_quote", fake_quote)
    monkeypatch.setattr(company_v2_debug_service, "_build_report_module", fake_report)
    company_v2_debug_service._memory_cache.clear()
    return company_v2_debug_service


@pytest.mark.asyncio
async def test_v2_debug_full_gate_payload_and_cache(fake_company_v2_builders):
    service = fake_company_v2_builders

    first = await service.build_full(
        "CN",
        "600519",
        include_raw=False,
        providers=["baostock"],
        force_refresh=True,
        max_raw_chars=1000,
        db=None,
    )
    payload = json.dumps(first, ensure_ascii=False)
    assert first["summary"]["modules_renderable"] >= 10
    assert first["summary"]["provider_calls_count"]["baostock_aggregate"] == 1
    assert first["summary"]["baostock_aggregate_calls"] == 1
    assert first["summary"]["providers_timeout"] == 0
    assert "raw_full" not in payload
    assert FORBIDDEN_LEGACY_MESSAGE not in payload
    assert "local_path" not in payload
    assert '"token"' not in payload
    assert first["modules"]["profitability"]["source_chain"][0]["aggregate_source_id"].startswith("baostock:")
    assert first["modules"]["profitability"]["normalized"]["rows"][0]["roe"] == 0
    assert first["modules"]["profitability"]["normalized"]["rows"][0].get("net_margin") is None

    second = await service.build_full(
        "CN",
        "600519",
        include_raw=False,
        providers=["baostock"],
        force_refresh=False,
        max_raw_chars=1000,
        db=None,
    )
    assert second["summary"]["cache_hit"] is True
    assert second["cache_hit"] is True


def test_company_v2_frontend_replacement_gate_source():
    root = Path(__file__).resolve().parents[3]
    stock_detail = (root / "frontend/src/views/StockDetailView.vue").read_text()
    company_v2 = (root / "frontend/src/views/CompanyV2View.vue").read_text()
    debug_panel = (root / "frontend/src/components/company-v2/CompanyV2DebugPanel.vue").read_text()

    assert "VITE_COMPANY_TAB_VERSION" in stock_detail
    assert "companyV2Query.value !== '0'" in stock_detail
    assert "company_v2 === '1'" not in stock_detail
    assert "data-testid=\"company-v2-bottom-sentinel\"" in company_v2
    assert "height: 100vh" not in company_v2
    assert "overflow: hidden" not in company_v2
    assert FORBIDDEN_LEGACY_MESSAGE not in company_v2
    assert FORBIDDEN_LEGACY_MESSAGE not in debug_panel
    assert "已展示当前可用的公开数据" in debug_panel


@pytest.mark.asyncio
async def test_baostock_module_without_full_context_uses_new_normalizer(monkeypatch):
    import app.services.company_v2_debug_service as service_module
    from app.services.company_v2_debug_service import company_v2_debug_service

    async def fake_runner(*args, **kwargs):
        return {
            "provider": "baostock",
            "endpoint": "get_all_financial_indicators",
            "attempted": True,
            "success": True,
            "status": "success",
            "rows_count": 1,
            "raw_sample": [{"profit": [{"roe_avg": 0.12, "gross_margin": 0.56, "net_margin": 0.23}]}],
            "columns": ["profit"],
        }

    monkeypatch.setattr(service_module, "run_provider_with_debug", fake_runner)
    env = await company_v2_debug_service.build_module(
        "CN",
        "600519",
        "profitability",
        include_raw=False,
        providers=["baostock"],
        force_refresh=True,
        max_raw_chars=1000,
        db=None,
    )
    assert env.render.table_renderable is True
    assert env.normalized.rows[0]["roe"] == 0.12
    assert env.source_chain[0].aggregate_source_id == "baostock:get_all_financial_indicators:600519.SH"


@pytest.mark.asyncio
async def test_valuation_reuses_quote_context_without_provider_calls():
    from app.schemas.company_v2_debug import CompanyV2SourceAttempt
    from app.services.company_v2_debug_service import company_v2_debug_service
    from app.services.company_v2_debug_service import CompanyV2DebugEnvelope

    env = CompanyV2DebugEnvelope(
        request_id="rid",
        market="CN",
        symbol="600519",
        ts_code="600519.SH",
        module_key="valuation",
        data_mode="free",
    )
    context = {
        "quote_overview": {
            "rows": [{"latest_price": 10, "pe_ttm": 11, "pb": 1.2}],
            "raw": {"baostock": [{"rows_count": 1}]},
            "source_chain": [CompanyV2SourceAttempt(provider="baostock", endpoint="query_history_k_data_plus", success=True, rows_count=1)],
        }
    }
    await company_v2_debug_service._build_quote(
        env,
        ["baostock"],
        include_raw=False,
        max_raw_chars=1000,
        context=context,
    )
    assert env.normalized.rows[0]["pe_ttm"] == 11
    assert env.source_chain[0].cache_hit is True
