from __future__ import annotations

import asyncio
import inspect
from pathlib import Path
from typing import Any

import pytest

from app.agent_runtime.agent_loop import PiAgentLoop
from app.agent_runtime.agents.official_report_pdf_agent import OfficialReportPdfAgent
from app.agent_runtime.capability_manifest import official_report_pdf_manifest
from app.agent_runtime.contracts import (
    ModelRequest,
    ModelStreamEvent,
    PiAgentMessage,
    PiRuntimeBudgets,
    PiRuntimeEvent,
    PiRuntimeRequest,
    PiToolCall,
    STATUS_FAILED,
    STATUS_SUCCESS,
    STATUS_UNAVAILABLE,
    new_id,
)
from app.agent_runtime.errors import (
    AGENT_DEADLINE_EXCEEDED,
    AGENT_MAX_TOOL_CALLS_EXCEEDED,
    AGENT_MAX_TURNS_EXCEEDED,
    AGENT_TOOL_ARGUMENT_INVALID,
    AGENT_TOOL_NOT_ALLOWED,
    AGENT_TOOL_TIMEOUT,
)
from app.agent_runtime.event_stream import PiEventRecorder
from app.agent_runtime.executor import PiCompatibleAgentExecutor
from app.agent_runtime.shadow_runner import PiCompatibleShadowRunner
from app.agent_runtime.tool_adapter import PiFinancialToolAdapter
from app.agent_runtime.tool_executor import PiToolExecutor
from app.agents.financial_runtime.contracts import (
    FinancialSessionContext,
    SecurityEntity,
    ToolResponse,
)


ROOT = Path(__file__).parents[3]
ARTIFACTS = ROOT / "backend" / "docs" / "artifacts"


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


def _context(*, year: int | None = 2025, entity: SecurityEntity | None = None) -> FinancialSessionContext:
    entity = entity or _entity()
    return FinancialSessionContext(
        trace_id="trace_test",
        status=STATUS_SUCCESS,
        primary_entity=entity,
        active_market=entity.market,
        active_symbol=entity.symbol,
        active_report_year=year,
    )


class FakeRegistry:
    def __init__(self, *, delay: float = 0.0, reports: list[dict[str, Any]] | None = None) -> None:
        self.delay = delay
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.cancelled = False
        self.reports = reports if reports is not None else [{
            "report_id": 1,
            "ts_code": "600519.SH",
            "title": "贵州茅台2025年年度报告",
            "report_year": 2025,
            "period_end": "2025-12-31",
            "report_type": "annual",
            "source_url": "https://www.cninfo.com.cn/new/disclosure/detail?stockCode=600519",
            "pdf_url": "https://static.cninfo.com.cn/finalpage/2026-04-30/official.PDF",
        }]

    async def call(self, capability: str, parameters: dict[str, Any], *, trace_id: str, context: FinancialSessionContext) -> ToolResponse:
        self.calls.append((capability, parameters))
        try:
            if self.delay:
                await asyncio.sleep(self.delay)
        except asyncio.CancelledError:
            self.cancelled = True
            raise
        return ToolResponse(
            trace_id=trace_id,
            status=STATUS_SUCCESS,
            tool_call_id=new_id("tool"),
            capability=capability,
            data={"reports_by_symbol": {"600519.SH": self.reports}} if capability == "get_official_reports" else {"entities": []},
            provenance=[{"source": "official_report_domain_service"}],
            freshness={"as_of": "2026-07-18T00:00:00+00:00"},
            quality={"status": "usable"},
            latency_ms=1,
        )


class FakeGateway:
    def __init__(self, turns: list[list[ModelStreamEvent]]) -> None:
        self.turns = turns
        self.calls = 0

    async def stream(self, request: ModelRequest):
        events = self.turns[min(self.calls, len(self.turns) - 1)]
        self.calls += 1
        for event in events:
            yield event


def test_p0_artifacts_exist_and_include_decision():
    expected = [
        "pi_mono_component_inventory.md",
        "pi_mono_license_security_review.md",
        "pi_mono_adoption_decision.md",
        "pi_compatible_runtime_architecture.md",
        "pi_compatible_agent_contracts.md",
        "pi_compatible_tool_protocol.md",
        "pi_compatible_event_protocol.md",
    ]
    for name in expected:
        assert (ARTIFACTS / name).exists()
    assert "Python Pi-Compatible Runtime" in (ARTIFACTS / "pi_mono_adoption_decision.md").read_text(encoding="utf-8")


def test_license_review_artifact_declares_mit_and_no_vendored_source():
    text = (ARTIFACTS / "pi_mono_license_security_review.md").read_text(encoding="utf-8")
    assert "MIT" in text
    assert "does not copy source code" in text


def test_no_coding_agent_tools_selected():
    assert set(official_report_pdf_manifest.allowed_tools) == {"resolve_security", "get_official_reports"}
    forbidden = {"bash", "read", "write", "edit", "grep", "find", "ls", "javascript_repl"}
    assert not forbidden.intersection(official_report_pdf_manifest.allowed_tools)


def test_event_and_contract_schema_versions_are_valid():
    event = PiRuntimeEvent(trace_id="trace", run_id="run", event_type="run_start", sequence=1)
    assert event.to_dict()["schema_version"] == "pi_financial_event_v1"
    req = _request()
    assert req.to_dict()["schema_version"] == "pi_financial_runtime_v1"


@pytest.mark.asyncio
async def test_executor_loop_ends_when_no_tool_call():
    gateway = FakeGateway([[ModelStreamEvent(event_type="structured_output", structured_output={"ok": True})]])
    loop = PiAgentLoop(tool_adapter=PiFinancialToolAdapter(FakeRegistry()), model_gateway=gateway)
    events = PiEventRecorder(trace_id="trace_test", run_id="run_test")
    result = await loop.run(
        request=_request(),
        financial_context=_context(),
        messages=[PiAgentMessage(role="user", content="hello")],
        agent_id="test_agent",
        events=events,
    )
    assert result.status == STATUS_SUCCESS
    assert result.turn_count == 1
    assert result.tool_call_count == 0


@pytest.mark.asyncio
async def test_max_turns_enforced():
    gateway = FakeGateway([[ModelStreamEvent(event_type="tool_call", tool_call=PiToolCall("tc1", "get_official_reports", {}))]])
    req = _request(budgets=PiRuntimeBudgets(max_turns=1, max_tool_calls=4))
    loop = PiAgentLoop(tool_adapter=PiFinancialToolAdapter(FakeRegistry()), model_gateway=gateway)
    result = await loop.run(
        request=req,
        financial_context=_context(),
        messages=[],
        agent_id="test_agent",
        events=PiEventRecorder(trace_id=req.trace_id, run_id=req.run_id),
    )
    assert result.status == STATUS_FAILED
    assert result.error["code"] == AGENT_MAX_TURNS_EXCEEDED


@pytest.mark.asyncio
async def test_max_tool_calls_enforced():
    gateway = FakeGateway([[
        ModelStreamEvent(event_type="tool_call", tool_call=PiToolCall("tc1", "get_official_reports", {})),
        ModelStreamEvent(event_type="tool_call", tool_call=PiToolCall("tc2", "get_official_reports", {})),
    ]])
    req = _request(budgets=PiRuntimeBudgets(max_turns=3, max_tool_calls=1))
    loop = PiAgentLoop(tool_adapter=PiFinancialToolAdapter(FakeRegistry()), model_gateway=gateway)
    result = await loop.run(
        request=req,
        financial_context=_context(),
        messages=[],
        agent_id="test_agent",
        events=PiEventRecorder(trace_id=req.trace_id, run_id=req.run_id),
    )
    assert result.error["code"] == AGENT_MAX_TOOL_CALLS_EXCEEDED


@pytest.mark.asyncio
async def test_deadline_cancels_execution():
    adapter = PiFinancialToolAdapter(FakeRegistry(delay=0.05))
    executor = PiCompatibleAgentExecutor(tool_adapter=adapter)
    req = _request(budgets=PiRuntimeBudgets(deadline_ms=1, max_turns=3, max_tool_calls=4))
    result = await executor.run(request=req, financial_context=_context())
    assert result.status == STATUS_FAILED
    assert result.error["code"] == AGENT_DEADLINE_EXCEEDED


@pytest.mark.asyncio
async def test_cancelled_error_propagates_correctly():
    registry = FakeRegistry(delay=1.0)
    executor = PiCompatibleAgentExecutor(tool_adapter=PiFinancialToolAdapter(registry))
    task = asyncio.create_task(executor.run(request=_request(), financial_context=_context()))
    await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert registry.cancelled is True


@pytest.mark.asyncio
async def test_invalid_unknown_and_unauthorized_tools_rejected():
    adapter = PiFinancialToolAdapter(FakeRegistry())
    context = _context()
    invalid = await adapter.execute(
        PiToolCall("tc1", "resolve_security", {"query": "贵州茅台", "extra": "no"}),
        trace_id="trace",
        context=context,
        allowed_tools={"resolve_security"},
    )
    unknown = await adapter.execute(
        PiToolCall("tc2", "bash", {"command": "pwd"}),
        trace_id="trace",
        context=context,
        allowed_tools={"resolve_security"},
    )
    unauthorized = await adapter.execute(
        PiToolCall("tc3", "get_official_reports", {}),
        trace_id="trace",
        context=context,
        allowed_tools={"resolve_security"},
    )
    assert invalid.error_code == AGENT_TOOL_ARGUMENT_INVALID
    assert unknown.error_code == AGENT_TOOL_NOT_ALLOWED
    assert unauthorized.error_code == AGENT_TOOL_NOT_ALLOWED


@pytest.mark.asyncio
async def test_tool_timeout_isolated():
    adapter = PiFinancialToolAdapter(FakeRegistry(delay=0.05))
    adapter.get_definition("get_official_reports").timeout_ms = 1
    resp = await adapter.execute(
        PiToolCall("tc", "get_official_reports", {}),
        trace_id="trace",
        context=_context(),
        allowed_tools={"get_official_reports"},
    )
    assert resp.error_code == AGENT_TOOL_TIMEOUT


@pytest.mark.asyncio
async def test_sequential_results_preserve_order_and_provenance():
    adapter = PiFinancialToolAdapter(FakeRegistry())
    executor = PiToolExecutor(adapter)
    calls = [
        PiToolCall("tc1", "get_official_reports", {}),
        PiToolCall("tc2", "resolve_security", {"query": "贵州茅台"}),
    ]
    responses = await executor.execute(
        calls,
        trace_id="trace",
        context=_context(),
        allowed_tools={"get_official_reports", "resolve_security"},
        max_remaining_calls=4,
        max_parallel_tools=2,
        mode="sequential",
        events=PiEventRecorder(trace_id="trace", run_id="run"),
    )
    assert [resp.capability for resp in responses] == ["get_official_reports", "resolve_security"]
    assert responses[0].provenance[0]["source"] == "official_report_domain_service"


@pytest.mark.asyncio
async def test_parallel_execution_requires_parallel_safe_tools():
    class CountingRegistry(FakeRegistry):
        def __init__(self) -> None:
            super().__init__(delay=0.01)
            self.active = 0
            self.max_active = 0

        async def call(self, capability: str, parameters: dict[str, Any], *, trace_id: str, context: FinancialSessionContext) -> ToolResponse:
            self.active += 1
            self.max_active = max(self.max_active, self.active)
            try:
                return await super().call(capability, parameters, trace_id=trace_id, context=context)
            finally:
                self.active -= 1

    registry = CountingRegistry()
    adapter = PiFinancialToolAdapter(registry)
    adapter.get_definition("resolve_security").parallel_safe = False
    responses = await PiToolExecutor(adapter).execute(
        [
            PiToolCall("tc1", "resolve_security", {"query": "贵州茅台"}),
            PiToolCall("tc2", "get_official_reports", {}),
        ],
        trace_id="trace",
        context=_context(),
        allowed_tools={"get_official_reports", "resolve_security"},
        max_remaining_calls=4,
        max_parallel_tools=2,
        mode="parallel",
        events=PiEventRecorder(trace_id="trace", run_id="run"),
    )
    assert len(responses) == 2
    assert registry.max_active == 1


def test_no_db_session_across_model_call_and_no_private_event_loop_bridge():
    runtime_dir = ROOT / "backend" / "app" / "agent_runtime"
    src = "\n".join(path.read_text(encoding="utf-8") for path in runtime_dir.rglob("*.py"))
    loop_src = inspect.getsource(PiAgentLoop)
    assert "AsyncSession" not in loop_src
    assert "AsyncSessionLocal" not in loop_src
    assert "new_event_loop" not in src
    assert "run_coroutine_threadsafe" not in src
    assert "asyncio.run(" not in src


@pytest.mark.asyncio
async def test_official_report_pdf_deterministic_path_without_llm():
    result = await PiCompatibleAgentExecutor(tool_adapter=PiFinancialToolAdapter(FakeRegistry())).run(
        request=_request(),
        financial_context=_context(year=2025),
    )
    assert result.status == STATUS_SUCCESS
    assert result.metrics.model_calls == 0
    assert result.tool_call_count == 1
    assert result.findings[0]["official_url"] == "https://static.cninfo.com.cn/finalpage/2026-04-30/official.PDF"


@pytest.mark.asyncio
async def test_official_report_supports_explicit_stock_code_and_company_name():
    agent = OfficialReportPdfAgent(tool_adapter=PiFinancialToolAdapter(FakeRegistry()))
    req = _request(entities=[{"market": "CN", "symbol": "600519", "ts_code": "600519.SH", "short_name": "贵州茅台"}])
    result = await agent.run(request=req, financial_context=_context(year=2025), events=PiEventRecorder(trace_id=req.trace_id, run_id=req.run_id))
    assert result.status == STATUS_SUCCESS
    assert "贵州茅台2025年年度报告" in result.structured_answer["findings"][0]


@pytest.mark.asyncio
async def test_official_report_supports_current_report_context_and_year_selection():
    reports = [
        {"report_id": 2, "ts_code": "600519.SH", "title": "2024年年度报告", "report_year": 2024, "report_type": "annual", "pdf_url": "https://static.cninfo.com.cn/finalpage/2025-04-30/2024.PDF"},
        {"report_id": 3, "ts_code": "600519.SH", "title": "2025年年度报告", "report_year": 2025, "report_type": "annual", "pdf_url": "https://static.cninfo.com.cn/finalpage/2026-04-30/2025.PDF"},
    ]
    result = await PiCompatibleAgentExecutor(tool_adapter=PiFinancialToolAdapter(FakeRegistry(reports=reports))).run(
        request=_request(context={"report_year": 2024}),
        financial_context=_context(year=2025),
    )
    assert result.findings[0]["official_url"] == "https://static.cninfo.com.cn/finalpage/2025-04-30/2024.PDF"
    assert result.findings[0]["report_year"] == 2024


@pytest.mark.asyncio
async def test_no_report_or_no_url_returns_unavailable_without_fabrication():
    no_report = await PiCompatibleAgentExecutor(tool_adapter=PiFinancialToolAdapter(FakeRegistry(reports=[]))).run(
        request=_request(),
        financial_context=_context(),
    )
    no_url = await PiCompatibleAgentExecutor(tool_adapter=PiFinancialToolAdapter(FakeRegistry(reports=[{"report_year": 2025, "title": "无链接报告"}]))).run(
        request=_request(),
        financial_context=_context(),
    )
    assert no_report.status == STATUS_UNAVAILABLE
    assert no_report.structured_answer["conclusion"] == "暂未找到可验证的官方报告 PDF。"
    assert no_url.status == STATUS_UNAVAILABLE
    assert "http" not in no_url.structured_answer["conclusion"]


def test_normal_ui_hides_internal_event_payload_but_debug_trace_exists():
    recorder = PiEventRecorder(trace_id="trace", run_id="run")
    recorder.emit("tool_call_start", {"arguments": {"report_id": 1}, "tool_name": "get_official_reports"})
    normal = recorder.public_events(debug=False)[0]
    debug = recorder.public_events(debug=True)[0]
    assert "arguments" not in normal["payload"]
    assert debug["payload"]["arguments"]["report_id"] == 1


def test_shadow_comparison_has_zero_side_effects_and_no_prompt_storage():
    runner = PiCompatibleShadowRunner()
    comparison = runner.compare(
        legacy={"status": "success", "intent": "official_report_pdf", "entity": {}, "report_year": 2025, "official_url": "https://static.cninfo.com.cn/finalpage/2026-04-30/official.PDF", "latency_ms": 1},
        pi_compatible={
            "trace_id": "trace",
            "status": "success",
            "findings": [{"official_url": "https://static.cninfo.com.cn/finalpage/2026-04-30/official.PDF", "report_year": 2025}],
            "evidence_ids": ["official_report:600519.SH:2025"],
            "metrics": {"latency_ms": 2},
            "turn_count": 0,
            "tool_call_count": 1,
        },
    )
    assert comparison["comparison"]["side_effect_count"] == 0
    assert comparison["comparison"]["pdf_url_match"] is True
    assert "prompt" not in str(comparison).lower()


def test_default_config_and_rollout_flags_unchanged():
    from app.core.config import settings

    assert settings.chat_runtime_mode == "legacy"
    assert settings.agent_executor_mode == "legacy"
    assert settings.pi_agent_shadow_enabled is False
    assert settings.pi_agent_allowed_agents == ""
    assert settings.company_v2_financial_fusion_auto_run is False
    assert settings.company_v2_financial_fusion_rollout_percent == 0
    assert settings.company_v2_financial_fusion_stage3_authorized is False
    assert settings.pi_official_report_tool_timeout_ms >= 10000


def test_database_sql_logging_defaults_hide_binds():
    from app.core.config import settings
    from app.core.database import _engine_kwargs

    assert settings.database_sql_echo is False
    assert settings.database_sql_hide_parameters is True


def test_official_pdf_intent_variants_are_eligible_for_shadow_agent():
    runner = PiCompatibleShadowRunner()
    for query in ["这份报告原文在哪里？", "年报链接", "官方报告地址", "这个年报的官方PDF链接"]:
        assert runner._looks_like_official_pdf_intent(query, query) is True


def test_shadow_uses_legacy_snapshot_for_official_pdf_without_reroute():
    runner = PiCompatibleShadowRunner()
    routing = runner._routing_from_snapshot(
        trace_id="trace",
        raw_query="这份报告原文在哪里？",
        normalized_query="这份报告原文在哪里？",
        resolved_entity_snapshot={
            "primary_entity": {"market": "CN", "symbol": "300750", "ts_code": "300750.SZ", "short_name": "宁德时代"},
            "ambiguity": False,
        },
    )
    assert routing is not None
    assert routing.intent == "official_report_pdf"
    assert routing.resolved_entities[0].symbol == "300750"


def test_shadow_ambiguous_official_pdf_alias_enters_clarification():
    runner = PiCompatibleShadowRunner()
    routing = runner._routing_from_snapshot(
        trace_id="trace",
        raw_query="平安的年报PDF在哪里？",
        normalized_query="平安的年报PDF在哪里？",
        resolved_entity_snapshot={},
    )
    assert routing is not None
    assert routing.intent == "official_report_pdf"
    assert routing.needs_clarification is True
    names = {item["short_name"] for item in routing.clarification_options}
    assert {"平安银行", "中国平安"}.issubset(names)

def test_official_report_tool_timeout_uses_configured_live_deadline():
    from app.core.config import settings

    adapter = PiFinancialToolAdapter(FakeRegistry())
    assert adapter.get_definition("get_official_reports").timeout_ms == settings.pi_official_report_tool_timeout_ms
    assert adapter.get_definition("get_official_reports").timeout_ms >= 10000
