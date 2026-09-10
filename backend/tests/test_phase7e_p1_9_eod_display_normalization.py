from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.services.stock_eod_display import project_stock_eod_display
from app.services.stock_eod_numeric_validation import (
    claim_from_evidence,
    validate_stock_eod_numeric_claims,
)


def _fact(value, unit, as_of="2026-09-09"):
    return {"value": value, "unit": unit, "as_of": as_of, "source": "tushare"}


@pytest.mark.parametrize(
    ("module", "metric", "value", "unit", "display_value", "display_unit", "conversion"),
    [
        ("quote", "amount", 4169035.35291, "CNY_thousand", "41.69", "亿元", "CNY_thousand_to_CNY_100M"),
        ("valuation", "total_mv", 20226203.088, "CNY_10k", "2,022.62", "亿元", "CNY_10k_to_CNY_100M"),
        ("quote", "vol", 7616584.07, "lot", "761.66", "万手", "lot_to_10k_lot"),
        ("valuation", "pe_ttm", 25.7405, "multiple", "25.74", "倍", "identity"),
        ("quote", "close", 5.46, "CNY", "5.46", "元", "identity"),
        ("financial", "roe", 17.9543, "%", "17.95", "%", "identity"),
    ],
)
def test_deterministic_display_projection_preserves_canonical_evidence(
    module, metric, value, unit, display_value, display_unit, conversion
):
    result = project_stock_eod_display(module=module, metric=metric, fact=_fact(value, unit))

    assert result["status"] == "fulfilled"
    evidence = result["evidence"]
    assert evidence == {
        **evidence,
        "metric": metric,
        "canonical_value": str(value),
        "canonical_unit": unit,
        "display_value": display_value,
        "display_unit": display_unit,
        "rounding_policy": "ROUND_HALF_UP_2_DECIMALS",
        "evidence_id": f"stock-eod:{module}:{metric}",
        "request_local_evidence_id": f"stock-eod:{module}:{metric}",
        "as_of": "2026-09-09",
        "source": "tushare",
    }
    assert evidence["format_rule"]["conversion"] == conversion
    assert evidence["format_rule"]["factor"] in {"1", "0.0001", "0.00001"}


def test_volume_conversion_uses_ten_thousand_lots_not_shares():
    result = project_stock_eod_display(
        module="quote", metric="vol", fact=_fact(7616584.07, "lot")
    )
    assert result["evidence"]["display_value"] == "761.66"
    assert result["evidence"]["display_unit"] == "万手"
    assert "股" not in result["evidence"]["display_unit"]


@pytest.mark.parametrize(
    "module,metric,fact",
    [
        ("quote", "close", _fact(5.46, "CNY_thousand")),
        ("quote", "amount", _fact(4169035.35291, "CNY")),
        ("valuation", "pe_ttm", _fact(25.7405, "%")),
        ("financial", "roe", _fact(17.9543, "multiple", "2026-06-30")),
    ],
)
def test_wrong_or_unknown_canonical_unit_is_not_converted(module, metric, fact):
    result = project_stock_eod_display(module=module, metric=metric, fact=fact)
    assert result == {
        "status": "unavailable",
        "reason_code": "DISPLAY_CANONICAL_FACT_REJECTED",
        "evidence": None,
    }


@pytest.mark.parametrize("bad_display", ["41.70", "416.90", "41.690"])
def test_wrong_rounding_or_magnitude_cannot_pass_numeric_validation(bad_display):
    projected = project_stock_eod_display(
        module="quote", metric="amount", fact=_fact(4169035.35291, "CNY_thousand")
    )["evidence"]
    claim = claim_from_evidence(projected)
    claim["display_value"] = bad_display
    answer = f"成交额 {bad_display}亿元，数据日期 2026-09-09。"
    result = validate_stock_eod_numeric_claims(
        answer, [projected], [claim], symbol="000725", allowed_metadata_dates=["2026-09-09"]
    )
    assert result["valid"] is False
    assert result["unsupported_tokens"]


def _fixture(name):
    path = Path(__file__).parent / "fixtures" / name
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("query", "symbol", "ts_code", "fixture_name"),
    [
        ("CN/000725 公司资料 + EOD", "000725", "000725.SZ", "phase7e_p1_6_tushare_000725_eod.json"),
        ("贵州茅台近期情况", "600519", "600519.SH", "phase7e_p0_1_tushare_600519_eod.json"),
        ("600519 财务指标、ROE、估值", "600519", "600519.SH", "phase7e_p0_1_tushare_600519_eod.json"),
    ],
)
async def test_queries_render_readable_units_with_request_local_evidence(
    monkeypatch, query, symbol, ts_code, fixture_name
):
    from app.agents import chat_orchestrator as orchestrator

    snapshot = _fixture(fixture_name)
    if symbol == "600519":
        snapshot = deepcopy(snapshot)
        snapshot["modules"]["profile"] = {
            "fields": {"name": {"value": "贵州茅台", "source": "tushare", "as_of": "2001-08-27"}}
        }
    entity = SimpleNamespace(
        market="CN", symbol=symbol, ts_code=ts_code,
        short_name="京东方A" if symbol == "000725" else "贵州茅台",
        full_name="京东方科技集团股份有限公司" if symbol == "000725" else "贵州茅台股份有限公司",
    )
    gateway = AsyncMock(return_value=snapshot)
    forbidden = AsyncMock(side_effect=AssertionError("general or unapproved tool must not run"))
    monkeypatch.setattr(orchestrator.security_entity_resolver, "resolve", AsyncMock(return_value={"entities": [entity], "ambiguity": False}))
    monkeypatch.setattr(orchestrator.tushare_eod_gateway, "get_company_snapshot", gateway)
    monkeypatch.setattr(orchestrator._registry, "call", forbidden)

    result = await orchestrator.process_message(query, None, uuid4())
    validation = result.metadata["numeric_validation"]

    assert result.metadata["route"] == "stock_eod_research"
    assert result.metadata["fulfillment"] == "fulfilled"
    assert result.metadata["ts_code"] == ts_code
    assert result.metadata["display_normalization"] == {
        "status": "fulfilled", "reason_code": None, "rejected_metrics": []
    }
    assert validation["valid"] is True
    assert validation["unsupported_tokens"] == []
    assert all({
        "metric", "canonical_value", "canonical_unit", "display_value", "display_unit",
        "rounding_policy", "evidence_id",
    }.issubset(item) for item in validation["evidence_basis"])
    assert "CNY_thousand" not in result.answer
    assert "CNY_10k" not in result.answer
    assert "multiple" not in result.answer
    assert "不是实时行情" in result.answer
    assert "约" not in result.answer
    gateway.assert_awaited_once_with("CN", symbol)
    forbidden.assert_not_awaited()


@pytest.mark.asyncio
async def test_unknown_unit_produces_safe_partial_without_showing_raw_value(monkeypatch):
    from app.agents import chat_orchestrator as orchestrator

    snapshot = _fixture("phase7e_p1_6_tushare_000725_eod.json")
    snapshot["modules"]["quote"]["fields"]["close"]["unit"] = "UNKNOWN_CURRENCY"
    entity = SimpleNamespace(
        market="CN", symbol="000725", ts_code="000725.SZ",
        short_name="京东方A", full_name="京东方科技集团股份有限公司",
    )
    monkeypatch.setattr(orchestrator.security_entity_resolver, "resolve", AsyncMock(return_value={"entities": [entity], "ambiguity": False}))
    monkeypatch.setattr(orchestrator.tushare_eod_gateway, "get_company_snapshot", AsyncMock(return_value=snapshot))

    result = await orchestrator.process_message("CN/000725 公司资料 + EOD", None, uuid4())

    assert result.metadata["fulfillment"] == "partial"
    assert result.metadata["reason_code"] == "EOD_DISPLAY_NORMALIZATION_UNAVAILABLE"
    assert result.metadata["display_normalization"]["rejected_metrics"] == ["quote:close"]
    assert "5.55" not in result.answer
    assert result.metadata["numeric_validation"]["valid"] is True
    assert result.metadata["numeric_validation"]["unsupported_tokens"] == []
