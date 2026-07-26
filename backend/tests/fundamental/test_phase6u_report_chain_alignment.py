from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _doc(
    report_id: int,
    *,
    ts_code: str = "600519.SH",
    report_year: int = 2024,
    report_type: str = "annual",
    period_end: str = "2024-12-31",
):
    from app.models.report_document import ReportDocument

    return ReportDocument(
        id=report_id,
        ts_code=ts_code,
        report_type=report_type,
        report_year=report_year,
        period_end=period_end,
        title=f"{ts_code} {report_year} {report_type}",
        disclosure_date=f"{report_year + 1}-03-30",
    )


class _FakeScalars:
    def __init__(self, item):
        self.item = item

    def first(self):
        return self.item


class _FakeResult:
    def __init__(self, item):
        self.item = item

    def scalars(self):
        return _FakeScalars(self.item)


class _FakeDb:
    def __init__(self, *items):
        self.items = list(items)
        self.statements = []

    async def execute(self, stmt):
        self.statements.append(stmt)
        item = self.items.pop(0) if self.items else None
        return _FakeResult(item)


def _selection(report_id: int = 2, reason: str = "explicit_report_id"):
    from app.agent.report_context import ReportSelection

    return ReportSelection(
        report_id=report_id,
        symbol="600519",
        market="CN",
        ts_code="600519.SH",
        stock_name="贵州茅台",
        report_year=2024,
        report_type="annual",
        period_end="2024-12-31",
        title="贵州茅台2024年年度报告",
        disclosure_date="2025-03-30",
        selection_reason=reason,
    )


def _chunk(chunk_id: int = 10):
    return {
        "chunk_id": chunk_id,
        "report_id": 2,
        "ts_code": "600519.SH",
        "report_type": "annual",
        "report_year": 2024,
        "period": "2024-12-31",
        "section_title": "管理层讨论",
        "content": "2024年年度报告披露，经营活动现金流量净额为正。",
        "score": 0.9,
    }


@pytest.mark.asyncio
async def test_phase6u_report_selection_priority_and_no_fallback():
    from app.agent.report_context import resolve_report_selection

    db = _FakeDb(_doc(2, report_year=2023), _doc(3, report_year=2024))
    selected = await resolve_report_selection(
        db=db,
        market="CN",
        symbol="600519",
        stock_name="贵州茅台",
        question="使用 report_id=2 分析贵州茅台 2024 年年报",
        years=[2024],
    )
    assert selected.ok is True
    assert selected.report_id == 2
    assert selected.selection_reason == "explicit_report_id"
    assert selected.stock_name == "贵州茅台"
    assert len(db.statements) == 1

    invalid_db = _FakeDb(None, _doc(9))
    invalid = await resolve_report_selection(
        db=invalid_db,
        market="CN",
        symbol="600519",
        question="使用 report_id=999 分析贵州茅台",
    )
    assert invalid.ok is False
    assert invalid.selection_reason == "explicit_report_id_not_found"
    assert "不能回退" in invalid.error
    assert len(invalid_db.statements) == 1


@pytest.mark.asyncio
async def test_phase6u_explicit_year_memory_and_latest_ordering():
    from app.agent.report_context import resolve_report_selection

    by_year = await resolve_report_selection(
        db=_FakeDb(_doc(4, report_year=2024)),
        market="CN",
        symbol="600519",
        question="贵州茅台 2024 年年报表现如何？",
    )
    assert by_year.report_id == 4
    assert by_year.selection_reason == "explicit_year_or_period"

    by_memory = await resolve_report_selection(
        db=_FakeDb(_doc(5, report_year=2023)),
        market="CN",
        symbol="600519",
        question="那现金流呢？",
        memory_turns=[{"report_context": {"report_id": 5}}],
    )
    assert by_memory.report_id == 5
    assert by_memory.selection_reason == "session_report_id"

    latest = await resolve_report_selection(
        db=_FakeDb(_doc(6, report_year=2024, report_type="q3", period_end="2024-09-30")),
        market="CN",
        symbol="600519",
        question="贵州茅台最新财报表现如何？",
    )
    assert latest.report_id == 6
    assert latest.selection_reason == "latest_formal_report"
    assert latest.report_type == "q3"


def test_phase6u_context_parsing_cache_and_fixture_contract():
    from app.agent.report_chat_cache import make_cache_key
    from app.agent.report_context import is_narrow_question, parse_explicit_report_id, parse_explicit_report_type

    assert parse_explicit_report_id("请用 report_id=2 分析") == 2
    assert parse_explicit_report_id("请用 report_id 2 分析") == 2
    assert parse_explicit_report_type("2024 年年报表现如何？") == "annual"
    assert is_narrow_question("现金流怎么样？") is True
    assert is_narrow_question("最新财报整体表现如何？") is False

    k1 = make_cache_key("600519.SH", "现金流", ["annual"], [2024], report_id=1)
    k2 = make_cache_key("600519.SH", "现金流", ["annual"], [2024], report_id=2)
    assert k1 != k2

    fixture = Path(__file__).parents[1] / "fixtures" / "phase6u_report_prompt_cases.json"
    cases = json.loads(fixture.read_text(encoding="utf-8"))
    assert len(cases) == 20
    assert {case["id"] for case in cases}


@pytest.mark.asyncio
async def test_phase6u_agent_uses_selected_report_for_rag_and_schema():
    from app.agent.report_chat_copilot_agent import ReportChatCopilotAgent

    captured = {}

    async def fake_rag_query(**kwargs):
        captured.update(kwargs)
        return {
            "chunks": [_chunk()],
            "partial": False,
            "errors": [],
            "provider": "mock",
            "search_mode": "keyword",
            "fallback_used": False,
        }

    llm_payload = {
        "answer": "## 结论\n2024年年报显示，经营现金流为正。\n\n## 关键数据\n仅基于已接入片段。\n\n## 解释\n不补充未提供数字。\n\n## 数据限制\n缺少结构化财务字段。\n\n## 来源\nchunk 10",
        "confidence": "medium",
        "evidence_used": [{"chunk_id": 10, "reason": "现金流披露"}],
        "data_limitations": ["缺少结构化财务字段"],
        "source_chunks": [{"chunk_id": 10, "citation": "管理层讨论"}],
        "disclaimer": "本内容基于已接入的公开财报片段，仅供参考，不构成投资建议。",
    }

    async def fake_review(analysis, data_pack):
        return {"status": "approved", "final": analysis, "audit": {"source_chunks_checked": True}}

    with patch("app.agent.report_chat_copilot_agent.resolve_report_selection", AsyncMock(return_value=_selection(2))):
        with patch("app.services.report_rag_service.ReportRagService") as MockRag:
            MockRag.return_value.query = fake_rag_query
            with patch("app.llm.deepseek_client.DeepSeekClient") as MockClient:
                MockClient.return_value.chat = MagicMock(return_value=json.dumps(llm_payload, ensure_ascii=False))
                with patch("app.agent.fundamental_review_agent.FundamentalReviewAgent") as MockReview:
                    MockReview.return_value.review = fake_review
                    with patch("app.core.config.settings") as mock_settings:
                        mock_settings.ai_enabled = True
                        mock_settings.ai_api_key = "test"
                        mock_settings.deepseek_model = "test-model"
                        mock_settings.enable_report_chat_cache = False
                        result = await ReportChatCopilotAgent().chat(
                            market="CN",
                            symbol="600519",
                            stock_name="贵州茅台",
                            question="贵州茅台的经营现金流怎么样？",
                            db=MagicMock(),
                            session_id="phase6u",
                        )

    assert captured["report_id"] == 2
    assert captured["report_types"] == ["annual"]
    assert captured["years"] == [2024]
    assert result["memory_meta"]["report_context"]["report_id"] == 2
    for key in {
        "answer",
        "source_chunks",
        "review_audit",
        "rag_status",
        "confidence",
        "evidence_used",
        "data_limitations",
        "disclaimer",
        "errors",
        "partial",
        "cache_meta",
        "memory_meta",
        "safety_meta",
    }:
        assert key in result
    assert result["source_chunks"] == [{"chunk_id": 10, "citation": "管理层讨论"}]
    assert "chain of thought" not in result["answer"].lower()
    assert "/Users/" not in result["answer"]


@pytest.mark.asyncio
async def test_phase6u_rejected_review_downgrades_answer_and_marks_partial():
    from app.agent.report_chat_copilot_agent import ReportChatCopilotAgent

    async def fake_rag_query(**kwargs):
        return {
            "chunks": [_chunk()],
            "partial": False,
            "errors": [],
            "provider": "mock",
            "search_mode": "keyword",
            "fallback_used": False,
        }

    async def fake_review(analysis, data_pack):
        return {"status": "rejected", "final": analysis, "audit": {"source_chunks_checked": False}}

    with patch("app.agent.report_chat_copilot_agent.resolve_report_selection", AsyncMock(return_value=_selection(2))):
        with patch("app.services.report_rag_service.ReportRagService") as MockRag:
            MockRag.return_value.query = fake_rag_query
            with patch("app.llm.deepseek_client.DeepSeekClient") as MockClient:
                MockClient.return_value.chat = MagicMock(return_value=json.dumps({
                    "answer": "2024年年报显示利润大幅改善。",
                    "confidence": "high",
                    "evidence_used": [],
                    "data_limitations": [],
                    "source_chunks": [{"chunk_id": 10, "citation": "管理层讨论"}],
                    "disclaimer": "本内容基于已接入的公开财报片段，仅供参考，不构成投资建议。",
                }, ensure_ascii=False))
                with patch("app.agent.fundamental_review_agent.FundamentalReviewAgent") as MockReview:
                    MockReview.return_value.review = fake_review
                    with patch("app.core.config.settings") as mock_settings:
                        mock_settings.ai_enabled = True
                        mock_settings.ai_api_key = "test"
                        mock_settings.deepseek_model = "test-model"
                        mock_settings.enable_report_chat_cache = False
                        result = await ReportChatCopilotAgent().chat(
                            market="CN",
                            symbol="600519",
                            question="财报表现如何？",
                            db=MagicMock(),
                        )

    assert result["partial"] is True
    assert result["confidence"] == "low"
    assert "证据审核未通过" in result["answer"]
    assert "证据审核未通过，强结论已降级" in result["data_limitations"]


@pytest.mark.asyncio
async def test_phase6u_no_chunks_and_narrow_question_do_not_fabricate_numbers():
    from app.agent.report_chat_copilot_agent import ReportChatCopilotAgent

    async def fake_rag_query(**kwargs):
        return {"chunks": [], "partial": False, "errors": [], "provider": "mock"}

    with patch("app.agent.report_chat_copilot_agent.resolve_report_selection", AsyncMock(return_value=_selection(2))):
        with patch("app.services.report_rag_service.ReportRagService") as MockRag:
            MockRag.return_value.query = fake_rag_query
            with patch("app.core.config.settings") as mock_settings:
                mock_settings.ai_enabled = False
                mock_settings.ai_api_key = None
                result = await ReportChatCopilotAgent().chat(
                    market="CN",
                    symbol="600519",
                    question="毛利率呢？",
                    db=MagicMock(),
                )

    assert result["partial"] is True
    assert "## 结论" in result["answer"]
    assert "## 关键数据" in result["answer"]
    assert "## 结论摘要" not in result["answer"]
    assert "不能编造" in result["answer"] or "不能使用模型记忆" in result["answer"]


@pytest.mark.asyncio
async def test_phase6u_report_explanation_skill_uses_copilot_and_preserves_context():
    from app.agents.chat_skills.base import SkillContext
    from app.agents.chat_skills.report_explanation_skill import ReportExplanationSkill

    captured = {}

    async def fake_chat(**kwargs):
        captured.update(kwargs)
        return {
            "answer": "## 结论\n沿用 2024 年年报回答现金流。",
            "partial": False,
            "report_context": _selection(2, "session_report_id").metadata(),
            "source_chunks": [{"chunk_id": 10}],
            "review_audit": {"source_chunks_checked": True},
            "rag_status": "keyword_only",
            "confidence": "medium",
            "data_limitations": [],
            "errors": [],
            "disclaimer": "本内容基于已接入的公开财报片段，仅供参考，不构成投资建议。",
        }

    memory_context = SimpleNamespace(
        resolved_query="贵州茅台 那现金流呢？",
        active_entities=[SimpleNamespace(type="stock", code="600519", market="CN", name="贵州茅台")],
    )

    with patch("app.agents.chat_skills.report_explanation_skill.ReportChatCopilotAgent") as MockAgent:
        MockAgent.return_value.chat = fake_chat
        result = await ReportExplanationSkill().run(
            "那现金流呢？",
            SkillContext(db=MagicMock(), user_id="u1", session_id="s1", memory_context=memory_context),
        )

    assert result.ok is True
    assert captured["symbol"] == "600519"
    assert captured["market"] == "CN"
    assert captured["stock_name"] == "贵州茅台"
    assert captured["use_memory"] is True
    assert result.data["report_context"]["report_id"] == 2
    assert result.answer.count("不构成投资建议") == 0
    assert "数据来源：" in result.answer


@pytest.mark.asyncio
async def test_phase6u_report_explanation_requires_symbol_and_market():
    from app.agents.chat_skills.base import SkillContext
    from app.agents.chat_skills.report_explanation_skill import ReportExplanationSkill

    result = await ReportExplanationSkill().run(
        "这份报告的现金流怎么样？",
        SkillContext(db=MagicMock(), user_id="u1", session_id="s1"),
    )

    assert result.ok is True
    assert result.data["status"] == "failed"
    assert result.data["partial"] is False
    assert result.data["error_code"] == "ENTITY_NOT_RESOLVED"
    assert "entity_not_resolved" in result.data["errors"]
    assert "请明确" in result.answer


def test_phase6u_prompt_contains_evidence_boundaries_and_no_direct_advice():
    prompt = (Path(__file__).parents[2] / "app" / "agent" / "prompts" / "report_chat_system.md").read_text(encoding="utf-8")
    for phrase in [
        "disclosed_facts",
        "interpretation",
        "data_limitations",
        "禁止使用模型记忆补充财务数字",
        "禁止生成直接买入或卖出指令",
        "## 报告与数据范围",
        "## 来源",
    ]:
        assert phrase in prompt
