from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.services.stock_eod_numeric_validation import (
    claim_from_evidence,
    make_request_local_evidence,
    validate_stock_eod_numeric_claims,
)


def _evidence(module="quote", metric="close", value=1688.25, unit="CNY", as_of="2026-08-31", **kwargs):
    fact = {"value": value, "unit": unit, "as_of": as_of, "source": kwargs.pop("source", "tushare")}
    return make_request_local_evidence(module=module, metric=metric, fact=fact, **kwargs)


def _validate(answer, evidence):
    evidence = [item for item in evidence if item is not None]
    return validate_stock_eod_numeric_claims(
        answer, evidence, [claim_from_evidence(item) for item in evidence],
        symbol="600519", allowed_metadata_dates=["2026-08-31", "2026-06-30"],
    )


def test_close_pe_pb_roe_and_report_period_are_valid_request_local_facts():
    evidence = [
        _evidence(metric="close"),
        _evidence(module="valuation", metric="pe_ttm", value=24.3, unit="multiple"),
        _evidence(module="valuation", metric="pb", value=7.12, unit="multiple"),
        _evidence(module="financial", metric="roe", value=19.7, unit="%", as_of="2026-06-30"),
    ]
    answer = "600519 最近交易日 2026-08-31：1688.25CNY，PE 24.3multiple，PB 7.12multiple；ROE 19.7%，报告期 2026-06-30。"
    result = _validate(answer, evidence)
    assert result["valid"] is True
    assert result["unsupported_tokens"] == []
    assert len(result["checked_claims"]) == 4
    assert all(item["request_local_evidence_id"].startswith("stock-eod:") for item in result["evidence_basis"])


def test_explicit_rounding_percentage_and_cny_100m_conversion_are_valid():
    evidence = [
        _evidence(metric="pct_chg", value=3.456, unit="%", decimal_places=2),
        _evidence(module="valuation", metric="total_mv", value=1234567, unit="CNY_10k", display_unit="CNY_100M", decimal_places=2),
    ]
    result = _validate("涨跌幅 3.46%，总市值 123.46亿元，数据日期 2026-08-31。", evidence)
    assert result["valid"] is True
    assert evidence[0]["format_rule"]["rounding"] == "ROUND_HALF_UP"
    assert evidence[1]["format_rule"]["conversion"] == "CNY_10k_to_CNY_100M"


def test_fabricated_number_is_rejected():
    evidence = [_evidence()]
    result = _validate("收盘价 1688.25CNY，预测目标价 2000CNY。", evidence)
    assert result["valid"] is False
    assert "2000" in result["unsupported_tokens"]


def test_stale_report_period_wrong_unit_and_missing_source_are_rejected():
    financial = _evidence(module="financial", metric="roe", value=19.7, unit="%", as_of="2026-06-30")
    stale_claim = claim_from_evidence(financial)
    stale_claim["report_period"] = "2025-12-31"
    wrong_unit = claim_from_evidence(financial)
    wrong_unit["unit"] = "multiple"
    for claim in (stale_claim, wrong_unit):
        result = validate_stock_eod_numeric_claims(
            "600519 ROE 19.7%，报告期 2026-06-30。", [financial], [claim],
            symbol="600519", allowed_metadata_dates=["2026-06-30"],
        )
        assert result["valid"] is False
        assert result["unsupported_tokens"]
    assert _evidence(source=None) is None


def test_symbol_and_dates_use_dedicated_metadata_rules_not_integer_exemption():
    result = _validate("600519 数据日期 2026-08-31；无证据数字 888。", [])
    assert result["valid"] is False
    assert result["metadata_rules"]["all_integers_exempt"] is False
    assert result["unsupported_tokens"] == ["888"]


def test_claim_mismatch_produces_safe_invalid_result():
    evidence = _evidence()
    claim = deepcopy(claim_from_evidence(evidence))
    claim["display_value"] = "1999"
    result = validate_stock_eod_numeric_claims(
        "收盘价 1999CNY。", [evidence], [claim], symbol="600519", allowed_metadata_dates=[]
    )
    assert result["valid"] is False
    assert "1999" in result["unsupported_tokens"]


def test_report_rag_numeric_validator_is_not_imported_or_modified():
    import app.services.stock_eod_numeric_validation as module

    assert "report" not in {name.split(".")[0] for name in module.__dict__ if name.startswith("report_")}


def _snapshot():
    def fact(value, unit, as_of):
        return {"value": value, "unit": unit, "as_of": as_of, "source": "tushare"}
    return {
        "fulfillment": "fulfilled", "reason_code": None, "as_of": "2026-08-31",
        "modules": {
            "quote": {"fields": {"close": fact(1688.25, "CNY", "2026-08-31")}},
            "valuation": {"fields": {
                "pe_ttm": fact(24.3, "multiple", "2026-08-31"),
                "pb": fact(7.12, "multiple", "2026-08-31"),
            }},
            "financial": {"fields": {"roe": fact(19.7, "%", "2026-06-30")}},
        },
    }


def _live_shape_snapshot():
    path = Path(__file__).parents[1] / "fixtures" / "phase7e_p0_1_tushare_600519_eod.json"
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.mark.asyncio
async def test_q3_response_exposes_successful_request_local_numeric_validation(monkeypatch):
    from app.agents import chat_orchestrator as orchestrator

    entity = SimpleNamespace(market="CN", symbol="600519", short_name="贵州茅台", full_name="贵州茅台股份有限公司")
    monkeypatch.setattr(orchestrator.security_entity_resolver, "resolve", AsyncMock(return_value={"entities": [entity], "ambiguity": False}))
    monkeypatch.setattr(orchestrator.tushare_eod_gateway, "get_company_snapshot", AsyncMock(return_value=_snapshot()))
    official = AsyncMock(side_effect=AssertionError("stock EOD route must not mix CNINFO event titles"))
    monkeypatch.setattr(orchestrator.official_company_event_service, "list_persisted_events", official)

    result = await orchestrator.process_message("600519 财务指标、ROE、估值", None, uuid4())
    validation = result.metadata["numeric_validation"]
    assert result.metadata["symbol"] == "600519"
    assert result.metadata["source"] == ["tushare"]
    assert result.metadata["as_of"] == "2026-08-31"
    assert validation["valid"] is True
    assert validation["unsupported_tokens"] == []
    assert any(item["report_period"] == "2026-06-30" for item in validation["evidence_basis"])
    official.assert_not_awaited()


@pytest.mark.asyncio
async def test_validation_failure_returns_partial_and_removes_unverified_numbers(monkeypatch):
    from app.agents import chat_orchestrator as orchestrator

    entity = SimpleNamespace(market="CN", symbol="600519", short_name="贵州茅台", full_name="贵州茅台股份有限公司")
    monkeypatch.setattr(orchestrator.security_entity_resolver, "resolve", AsyncMock(return_value={"entities": [entity], "ambiguity": False}))
    monkeypatch.setattr(orchestrator.tushare_eod_gateway, "get_company_snapshot", AsyncMock(return_value=_snapshot()))
    monkeypatch.setattr(orchestrator, "validate_stock_eod_numeric_claims", lambda *args, **kwargs: {
        "valid": False, "checked_claims": [], "unsupported_tokens": ["9999"], "evidence_basis": []
    })

    result = await orchestrator.process_message("600519 财务指标、ROE、估值", None, uuid4())
    assert result.metadata["fulfillment"] == "partial"
    assert result.metadata["reason_code"] == "NUMERIC_EVIDENCE_VALIDATION_FAILED"
    assert result.metadata["numeric_validation"]["valid"] is False
    assert "1688.25" not in result.answer
    assert "9999" not in result.answer


@pytest.mark.asyncio
@pytest.mark.parametrize("query", ["贵州茅台近期情况", "600519 财务指标、ROE、估值"])
async def test_live_tushare_shape_is_fully_grounded_without_report_or_event_number_leakage(monkeypatch, query):
    from app.agents import chat_orchestrator as orchestrator

    entity = SimpleNamespace(
        market="CN", symbol="600519", short_name="贵州茅台", full_name="贵州茅台股份有限公司"
    )
    gateway = AsyncMock(return_value=_live_shape_snapshot())
    official = AsyncMock(side_effect=AssertionError("CNINFO is a separate research route"))
    monkeypatch.setattr(
        orchestrator.security_entity_resolver,
        "resolve",
        AsyncMock(return_value={"entities": [entity], "ambiguity": False}),
    )
    monkeypatch.setattr(orchestrator.tushare_eod_gateway, "get_company_snapshot", gateway)
    monkeypatch.setattr(orchestrator.official_company_event_service, "list_persisted_events", official)

    result = await orchestrator.process_message(query, None, uuid4())
    validation = result.metadata["numeric_validation"]

    assert result.metadata["route"] == "stock_eod_research"
    assert result.metadata["symbol"] == "600519"
    assert result.metadata["source"] == ["tushare"]
    assert result.metadata["fulfillment"] == "fulfilled"
    assert result.metadata["reason_code"] is None
    assert result.metadata["as_of"] == "2026-09-09"
    assert validation["valid"] is True
    assert validation["unsupported_tokens"] == []
    assert len(validation["checked_claims"]) == len(validation["evidence_basis"]) == 18
    assert {item["source"] for item in validation["evidence_basis"]} == {"tushare"}
    assert any(item["metric"] == "close" and item["display_value"] == "1290.88" for item in validation["evidence_basis"])
    assert any(item["metric"] == "pe_ttm" and item["display_value"] == "19.8161" for item in validation["evidence_basis"])
    assert any(item["metric"] == "pb" and item["display_value"] == "6.4226" for item in validation["evidence_basis"])
    assert any(item["metric"] == "roe" and item["report_period"] == "2026-06-30" for item in validation["evidence_basis"])
    assert "不是实时行情" in result.answer
    assert "Report RAG" in result.answer
    gateway.assert_awaited_once_with("CN", "600519")
    official.assert_not_awaited()


def test_live_shape_symbol_exchange_and_strict_unit_period_source_contract():
    from app.datasource.tushare_client import _to_ts_code

    snapshot = _live_shape_snapshot()
    assert _to_ts_code(snapshot["market"], snapshot["symbol"]) == snapshot["ts_code"] == "600519.SH"
    roe = snapshot["modules"]["financial"]["fields"]["roe"]
    assert roe == {"value": 17.9543, "unit": "%", "as_of": "2026-06-30", "source": "tushare"}

    wrong_unit = {**roe, "unit": "multiple"}
    wrong_period = {**roe, "as_of": "2026-09-09"}
    wrong_source = {**roe, "source": None}
    assert make_request_local_evidence(module="financial", metric="roe", fact=wrong_unit) is None
    evidence = make_request_local_evidence(module="financial", metric="roe", fact=roe)
    bad_claim = claim_from_evidence(evidence)
    bad_claim["unit"] = "multiple"
    assert validate_stock_eod_numeric_claims(
        "600519 ROE 17.9543%，报告期 2026-06-30。", [evidence], [bad_claim],
        symbol="600519", allowed_metadata_dates=["2026-06-30"],
    )["valid"] is False
    stale = make_request_local_evidence(module="financial", metric="roe", fact=wrong_period)
    assert stale["report_period"] == "2026-09-09"
    assert make_request_local_evidence(module="financial", metric="roe", fact=wrong_source) is None
