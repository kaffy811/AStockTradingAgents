from __future__ import annotations

import pytest


def test_baostock_profit_raw_maps_to_profitability_normalized():
    from app.services.company_v2_normalizers import normalize_baostock_aggregate

    rows = normalize_baostock_aggregate("profitability", {
        "profit": [{
            "stat_date": "2026-03-31",
            "pub_date": "2026-04-25",
            "roe_avg": 0.105,
            "net_margin": 0.52,
            "gross_margin": 0.89,
            "net_profit": 100,
            "eps_ttm": 2.1,
            "mb_revenue": 200,
            "total_share": 10,
            "liqa_share": 8,
        }]
    })
    assert rows[0]["roe"] == 0.105
    assert rows[0]["net_margin"] == 0.52
    assert rows[0]["gross_margin"] == 0.89
    assert rows[0]["source_field_map"]["roe"] == "roe_avg"


def test_baostock_growth_raw_maps_to_growth_normalized():
    from app.services.company_v2_normalizers import normalize_baostock_aggregate

    rows = normalize_baostock_aggregate("growth", {"growth": [{
        "YOYEquity": 1,
        "YOYAsset": 2,
        "YOYNI": 3,
        "YOYEPSBasic": 4,
        "YOYPNI": 5,
    }]})
    assert rows[0]["equity_yoy"] == 1
    assert rows[0]["net_profit_yoy"] == 3
    assert rows[0]["parent_net_profit_yoy"] == 5


def test_baostock_cashflow_raw_maps_to_cashflow_normalized():
    from app.services.company_v2_normalizers import normalize_baostock_aggregate

    rows = normalize_baostock_aggregate("cashflow_quality", {"cash_flow": [{
        "CFOToOR": 0.1,
        "CFOToNP": 0.2,
        "CFOToGr": 0.3,
    }]})
    assert rows[0]["ocf_to_revenue"] == 0.3
    assert rows[0]["ocf_to_np"] == 0.2
    assert rows[0]["cashflow_revenue_ratio"] == 0.1


def test_baostock_solvency_raw_maps_to_solvency_normalized():
    from app.services.company_v2_normalizers import normalize_baostock_aggregate

    rows = normalize_baostock_aggregate("solvency", {"balance": [{
        "currentRatio": 1.1,
        "quickRatio": 1.0,
        "cashRatio": 0.7,
        "liabilityToAsset": 0.4,
        "assetToEquity": 1.8,
    }]})
    assert rows[0]["current_ratio"] == 1.1
    assert rows[0]["debt_ratio"] == 0.4
    assert rows[0]["equity_multiplier"] == 1.8


def test_baostock_operation_raw_maps_to_operation_normalized():
    from app.services.company_v2_normalizers import normalize_baostock_aggregate

    rows = normalize_baostock_aggregate("operation_capability", {"operation": [{
        "NRTurnRatio": 2,
        "INVTurnRatio": 3,
        "AssetTurnRatio": 4,
    }]})
    assert rows[0]["receivable_turnover"] == 2
    assert rows[0]["inventory_turnover"] == 3
    assert rows[0]["total_asset_turnover"] == 4


def test_baostock_dupont_raw_maps_to_dupont_normalized():
    from app.services.company_v2_normalizers import normalize_baostock_aggregate

    rows = normalize_baostock_aggregate("dupont", {"dupont": [{
        "dupontROE": 0.1,
        "dupontAssetStoEquity": 2,
        "dupontAssetTurn": 3,
        "dupontPnitoni": 0.4,
        "dupontNitogr": 0.5,
    }]})
    assert rows[0]["roe"] == 0.1
    assert rows[0]["equity_multiplier"] == 2
    assert rows[0]["asset_turnover"] == 3
    assert rows[0]["dupont_net_profit_factor"] == 0.4
    assert rows[0]["dupont_income_margin"] == 0.5
    assert rows[0]["net_margin"] == 0.2


def test_mapping_error_when_raw_rows_but_no_normalized_rows():
    from app.services.company_v2_debug_diagnosis_service import diagnose_company_v2_envelope

    diagnosis = diagnose_company_v2_envelope({
        "module_key": "profitability",
        "source_chain": [{"provider": "baostock", "success": True, "rows_count": 6}],
        "normalized": {"rows": [], "fields": {}},
        "render": {"renderable": False},
    })
    assert diagnosis["primary_issue"] == "MAPPING_ERROR"
    assert diagnosis["raw_rows_count"] == 6


def test_normalized_valid_fields_renderable_table():
    from app.services.company_v2_debug_service import _fill_fields, _render

    fields, _, _ = _fill_fields("profitability", [{"roe": 0}], {})
    render = _render("profitability", [{"roe": 0}], fields)
    assert render.table_renderable is True
    assert render.has_displayable_data is True


@pytest.mark.asyncio
async def test_debug_full_calls_baostock_aggregate_once_and_reuses(monkeypatch):
    from app.services.company_v2_debug_service import company_v2_debug_service

    calls = {"aggregate": 0}

    async def fake_prepare(market, symbol, *, include_raw, force_refresh, max_raw_chars, context):
        calls["aggregate"] += 1
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
                "raw_sample": [],
            },
            "raw": {
                "profit": [{"roe_avg": 0.1, "gross_margin": 0.2, "net_margin": 0.3}],
                "growth": [{"YOYNI": 4}],
                "cash_flow": [{"CFOToNP": 5}],
                "balance": [{"currentRatio": 6}],
                "operation": [{"AssetTurnRatio": 7}],
                "dupont": [{"dupontROE": 8, "dupontAssetTurn": 9, "dupontAssetStoEquity": 10, "dupontPnitoni": 11}],
            },
            "cache_hit": False,
            "cache_stale": False,
            "cache_status": "ok",
            "aggregate_source_id": "unit",
        }

    monkeypatch.setattr(company_v2_debug_service, "_prepare_baostock_aggregate", fake_prepare)
    result = await company_v2_debug_service.build_full(
        "CN", "600519", include_raw=False, providers=["baostock"], force_refresh=True, max_raw_chars=1000, db=None
    )
    assert calls["aggregate"] == 1
    assert result["summary"]["provider_calls_count"]["baostock_aggregate"] == 1
    assert result["modules"]["profitability"]["render"]["table_renderable"] is True
    assert result["modules"]["dupont"]["source_chain"][0]["aggregate_source_id"] == "unit"


@pytest.mark.asyncio
async def test_snapshot_cache_hit_and_stale_timeout_diagnosis():
    from app.services.company_v2_debug_diagnosis_service import diagnose_company_v2_envelope
    from app.services.company_v2_snapshot_cache_service import company_v2_snapshot_cache_service

    key = company_v2_snapshot_cache_service.make_key("module", "600519.SH", "profitability", "unit")
    await company_v2_snapshot_cache_service.set(key, {"ok": True, "_stale": True}, ttl=60)
    cached, hit, stale, _ = await company_v2_snapshot_cache_service.get(key)
    assert hit is True
    assert stale is True
    assert cached["ok"] is True

    diagnosis = diagnose_company_v2_envelope({
        "module_key": "profitability",
        "stale": True,
        "source_chain": [{"provider": "baostock", "status": "timeout", "error_code": "PROVIDER_TIMEOUT"}],
        "normalized": {"rows": [], "fields": {}},
        "render": {"renderable": False},
    })
    assert diagnosis["primary_issue"] == "PROVIDER_TIMEOUT_WITH_STALE_CACHE"


@pytest.mark.asyncio
async def test_baostock_aggregate_timeout_uses_stale_snapshot(monkeypatch):
    from app.services.company_v2_debug_service import company_v2_debug_service
    from app.services.company_v2_snapshot_cache_service import company_v2_snapshot_cache_service
    import app.services.company_v2_debug_service as service_module

    key = company_v2_snapshot_cache_service.make_key(
        "provider", "600519.SH", "baostock", "get_all_financial_indicators", "n8"
    )
    await company_v2_snapshot_cache_service.set(key, {
        "result": {
            "provider": "baostock",
            "endpoint": "get_all_financial_indicators",
            "attempted": True,
            "success": True,
            "status": "success",
            "rows_count": 1,
        },
        "raw": {"profit": [{"roe_avg": 0.2}]},
        "_stale": True,
    }, ttl=60)

    async def timeout_runner(*args, **kwargs):
        return {
            "provider": "baostock",
            "endpoint": "get_all_financial_indicators",
            "attempted": True,
            "success": False,
            "status": "timeout",
            "error_code": "PROVIDER_TIMEOUT",
            "rows_count": 0,
        }

    monkeypatch.setattr(service_module, "run_provider_with_debug", timeout_runner)
    context = {"provider_calls_count": {}, "force_refresh": True}
    await company_v2_debug_service._prepare_baostock_aggregate(
        "CN", "600519", include_raw=False, force_refresh=True, max_raw_chars=1000, context=context
    )
    aggregate = context["baostock_aggregate"]
    assert aggregate["cache_stale"] is True
    assert aggregate["raw"]["profit"][0]["roe_avg"] == 0.2


@pytest.mark.asyncio
async def test_snapshot_cache_sanitizes_secret_and_local_path():
    from app.services.company_v2_snapshot_cache_service import company_v2_snapshot_cache_service

    key = company_v2_snapshot_cache_service.make_key("provider", "600519.SH", "unit-secret")
    await company_v2_snapshot_cache_service.set(key, {"token": "secret", "local_path": "/tmp/x.pdf", "value": 1}, ttl=60)
    cached, hit, _, _ = await company_v2_snapshot_cache_service.get(key)
    assert hit is True
    assert cached["token"] == "[redacted]"
    assert "local_path" not in cached


def test_frontend_company_v2_mapping_diagnosis_text():
    from pathlib import Path

    root = Path(__file__).resolve().parents[3]
    section = (root / "frontend/src/components/company-v2/CompanyV2Section.vue").read_text()
    panel = (root / "frontend/src/components/company-v2/CompanyV2DebugPanel.vue").read_text()
    assert "raw_rows_count" in section
    assert "原始数据已返回，但字段映射为空" in section
    assert "数据源超时，已展示缓存快照" in section
    assert "baostock_aggregate_calls" in panel
