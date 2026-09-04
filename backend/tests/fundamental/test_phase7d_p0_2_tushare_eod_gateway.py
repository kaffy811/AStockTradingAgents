from __future__ import annotations

import asyncio
import json
import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pandas as pd
import pytest

from app.datasource.tushare_client import TushareAuthError
from app.services.tushare_eod_gateway import TushareEodGateway, _safe_failure


class FakeClient:
    def __init__(self, failures=None):
        self.failures = failures or {}
        self.calls = []

    async def _result(self, endpoint, frame):
        self.calls.append(endpoint)
        if endpoint in self.failures:
            raise self.failures[endpoint]
        return frame

    async def get_stock_basic(self, **kwargs):
        return await self._result("stock_basic", pd.DataFrame([{
            "ts_code": "000725.SZ", "name": "京东方A", "fullname": "京东方科技集团股份有限公司",
            "exchange": "SZSE", "industry": "元器件", "list_date": "20010112", "list_status": "L",
        }]))

    async def get_daily(self, ts_code):
        return await self._result("daily", pd.DataFrame([{
            "trade_date": "20260831", "close": 4.21, "change": 0.03, "pct_chg": 0.72,
            "vol": 1234.0, "amount": 5678.0,
        }]))

    async def get_daily_basic(self, ts_code):
        return await self._result("daily_basic", pd.DataFrame([{
            "trade_date": "20260831", "pe_ttm": 21.3, "pb": 1.2, "turnover_rate": 0.8,
            "total_mv": 15000000.0,
        }]))

    async def get_fina_indicator(self, ts_code):
        return await self._result("fina_indicator", pd.DataFrame([{
            "end_date": "20260630", "roe": 4.5, "grossprofit_margin": 18.2,
        }]))

    async def get_index_daily(self, ts_code):
        return await self._result("index_daily", pd.DataFrame([{"trade_date": "20260831", "close": 3200.0}]))


@pytest.fixture(autouse=True)
def no_cache_write(monkeypatch):
    from app.services import tushare_eod_gateway as module
    monkeypatch.setattr(module.company_v2_snapshot_cache_service, "set_swr", AsyncMock())


@pytest.mark.asyncio
async def test_all_approved_eod_endpoints_normalize_grounded_facts():
    client = FakeClient()
    result = await TushareEodGateway(client).get_company_snapshot("CN", "000725", use_cache=False)
    assert result["fulfillment"] == "fulfilled"
    assert client.calls == ["stock_basic", "daily", "daily_basic", "fina_indicator"]
    assert "index_daily" not in client.calls
    assert result["modules"]["quote"]["fields"]["close"] == {
        "value": 4.21, "unit": "CNY", "as_of": "2026-08-31", "source": "tushare",
        "source_status": "verified", "freshness": "latest_available_eod",
        "field_availability": "available", "reason_code": None,
    }
    assert result["modules"]["financial"]["fields"]["roe"]["as_of"] == "2026-06-30"
    assert result["fallback_providers_used"] == []


@pytest.mark.asyncio
@pytest.mark.parametrize("endpoint", ["stock_basic", "daily", "daily_basic", "fina_indicator"])
async def test_each_endpoint_failure_is_isolated(endpoint):
    client = FakeClient({endpoint: ConnectionError("connection unavailable")})
    result = await TushareEodGateway(client).get_company_snapshot("CN", "000725", use_cache=False)
    failed_module = {"stock_basic": "profile", "daily": "quote", "daily_basic": "valuation", "fina_indicator": "financial"}[endpoint]
    assert result["fulfillment"] == "partial"
    assert result["modules"][failed_module]["reason_code"] == "PROVIDER_NETWORK_ERROR"
    assert sum(module["status"] == "fulfilled" for module in result["modules"].values()) == 3


@pytest.mark.asyncio
@pytest.mark.parametrize("endpoint", ["stock_basic", "daily", "daily_basic", "fina_indicator"])
@pytest.mark.parametrize("exc,reason", [
    (TushareAuthError("40203 权限不足"), "PROVIDER_PERMISSION_DENIED"),
    (KeyError("missing required date field"), "PROVIDER_SCHEMA_ERROR"),
    (ValueError("empty result"), "DATA_NOT_AVAILABLE"),
])
async def test_each_endpoint_permission_schema_and_empty_result(endpoint, exc, reason):
    client = FakeClient({endpoint: exc})
    result = await TushareEodGateway(client).get_company_snapshot("CN", "000725", use_cache=False)
    failed_module = {"stock_basic": "profile", "daily": "quote", "daily_basic": "valuation", "fina_indicator": "financial"}[endpoint]
    assert result["modules"][failed_module]["reason_code"] == reason
    assert result["fulfillment"] == "partial"


@pytest.mark.parametrize("exc,category,reason", [
    (TushareAuthError("40203 权限不足"), "permission", "PROVIDER_PERMISSION_DENIED"),
    (TushareAuthError("token 无效"), "credential", "PROVIDER_CREDENTIAL_ERROR"),
    (asyncio.TimeoutError(), "network", "PROVIDER_NETWORK_ERROR"),
    (RuntimeError("HTTP status 503"), "http", "PROVIDER_HTTP_ERROR"),
    (KeyError("missing required date field"), "schema", "PROVIDER_SCHEMA_ERROR"),
    (ValueError("empty result"), "empty_result", "DATA_NOT_AVAILABLE"),
])
def test_failure_taxonomy_is_safe(exc, category, reason):
    result = _safe_failure("daily", exc)
    assert result["source_status"] == category
    assert result["reason_code"] == reason
    assert "message" not in result


@pytest.mark.asyncio
async def test_explicit_index_mapping_is_required_before_index_call():
    client = FakeClient()
    await TushareEodGateway(client).get_company_snapshot("CN", "000725", index_ts_code="000001.SH", use_cache=False)
    assert client.calls[-1] == "index_daily"


def test_client_initialization_log_never_contains_token_prefix(caplog, monkeypatch):
    import sys
    from app.datasource.tushare_client import TushareClient

    secret = "sensitive-token-value-that-must-never-appear"
    fake_sdk = SimpleNamespace(set_token=lambda value: None, pro_api=lambda: object())
    monkeypatch.setitem(sys.modules, "tushare", fake_sdk)
    caplog.set_level(logging.INFO)
    TushareClient()._ensure_initialized(secret, 500, 15.0)
    assert secret not in caplog.text
    assert secret[:6] not in caplog.text


@pytest.mark.asyncio
async def test_public_company_eod_route_has_no_auth_or_raw_payload(monkeypatch):
    from app.routers import company_v2_debug as route
    from app.services import tushare_eod_gateway as module

    payload = await TushareEodGateway(FakeClient()).get_company_snapshot("CN", "000725", use_cache=False)
    payload["provider_debug"] = "must-not-be-public"
    payload["modules"]["quote"]["provider_message"] = "private provider body"
    payload["modules"]["quote"]["fields"]["raw_code"] = {
        "value": "private", "source": "tushare", "as_of": "2026-08-31",
    }
    monkeypatch.setattr(module.tushare_eod_gateway, "get_company_snapshot", AsyncMock(return_value=payload))
    response = await route.get_company_eod("CN", "000725")
    body = json.loads(response.body)
    assert response.status_code == 200
    assert body["modules"]["quote"]["status"] == "fulfilled"
    serialized = response.body.decode().lower()
    for module in body["modules"].values():
        assert "endpoint" not in module
    for forbidden in (
        "auth_required", "eastmoney", "akshare", "raw_payload", "trace_id", "token",
        "provider_debug", "provider_message", "private provider body", "raw_code",
    ):
        assert forbidden not in serialized


@pytest.mark.asyncio
async def test_stock_eod_research_resolves_600519_and_never_claims_realtime(monkeypatch):
    from app.agents import chat_orchestrator as orchestrator

    entity = SimpleNamespace(market="CN", symbol="600519", short_name="贵州茅台", full_name="贵州茅台股份有限公司")
    monkeypatch.setattr(orchestrator.security_entity_resolver, "resolve", AsyncMock(return_value={"entities": [entity], "ambiguity": False}))
    snapshot = await TushareEodGateway(FakeClient()).get_company_snapshot("CN", "000725", use_cache=False)
    snapshot["symbol"] = "600519"
    monkeypatch.setattr(orchestrator.tushare_eod_gateway, "get_company_snapshot", AsyncMock(return_value=snapshot))
    monkeypatch.setattr(orchestrator.official_company_event_service, "list_persisted_events", AsyncMock(return_value={
        "fulfillment": "unavailable", "reason_code": "NO_PERSISTED_CNINFO_EVENTS", "events": [], "as_of": None,
    }))

    result = await orchestrator.process_message("贵州茅台近期情况呢？", None, uuid4())
    assert result.metadata["route"] == "stock_eod_research"
    assert result.metadata["symbol"] == "600519"
    assert "最近交易日收盘" in result.answer
    assert "不是实时行情" in result.answer
    assert "实时价格" not in result.answer
    assert "Eastmoney" not in result.answer


@pytest.mark.asyncio
async def test_industry_news_stays_fail_closed_before_eod_gateway(monkeypatch):
    from app.agents import chat_orchestrator as orchestrator

    gateway = AsyncMock()
    monkeypatch.setattr(orchestrator.tushare_eod_gateway, "get_company_snapshot", gateway)
    result = await orchestrator.process_message("AI 热潮带动哪些半导体设备公司？", None, uuid4())
    assert result.metadata["fulfillment"] == "unavailable"
    assert result.metadata["reason_code"] == "NO_APPROVED_INDUSTRY_NEWS_SOURCE"
    gateway.assert_not_awaited()
