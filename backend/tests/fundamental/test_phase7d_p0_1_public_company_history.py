from __future__ import annotations

import json

import pytest


@pytest.mark.asyncio
async def test_anonymous_history_is_public_and_safely_trimmed(monkeypatch):
    from app.routers import company_v2_debug as route
    from app.services import company_v2_history_service

    async def fake_dashboard(*args, **kwargs):
        assert kwargs["force_refresh"] is False
        return {
            "period": "annual", "start_year": 2023, "end_year": 2024,
            "generated_at": "2025-04-30", "history_range_label": "2023–2024",
            "modules": {"profitability": {
                "history": [{"period": "2024-12-31", "roe": 0.12, "raw_payload": "hidden", "provider": "hidden"}],
                "latest": {"period": "2024-12-31", "roe": 0.12, "trace_id": "hidden"},
                "data_success": True, "provider": "public-source", "completeness_status": "complete",
                "history_coverage": {"periods_count": 1, "debug_count": 99},
            }},
            "performance_summary": {"calls_by_endpoint": {"secret": 1}},
        }

    monkeypatch.setattr(company_v2_history_service, "build_company_history_dashboard", fake_dashboard)
    response = await route.get_company_history("CN", "000725", "annual", None, None, True, None)
    body = json.loads(response.body)
    assert response.status_code == 200
    assert body["ok"] is True
    assert body["symbol"] == "000725"
    assert body["source"] == ["public_company_financials"]
    assert body["as_of"] == "2025-04-30"
    assert body["modules"]["profitability"]["field_availability"]["roe"] is True
    serialized = response.body.decode()
    for forbidden in ("AUTH_REQUIRED", "raw_payload", "trace_id", "performance_summary", "calls_by_endpoint"):
        assert forbidden not in serialized


@pytest.mark.asyncio
async def test_anonymous_history_empty_is_explicitly_unavailable(monkeypatch):
    from app.routers import company_v2_debug as route
    from app.services import company_v2_history_service

    async def fake_dashboard(*args, **kwargs):
        return {"period": "annual", "generated_at": "2025-04-30", "modules": {}}

    monkeypatch.setattr(company_v2_history_service, "build_company_history_dashboard", fake_dashboard)
    response = await route.get_company_history("CN", "000725", "annual", None, None, False, None)
    body = json.loads(response.body)
    assert response.status_code == 200
    assert body["ok"] is False
    assert body["reason_code"] == "DATA_NOT_AVAILABLE"
    assert body["field_availability"] == {}


def test_public_history_record_uses_positive_allowlist_and_denies_unknown_values():
    from app.routers.company_v2_debug import _public_financial_record

    row = {
        "period": "2024-12-31",
        "roe": 0.12,
        "gross_margin": None,
        "api_key": "placeholder",
        "token": "placeholder",
        "secret": "placeholder",
        "password": "placeholder",
        "debug_detail": "placeholder",
        "trace": "placeholder",
        "raw_payload": "placeholder",
        "unknown_string": "placeholder",
        "unknown_number": 42,
        "unknown_boolean": True,
        "unknown_none": None,
        "unknown_dict": {"value": "placeholder"},
        "unknown_list": ["placeholder"],
    }

    assert _public_financial_record(row, "profitability") == {
        "period": "2024-12-31",
        "roe": 0.12,
        "gross_margin": None,
    }


def test_public_history_warning_uses_local_message_and_public_field_only():
    from app.routers.company_v2_debug import _public_financial_record

    hostile_message = "RuntimeError https://provider.invalid/private /srv/app token=placeholder raw body"
    row = {
        "period": "2024-12-31",
        "roe": 0.12,
        "warnings": [
            {
                "code": "OUTLIER_REQUIRES_REVIEW",
                "message": hostile_message,
                "field": "roe",
                "outlier_status": "extreme",
                "provider_body": "placeholder",
            },
            {"code": "UNKNOWN_PROVIDER_ERROR", "message": hostile_message, "field": "roe"},
            {"code": "FIELD_CONFLICT", "message": hostile_message, "field": "api_key"},
        ],
    }

    public = _public_financial_record(row, "profitability")
    serialized = json.dumps(public, ensure_ascii=False)
    assert public["warnings"] == [
        {
            "code": "OUTLIER_REQUIRES_REVIEW",
            "message": "部分历史指标超出常见范围，需核对披露口径。",
            "field": "roe",
            "outlier_status": "extreme",
        },
        {
            "code": "FIELD_CONFLICT",
            "message": "不同公开来源的指标口径存在差异。",
        },
    ]
    for forbidden in ("provider.invalid", "RuntimeError", "/srv/app", "token=", "raw body", "api_key"):
        assert forbidden not in serialized


@pytest.mark.asyncio
async def test_public_profile_error_is_fixed_and_does_not_expose_exception(monkeypatch):
    from app.routers import company_v2_debug as route
    from app.services import company_v2_stock_basic_service

    detail = "RuntimeError provider body at /srv/private token=placeholder"

    async def fail_profile(*args, **kwargs):
        raise RuntimeError(detail)

    monkeypatch.setattr(company_v2_stock_basic_service, "get_stock_basic", fail_profile)
    response = await route.get_company_profile("CN", "000725", None)
    body = json.loads(response.body)
    assert response.status_code == 200
    assert body == {
        "ok": False,
        "error_code": "PUBLIC_PROFILE_UNAVAILABLE",
        "message": "公司资料暂不可用，请稍后重试。",
    }
    assert detail not in response.body.decode()
