from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.agents import chat_orchestrator
from app.services.security_entity_resolver import SecurityEntityResolver


FIXTURE = Path(__file__).parent / "fixtures" / "phase7e_p1_6_tushare_000725_eod.json"
MOUTAI_FIXTURE = Path(__file__).parent / "fixtures" / "phase7e_p0_1_tushare_600519_eod.json"


def _snapshot() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _snapshot_for(symbol: str) -> dict:
    if symbol == "000725":
        return _snapshot()
    snapshot = json.loads(MOUTAI_FIXTURE.read_text(encoding="utf-8"))
    snapshot["modules"]["profile"] = {
        "status": "fulfilled",
        "source": "tushare",
        "as_of": "2001-08-27",
        "fields": {
            "name": {"value": "贵州茅台", "unit": None, "as_of": "2001-08-27", "source": "tushare"},
            "fullname": {"value": "贵州茅台酒股份有限公司", "unit": None, "as_of": "2001-08-27", "source": "tushare"},
            "industry": {"value": "白酒", "unit": None, "as_of": "2001-08-27", "source": "tushare"},
            "exchange": {"value": "SSE", "unit": None, "as_of": "2001-08-27", "source": "tushare"},
        },
    }
    return snapshot


def _entity(symbol: str, *, name: str | None = None) -> SimpleNamespace:
    suffix = "SZ" if symbol.startswith(("0", "2", "3")) else "SH"
    exchange = "SZSE" if suffix == "SZ" else "SSE"
    return SimpleNamespace(
        market="CN",
        symbol=symbol,
        ts_code=f"{symbol}.{suffix}",
        exchange=exchange,
        short_name=name or ("京东方A" if symbol == "000725" else "贵州茅台"),
        full_name="",
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("query", "expected_symbol", "expected_ts_code"),
    [
        ("CN/000725 公司资料 + EOD", "000725", "000725.SZ"),
        ("000725 公司资料 + EOD", "000725", "000725.SZ"),
        ("000725.SZ 收盘价", "000725", "000725.SZ"),
        ("600519 财务指标", "600519", "600519.SH"),
        ("600519.SH 估值", "600519", "600519.SH"),
        ("贵州茅台近期情况", "600519", "600519.SH"),
    ],
)
async def test_resolver_normalizes_supported_current_turn_identifiers(
    query, expected_symbol, expected_ts_code
):
    resolver = SecurityEntityResolver(sample_rows=[
        {"market": "CN", "symbol": "000725", "exchange": "SZSE", "short_name": "京东方A"},
        {"market": "CN", "symbol": "600519", "exchange": "SSE", "short_name": "贵州茅台"},
    ])

    result = await resolver.resolve(None, query, market_hint="CN", min_confidence=0.72)

    assert result["ambiguity"] is False
    assert len(result["entities"]) == 1
    assert result["entities"][0].symbol == expected_symbol
    assert result["entities"][0].ts_code == expected_ts_code


@pytest.mark.asyncio
@pytest.mark.parametrize("query", ["000725.SH 收盘价", "600519.SZ 估值"])
async def test_resolver_rejects_exchange_suffix_mismatch(query):
    resolver = SecurityEntityResolver(sample_rows=[
        {"market": "CN", "symbol": "000725", "exchange": "SZSE", "short_name": "京东方A"},
        {"market": "CN", "symbol": "600519", "exchange": "SSE", "short_name": "贵州茅台"},
    ])

    result = await resolver.resolve(None, query, market_hint="CN", min_confidence=0.72)

    assert result["entities"] == []
    assert result["ambiguity"] is False


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("query", "symbol", "ts_code"),
    [
        ("CN/000725 公司资料 + EOD", "000725", "000725.SZ"),
        ("000725 公司资料 + EOD", "000725", "000725.SZ"),
        ("000725.SZ 收盘价和估值", "000725", "000725.SZ"),
        ("600519 财务指标、ROE、估值", "600519", "600519.SH"),
        ("600519.SH 近期情况", "600519", "600519.SH"),
        ("贵州茅台近期情况", "600519", "600519.SH"),
    ],
)
async def test_explicit_identifier_and_company_name_route_directly_to_eod(
    monkeypatch, query, symbol, ts_code
):
    snapshot = _snapshot_for(symbol)
    resolver = AsyncMock(return_value={"entities": [_entity(symbol)], "ambiguity": False})
    gateway = AsyncMock(return_value=snapshot)
    forbidden = AsyncMock(side_effect=AssertionError("memory, skill, LLM or general tool path must not run"))
    monkeypatch.setattr(chat_orchestrator.security_entity_resolver, "resolve", resolver)
    monkeypatch.setattr(chat_orchestrator.tushare_eod_gateway, "get_company_snapshot", gateway)
    monkeypatch.setattr(chat_orchestrator._registry, "call", forbidden)

    result = await chat_orchestrator.process_message(query, None, uuid4(), session_id=uuid4())

    assert result.metadata["route"] == "stock_eod_research"
    assert result.metadata["fulfillment"] == "fulfilled"
    assert result.metadata["symbol"] == symbol
    assert result.metadata["ts_code"] == ts_code
    assert result.metadata["report_period"] == "2026-06-30"
    assert result.metadata["source"] == ["tushare"]
    assert result.metadata["as_of"] == "2026-09-09"
    assert result.metadata["numeric_validation"]["valid"] is True
    assert result.metadata["numeric_validation"]["unsupported_tokens"] == []
    assert "不是实时行情" in result.answer
    assert "## 公司资料" in result.answer
    expected_profile_name = "京东方科技集团股份有限公司" if symbol == "000725" else "贵州茅台酒股份有限公司"
    assert expected_profile_name in result.answer
    gateway.assert_awaited_once_with("CN", symbol)
    forbidden.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("previous_symbol", "query", "expected_symbol"),
    [
        ("600519", "CN/000725 公司资料 + EOD", "000725"),
        ("000725", "600519.SH 近期情况", "600519"),
    ],
)
async def test_current_turn_explicit_symbol_outranks_cross_turn_memory(
    monkeypatch, previous_symbol, query, expected_symbol
):
    snapshot = _snapshot_for(expected_symbol)
    current_entity = _entity(expected_symbol)
    resolver = AsyncMock(return_value={"entities": [current_entity], "ambiguity": False})
    gateway = AsyncMock(return_value=snapshot)
    memory = AsyncMock(side_effect=AssertionError(f"must not reuse previous symbol {previous_symbol}"))
    monkeypatch.setattr(chat_orchestrator.security_entity_resolver, "resolve", resolver)
    monkeypatch.setattr(chat_orchestrator.tushare_eod_gateway, "get_company_snapshot", gateway)
    monkeypatch.setattr("app.services.conversation_memory_service.build_memory_context", memory)

    result = await chat_orchestrator.process_message(query, None, uuid4(), session_id=uuid4())

    assert result.metadata["symbol"] == expected_symbol
    assert result.metadata["ts_code"] == current_entity.ts_code
    memory.assert_not_awaited()
    gateway.assert_awaited_once_with("CN", expected_symbol)


@pytest.mark.asyncio
async def test_different_sessions_and_no_session_do_not_inject_a_previous_symbol(monkeypatch):
    resolver = AsyncMock(return_value={"entities": [_entity("000725")], "ambiguity": False})
    gateway = AsyncMock(return_value=_snapshot())
    monkeypatch.setattr(chat_orchestrator.security_entity_resolver, "resolve", resolver)
    monkeypatch.setattr(chat_orchestrator.tushare_eod_gateway, "get_company_snapshot", gateway)

    first = await chat_orchestrator.process_message(
        "CN/000725 公司资料 + EOD", None, uuid4(), session_id=uuid4()
    )
    second = await chat_orchestrator.process_message(
        "CN/000725 公司资料 + EOD", None, uuid4(), session_id=uuid4()
    )
    no_history = await chat_orchestrator.process_message(
        "CN/000725 公司资料 + EOD", None, uuid4(), session_id=None
    )

    assert {first.metadata["symbol"], second.metadata["symbol"], no_history.metadata["symbol"]} == {"000725"}
    assert gateway.await_count == 3


@pytest.mark.asyncio
async def test_unknown_six_digit_candidate_fails_closed_without_gateway_skill_or_llm(monkeypatch):
    resolver = AsyncMock(return_value={"entities": [], "ambiguity": False})
    gateway = AsyncMock(side_effect=AssertionError("unknown security must not call EOD provider"))
    general = AsyncMock(side_effect=AssertionError("unknown security must not reach a general skill"))
    monkeypatch.setattr(chat_orchestrator.security_entity_resolver, "resolve", resolver)
    monkeypatch.setattr(chat_orchestrator.tushare_eod_gateway, "get_company_snapshot", gateway)
    monkeypatch.setattr(chat_orchestrator._registry, "call", general)

    result = await chat_orchestrator.process_message("123456 公司资料 + EOD", None, uuid4())

    assert result.metadata == {
        "route": "stock_eod_research",
        "fulfillment": "unavailable",
        "reason_code": "COMPANY_NOT_RESOLVED",
    }
    gateway.assert_not_awaited()
    general.assert_not_awaited()


@pytest.mark.asyncio
async def test_official_report_request_keeps_cninfo_priority(monkeypatch):
    official_result = chat_orchestrator.OrchestratorResult(
        answer="official", metadata={"route": "official_company_events", "fulfillment": "partial"}
    )
    official = AsyncMock(return_value=official_result)
    eod = AsyncMock(side_effect=AssertionError("official report query must not enter EOD"))
    monkeypatch.setattr(chat_orchestrator, "_handle_official_company_research", official)
    monkeypatch.setattr(chat_orchestrator, "_handle_stock_eod_research", eod)

    result = await chat_orchestrator.process_message("CN/000725 官方公告和历史报告", None, uuid4())

    assert result.metadata["route"] == "official_company_events"
    official.assert_awaited_once()
    eod.assert_not_awaited()


@pytest.mark.asyncio
async def test_exact_theme_query_remains_fail_closed_with_zero_downstream_calls(monkeypatch):
    forbidden = AsyncMock(side_effect=AssertionError("LLM and providers must remain at zero"))
    monkeypatch.setattr(chat_orchestrator.security_entity_resolver, "resolve", forbidden)
    monkeypatch.setattr(chat_orchestrator.tushare_eod_gateway, "get_company_snapshot", forbidden)
    monkeypatch.setattr(chat_orchestrator._registry, "call", forbidden)

    result = await chat_orchestrator.process_message("AI 半导体设备主题问题", None, uuid4())

    assert result.metadata["fulfillment"] == "unavailable"
    assert result.metadata["reason_code"] == "NO_APPROVED_INDUSTRY_NEWS_SOURCE"
    assert result.metadata["scope"] == "unapproved_industry_theme_research"
    forbidden.assert_not_awaited()
