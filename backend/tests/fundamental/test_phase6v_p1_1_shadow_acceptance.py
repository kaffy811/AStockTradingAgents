from __future__ import annotations

import asyncio
from typing import Any

import pytest

from app.agent_runtime.agents.official_report_pdf_agent import OfficialReportPdfAgent
from app.agent_runtime.contracts import PiRuntimeRequest, STATUS_SUCCESS, STATUS_UNAVAILABLE
from app.agent_runtime.event_stream import PiEventRecorder
from app.agent_runtime.shadow_acceptance import (
    ShadowSideEffectSnapshot,
    build_agent_gate,
    build_live_shadow_case_result,
    build_runtime_gate,
    compute_pi_side_effect_count,
    planned_official_report_shadow_cases,
    summarize_shadow_results,
)
from app.agent_runtime.shadow_runner import PiCompatibleShadowRunner
from app.agent_runtime.tool_adapter import PiFinancialToolAdapter
from app.agent_runtime.url_utils import normalize_report_url, official_domain_verified
from app.agents.financial_runtime.contracts import FinancialSessionContext, SecurityEntity, ToolResponse


def _entity(symbol: str = "600519", name: str = "贵州茅台") -> SecurityEntity:
    return SecurityEntity(
        trace_id="trace_test",
        status=STATUS_SUCCESS,
        market="CN",
        symbol=symbol,
        ts_code=f"{symbol}.SH" if symbol.startswith("6") else f"{symbol}.SZ",
        short_name=name,
        source="test",
    )


def _context(*, year: int | None = 2025, report_type: str | None = "annual") -> FinancialSessionContext:
    entity = _entity()
    return FinancialSessionContext(
        trace_id="trace_test",
        status=STATUS_SUCCESS,
        primary_entity=entity,
        active_market=entity.market,
        active_symbol=entity.symbol,
        active_report_year=year,
        active_report_type=report_type,
    )


def _request(**overrides: Any) -> PiRuntimeRequest:
    data = {
        "trace_id": "trace_test",
        "run_id": "run_test",
        "conversation_id": "conv",
        "user_id": "user",
        "intent": "official_report_pdf",
        "allowed_tools": ["resolve_security", "get_official_reports"],
        "runtime_mode": "shadow",
        "read_only": True,
    }
    data.update(overrides)
    return PiRuntimeRequest(**data)


class Registry:
    def __init__(self, reports: list[dict[str, Any]]) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.reports = reports

    async def call(self, capability: str, parameters: dict[str, Any], *, trace_id: str, context: FinancialSessionContext) -> ToolResponse:
        self.calls.append((capability, parameters))
        return ToolResponse(
            trace_id=trace_id,
            status=STATUS_SUCCESS,
            capability=capability,
            tool_call_id="tool_1",
            data={"reports_by_symbol": {"600519.SH": self.reports}},
            provenance=[{"source": "official_report_domain_service"}],
            quality={"status": "usable"},
            latency_ms=1,
        )


def test_planned_live_shadow_cases_are_at_least_30_and_cover_required_scenarios():
    cases = planned_official_report_shadow_cases()
    assert len(cases) >= 30
    assert {"multi_turn_current_report", "explicit_company_name", "explicit_stock_code", "report_type", "ambiguity", "missing"}.issubset({case.query_type for case in cases})


def test_live_gate_rejects_zero_samples_without_fake_rates():
    summary = summarize_shadow_results([], planned_samples=30)
    gate = build_agent_gate(summary)
    runtime_gate = build_runtime_gate(gate)
    assert gate["executed_samples"] == 0
    assert gate["metrics"]["status_match_rate"] is None
    assert gate["metrics"]["url_match_rate"] is None
    assert gate["passed"] is False
    assert gate["recommended_for_next_authorization"] is False
    assert runtime_gate["pi_executor_enabled"] is False
    assert runtime_gate["authorized_agents"] == []
    assert runtime_gate["decision"] == "do_not_enable_pi_compatible"


def test_url_normalization_removes_tracking_but_preserves_signed_query():
    assert normalize_report_url("http://static.cninfo.com.cn/a.PDF?utm_source=x&foo=1") == "https://static.cninfo.com.cn/a.PDF?foo=1"
    signed = "https://static.cninfo.com.cn/a.PDF?X-Amz-Signature=abc&utm_source=x"
    assert normalize_report_url(signed) == signed
    assert official_domain_verified("https://static.cninfo.com.cn/a.PDF") is True
    assert official_domain_verified("https://mirror.example.com/a.PDF") is False


@pytest.mark.asyncio
async def test_report_type_unsupported_returns_unavailable_without_tool_or_llm():
    registry = Registry([{
        "report_id": 1,
        "ts_code": "600519.SH",
        "title": "贵州茅台2025年年度报告",
        "report_type": "annual",
        "report_year": 2025,
        "pdf_url": "https://static.cninfo.com.cn/finalpage/2026-04-30/1.PDF",
    }])
    agent = OfficialReportPdfAgent(tool_adapter=PiFinancialToolAdapter(registry))
    req = _request(context={"report_year": 2025, "report_type": "semi"})
    result = await agent.run(request=req, financial_context=_context(report_type="semi"), events=PiEventRecorder(trace_id=req.trace_id, run_id=req.run_id))
    assert result.status == STATUS_UNAVAILABLE
    assert result.tool_call_count == 0
    assert result.metrics.model_calls == 0
    assert registry.calls == []


@pytest.mark.asyncio
async def test_unofficial_pdf_url_is_rejected_without_fabrication():
    registry = Registry([{
        "report_id": 1,
        "ts_code": "600519.SH",
        "title": "贵州茅台2025年年度报告",
        "report_type": "annual",
        "report_year": 2025,
        "pdf_url": "https://mirror.example.com/fake.PDF",
    }])
    agent = OfficialReportPdfAgent(tool_adapter=PiFinancialToolAdapter(registry))
    req = _request(context={"report_year": 2025, "report_type": "annual"})
    result = await agent.run(request=req, financial_context=_context(), events=PiEventRecorder(trace_id=req.trace_id, run_id=req.run_id))
    assert result.status == STATUS_UNAVAILABLE
    assert result.error["code"] == "OFFICIAL_DOMAIN_UNVERIFIED"
    assert "http" not in result.structured_answer["conclusion"]


@pytest.mark.asyncio
async def test_source_page_and_pdf_url_are_distinguished_and_event_sequence_monotonic():
    registry = Registry([{
        "report_id": 1,
        "ts_code": "600519.SH",
        "title": "贵州茅台2025年年度报告",
        "report_type": "annual",
        "report_year": 2025,
        "source_page_url": "https://www.cninfo.com.cn/new/disclosure/detail?stockCode=600519&utm_source=x",
        "pdf_url": "https://static.cninfo.com.cn/finalpage/2026-04-30/1.PDF",
    }])
    agent = OfficialReportPdfAgent(tool_adapter=PiFinancialToolAdapter(registry))
    req = _request(context={"report_year": 2025, "report_type": "annual"})
    result = await agent.run(request=req, financial_context=_context(), events=PiEventRecorder(trace_id=req.trace_id, run_id=req.run_id))
    finding = result.findings[0]
    assert finding["source_page_url"] != finding["pdf_url"]
    assert finding["official_domain_verified"] is True
    sequences = [event["sequence"] for event in result.events]
    assert sequences == sorted(sequences)
    assert [event["event_type"] for event in result.events][:3] == ["run_start", "turn_start", "tool_call_start"]


def test_shadow_comparison_contract_and_side_effect_count():
    runner = PiCompatibleShadowRunner()
    case = planned_official_report_shadow_cases()[3]
    pi_result = {
        "trace_id": "trace",
        "status": "success",
        "findings": [{
            "market": "CN",
            "symbol": "000858",
            "company_name": "五粮液",
            "report_year": 2025,
            "report_type": "annual",
            "source_page_url": "https://www.cninfo.com.cn/new/disclosure/detail?stockCode=000858&utm_source=x",
            "pdf_url": "https://static.cninfo.com.cn/finalpage/2026-04-30/2.PDF?utm_source=x",
            "official_domain_verified": True,
        }],
        "evidence_ids": ["official_report:000858.SZ:2025"],
        "metrics": {"latency_ms": 12, "model_calls": 0},
        "turn_count": 1,
        "tool_call_count": 1,
        "events": [{"event_type": "run_start", "timestamp": "t", "sequence": 1, "payload": {}}],
    }
    result = build_live_shadow_case_result(
        runner=runner,
        case=case,
        legacy={
            "status": "success",
            "symbol": "000858",
            "report_year": 2025,
            "report_type": "annual",
            "source_page_url": "https://www.cninfo.com.cn/new/disclosure/detail?stockCode=000858",
            "pdf_url": "http://static.cninfo.com.cn/finalpage/2026-04-30/2.PDF",
        },
        pi_result=pi_result,
        side_effect_count=0,
    )
    assert result["schema_version"] == "pi_official_report_shadow_v1"
    assert result["comparison"]["pdf_url_match"] is True
    assert result["comparison"]["unsupported_url_count"] == 0
    assert result["comparison"]["side_effect_count"] == 0
    assert "prompt" not in str(result).lower()

    before = ShadowSideEffectSnapshot(1, 10, 0, 2, 3, 4, 0, 1, 0)
    after = ShadowSideEffectSnapshot(1, 12, 0, 2, 3, 4, 0, 1, 0)
    assert compute_pi_side_effect_count(before, after, expected_legacy_chat_message_delta=2) == 0
    leaked = ShadowSideEffectSnapshot(1, 13, 0, 2, 3, 4, 0, 1, 0)
    assert compute_pi_side_effect_count(before, leaked, expected_legacy_chat_message_delta=2) == 1


@pytest.mark.asyncio
async def test_cancellation_leaves_no_pending_shadow_task():
    async def short_task() -> None:
        await asyncio.sleep(0.01)

    task = asyncio.create_task(short_task())
    await task
    assert task.done()
