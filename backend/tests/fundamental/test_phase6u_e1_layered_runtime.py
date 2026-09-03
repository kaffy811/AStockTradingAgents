from __future__ import annotations

import inspect
from pathlib import Path

from app.agents.financial_runtime.compliance import ComplianceGate
from app.agents.financial_runtime.contracts import (
    AgentResponse,
    FinancialSessionContext,
    FinancialFact,
    IntentRoutingResult,
    RuntimeRequest,
    SecurityEntity,
    STATUS_SUCCESS,
    StructuredAnswer,
    ToolResponse,
    VALID_STATUSES,
)
from app.agents.financial_runtime.domain_agents import (
    FinancialReportAnalysisAgent,
    FundamentalAnalysisAgent,
    MultiCompanyFinancialComparisonAgent,
    QuoteAnalysisAgent,
)
from app.agents.financial_runtime.drafting import AnswerRenderer, StructuredAnswerBuilder
from app.agents.financial_runtime.planner import ExecutionPlanner
from app.agents.financial_runtime.router import IntentSafetyRouter
from app.agents.financial_runtime.tool_runtime import FinancialToolRegistry
from app.services.company_v2_report_rag_db_repository import DatabaseCompanyV2ReportRagRepository


def test_l0_router_does_not_query_business_data_or_llm():
    src = inspect.getsource(IntentSafetyRouter)
    assert "stock_data_service" not in src
    assert "ReportDocument" not in src
    assert "build_company_history_dashboard" not in src
    assert "llm" not in src.lower()


def test_l1_planner_does_not_call_providers_or_tools():
    src = inspect.getsource(ExecutionPlanner)
    assert "stock_data_service" not in src
    assert "AsyncSession" not in src
    assert "financial_tool_registry.call" not in src


def test_l2_tools_do_not_call_llm():
    src = inspect.getsource(FinancialToolRegistry)
    assert "deepseek" not in src.lower()
    assert "openai" not in src.lower()
    assert "llm" not in src.lower()


def test_l3_agents_do_not_hold_db_sessions_or_repositories():
    for cls in [
        FinancialReportAnalysisAgent,
        MultiCompanyFinancialComparisonAgent,
        FundamentalAnalysisAgent,
        QuoteAnalysisAgent,
    ]:
        src = inspect.getsource(cls)
        assert "AsyncSession" not in src
        assert "AsyncSessionLocal" not in src
        assert "Repository" not in src
        assert "stock_data_service" not in src
        assert "免责声明" not in src


def test_l4_numeric_fact_requires_evidence_for_report_answer():
    response = AgentResponse(
        trace_id="t",
        status=STATUS_SUCCESS,
        metrics=[
            FinancialFact(
                trace_id="t",
                status=STATUS_SUCCESS,
                fact_id="f1",
                label="营业收入",
                value=100,
                unit="元",
                period="2025-12-31",
                evidence_ids=["report:1:chunk:2"],
                provenance=[{"source": "official_report"}],
            )
        ],
    )
    answer = StructuredAnswerBuilder().build(trace_id="t", intent="financial_report", agent_response=response, tool_data={})
    assert answer.tables[0]["rows"][0]["数值"] == 100
    assert response.metrics[0].evidence_ids


def test_l5_compliance_does_not_use_global_string_replacement():
    src = inspect.getsource(ComplianceGate)
    assert ".replace(" not in src
    review = ComplianceGate().review(StructuredAnswer(trace_id="t", conclusion="建议买入并给出目标价"))
    assert review.passed is False
    assert review.edit_instructions[0]["action"] == "replace_answer"


def test_renderer_builds_deterministic_table_and_no_disclaimer():
    answer = StructuredAnswer(
        trace_id="t",
        status=STATUS_SUCCESS,
        conclusion="已生成对比。",
        tables=[{"columns": ["指标", "A", "B"], "rows": [{"指标": "营收", "A": "1", "B": "2"}]}],
        sources=[{"label": "正式报告"}],
    )
    rendered = AnswerRenderer().render(answer)
    assert "| 指标 | A | B |" in rendered
    assert "仅供研究参考" not in rendered
    assert "<details><summary>查看数据来源</summary>" in rendered


def test_chat_request_layered_path_has_no_sync_rag_bridge():
    runtime_dir = Path(__file__).parents[2] / "app" / "agents" / "financial_runtime"
    src = "\n".join(path.read_text(encoding="utf-8") for path in runtime_dir.glob("*.py"))
    assert "run_coroutine_threadsafe" not in src
    assert ".result()" not in src
    assert "new_event_loop" not in src
    assert "asyncio.run(" not in src


def test_rag_repository_exposes_native_async_api_for_runtime_tools():
    assert hasattr(DatabaseCompanyV2ReportRagRepository, "get_document_async")
    assert hasattr(DatabaseCompanyV2ReportRagRepository, "get_any_document_async")
    assert hasattr(DatabaseCompanyV2ReportRagRepository, "query_chunks_async")
    assert hasattr(DatabaseCompanyV2ReportRagRepository, "get_structured_fields_async")
    assert hasattr(DatabaseCompanyV2ReportRagRepository, "get_latest_indexed_report_async")


def test_tool_response_contract_contains_required_fields():
    resp = ToolResponse(
        trace_id="t",
        status=STATUS_SUCCESS,
        tool_call_id="tool_1",
        capability="get_quote_snapshot",
        data={"x": 1},
        provenance=[{"source": "test"}],
        freshness={"as_of": "now"},
        quality={"status": "usable"},
        latency_ms=1,
    )
    data = resp.to_dict()
    for key in ["trace_id", "schema_version", "status", "created_at", "updated_at", "error_code"]:
        assert key in data
    assert data["provenance"][0]["source"] == "test"


def test_runtime_contract_base_fields_and_status_vocabulary():
    req = RuntimeRequest(trace_id="trace_1", status=STATUS_SUCCESS, raw_query="贵州茅台最新财报")
    data = req.to_dict()
    for key in ["schema_version", "trace_id", "request_id", "status", "created_at", "completed_at", "error_code", "warnings", "metadata"]:
        assert key in data
    assert req.status in VALID_STATUSES


def test_tool_registry_declares_first_batch_and_deferred_capabilities():
    registry = FinancialToolRegistry()
    for capability in [
        "resolve_security",
        "get_market_clock",
        "get_quote_snapshot",
        "get_market_history",
        "get_company_profile",
        "get_financial_snapshot",
        "get_financial_history",
        "get_official_reports",
        "get_latest_official_report",
        "get_official_report_url",
        "get_structured_report_financials",
        "query_report_evidence",
        "compare_financials",
        "align_financial_periods",
        "compare_financial_fields",
        "get_company_news",
        "get_market_events",
        "get_industry_snapshot",
        "get_peer_companies",
        "get_industry_benchmark",
        "update_watchlist",
    ]:
        assert capability in registry.capabilities


def test_execution_planner_first_five_migrated_scenarios():
    entity = SecurityEntity(trace_id="t", status=STATUS_SUCCESS, market="CN", symbol="600519", short_name="贵州茅台")
    context = FinancialSessionContext(trace_id="t", status=STATUS_SUCCESS, primary_entity=entity, active_market="CN", active_symbol="600519")
    planner = ExecutionPlanner()
    cases = {
        "quote_query": ["get_quote_snapshot"],
        "official_report_pdf": ["get_official_report_url"],
        "financial_report": ["get_official_reports", "get_structured_report_financials", "query_report_evidence"],
        "financial_comparison": ["get_official_reports", "get_structured_report_financials", "compare_financials"],
        "company_fundamental": ["get_financial_snapshot"],
    }
    for intent, capabilities in cases.items():
        routing = IntentRoutingResult(trace_id="t", status=STATUS_SUCCESS, intent=intent, resolved_entities=[entity])
        if intent == "financial_comparison":
            context.secondary_entities = [SecurityEntity(trace_id="t", status=STATUS_SUCCESS, market="CN", symbol="000858", short_name="五粮液")]
        plan = planner.plan(trace_id="t", routing=routing, context=context)
        assert [step.capability for step in plan.steps] == capabilities
        assert plan.status == STATUS_SUCCESS
