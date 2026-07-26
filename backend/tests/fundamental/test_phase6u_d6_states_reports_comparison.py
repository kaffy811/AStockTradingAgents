from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.agents.central_planning_agent import CentralPlanningAgent
from app.agents.chat_skills.base import SkillContext
from app.agents.chat_skills.report_comparison_skill import ReportComparisonSkill, _build_comparison_entities
from app.agents.intent_decision_agent import IntentDecision
from app.services.company_v2_history_service import _build_module_statuses
from app.services.report_document_classifier import (
    KIND_ANNUAL_FULL,
    KIND_CORRECTION,
    KIND_DELAYED_DISCLOSURE,
    KIND_INQUIRY_REPLY,
    KIND_RISK_WARNING,
    classify_report_document,
)
from app.services.conversation_memory_service import MemoryContext, ResolvedEntity, resolve_coreferences
from app.services.security_entity_resolver import SecurityEntityResolver
from app.services import security_entity_resolver as resolver_module


SAMPLE_SECURITIES = [
    {"market": "CN", "symbol": "600519", "short_name": "贵州茅台", "full_name": "贵州茅台酒股份有限公司", "industry": "白酒"},
    {"market": "CN", "symbol": "000858", "short_name": "五粮液", "full_name": "宜宾五粮液股份有限公司", "industry": "白酒"},
    {"market": "CN", "symbol": "300750", "short_name": "宁德时代", "full_name": "宁德时代新能源科技股份有限公司", "industry": "电池"},
    {"market": "CN", "symbol": "601318", "short_name": "中国平安", "full_name": "中国平安保险(集团)股份有限公司", "industry": "保险"},
    {"market": "CN", "symbol": "000001", "short_name": "平安银行", "full_name": "平安银行股份有限公司", "industry": "银行"},
]


def test_d6_annual_full_title_classification():
    result = classify_report_document("300209：2024年年度报告", report_type="annual")
    assert result.report_document_kind == KIND_ANNUAL_FULL
    assert result.report_year == 2024
    assert result.classification_version


def test_d6_non_annual_announcements_are_excluded():
    assert classify_report_document("关于深圳证券交易所年报问询函回复的公告", report_type="annual").report_document_kind == KIND_INQUIRY_REPLY
    assert classify_report_document("关于延期披露2024年年度报告的公告", report_type="annual").report_document_kind == KIND_DELAYED_DISCLOSURE
    assert classify_report_document("关于公司股票可能被实施风险警示的风险提示公告", report_type="annual").report_document_kind == KIND_RISK_WARNING
    assert classify_report_document("2024年年度报告更正公告", report_type="annual").report_document_kind == KIND_CORRECTION


@pytest.mark.asyncio
async def test_d6_security_resolver_supports_sample_names():
    resolver = SecurityEntityResolver(sample_rows=SAMPLE_SECURITIES)
    entities = await resolver.resolve_many(None, "那它和五粮液比呢，顺便看看宁德时代")
    assert [m.symbol for m in entities] == ["000858", "300750"]


@pytest.mark.asyncio
async def test_d6_security_resolver_requires_clarification_for_ambiguous_name():
    resolver = SecurityEntityResolver(sample_rows=SAMPLE_SECURITIES)
    result = await resolver.resolve(None, "平安最近表现如何", market_hint="CN", min_confidence=0.72)
    assert result["ambiguity"] is True
    assert {c["symbol"] for c in result["candidates"]} >= {"601318", "000001"}


def test_d6_coreference_resolves_it_to_previous_primary_stock():
    ctx = MemoryContext(active_entities=[ResolvedEntity(type="stock", name="贵州茅台", code="600519", market="CN")])
    resolved, needs_clarification, _ = resolve_coreferences("那它和五粮液比呢", ctx)
    assert not needs_clarification
    assert "贵州茅台" in resolved
    assert "五粮液" in resolved


def test_d6_planner_routes_followup_comparison_to_report_comparison():
    ctx = MemoryContext(active_entities=[ResolvedEntity(type="stock", name="贵州茅台", code="600519", market="CN")])
    decision = IntentDecision(intent="direct_answer", confidence=0.7, reason="", need_agent=False, need_confirmation=False, target_entities=[])
    plan = CentralPlanningAgent().create_plan("那它和五粮液比呢", decision, memory_context=ctx)
    assert plan.intent == "report_financial_comparison"
    assert plan.tasks
    assert "MultiCompanyFinancialComparisonAgent" in {task.agent for task in plan.tasks}
    assert "无需调用专业 Agent" not in plan.get_phase_event("planning")["content"]
    assert [task.agent for task in plan.tasks].count("MultiCompanyFinancialComparisonAgent") == 1


def test_d6_report_comparison_skill_can_handle_contextual_followup():
    memory = MemoryContext(active_entities=[ResolvedEntity(type="stock", name="贵州茅台", code="600519", market="CN")])
    context = SkillContext(db=None, user_id="u", session_id="s", memory_context=memory)
    assert ReportComparisonSkill().can_handle("那它和五粮液比呢", context)


@pytest.mark.asyncio
async def test_d6_2_pronoun_and_explicit_entity_merge(monkeypatch):
    monkeypatch.setattr(resolver_module.security_entity_resolver, "_sample_rows", SAMPLE_SECURITIES)
    memory = MemoryContext(active_entities=[ResolvedEntity(type="stock", name="贵州茅台", code="600519", market="CN")])
    context = SkillContext(
        db=None,
        user_id="u",
        session_id="s",
        memory_context=memory,
        metadata={"raw_query": "那它和五粮液比呢", "effective_query": "那贵州茅台（CN/600519）和五粮液比呢"},
    )
    entities, diagnostics = await _build_comparison_entities("那贵州茅台（CN/600519）和五粮液比呢", context)
    assert [(e["market"], e["symbol"], e["source"]) for e in entities[:2]] == [
        ("CN", "600519", "pronoun_context"),
        ("CN", "000858", "current_query_explicit"),
    ]
    assert diagnostics["comparison_parser_output"]["entities"][1]["symbol"] == "000858"


@pytest.mark.asyncio
async def test_d6_2_missing_comparison_entities_keeps_context_pending(monkeypatch):
    monkeypatch.setattr(resolver_module.security_entity_resolver, "_sample_rows", SAMPLE_SECURITIES)
    memory = MemoryContext(active_entities=[ResolvedEntity(type="stock", name="贵州茅台", code="600519", market="CN")])
    context = SkillContext(
        db=None,
        user_id="u",
        session_id="s",
        memory_context=memory,
        metadata={"raw_query": "那它比呢", "effective_query": "那贵州茅台（CN/600519）比呢"},
    )
    result = await ReportComparisonSkill().run("那贵州茅台（CN/600519）比呢", context)
    assert result.data["status"] == "failed"
    assert result.data["error_code"] == "COMPARE_ENTITY_MISSING"
    assert result.data["pending_context"]["last_failed_intent"] == "financial_report_comparison"
    assert result.data["diagnostics"]["context_commit_reason"].startswith("not_committed")


def test_d6_extreme_ratio_splits_completeness_and_validity():
    rows = [{
        "period": "2024-12-31",
        "ocf_to_np": 70.411,
        "warnings": [{
            "code": "CFO_TO_NP_DENOMINATOR_SENSITIVE",
            "message": "净利润基数较小，该指标波动较大，仅供辅助参考。",
            "field": "ocf_to_np",
            "outlier_status": "extreme",
        }],
    }]
    statuses = _build_module_statuses(
        rows,
        {"applicable_fields": ["ocf_to_np"], "module_status": "complete"},
        {"periods_count": 1},
        {},
    )
    assert statuses["completeness_status"] == "complete"
    assert statuses["semantic_status"] == "warning"
    assert statuses["outlier_status"] == "extreme"
    assert "基数较小" in statuses["user_message"]


def test_d6_empty_module_status_is_unavailable():
    statuses = _build_module_statuses([], {"applicable_fields": ["roe"]}, {"periods_count": 0}, {})
    assert statuses["completeness_status"] == "unavailable"


def test_d6_report_comparison_cache_key_shape_is_report_scoped():
    left = SimpleNamespace(report_id=2)
    right = SimpleNamespace(report_id=8)
    assert left.report_id != right.report_id
