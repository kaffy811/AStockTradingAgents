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
    assert body["source"] == ["public-source"]
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
