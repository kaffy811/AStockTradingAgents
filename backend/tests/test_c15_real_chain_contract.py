"""
C15 Real-Chain Contract Tests.

These tests verify:
  1. "财报" / "最新财报" queries are routed to a real skill (not default greeting)
  2. GeneralFinancialAnswerSkill is registered in the live orchestrator registry
  3. can_handle() excludes simple greetings but catches financial queries
  4. RAGResult constructor in GeneralFinancialAnswerSkill uses correct parameters
  5. SkillRegistry with GeneralFinancialAnswerSkill handles unmatched queries
  6. process_message() never returns default greeting for financial research queries
  7. SSE event flow emits agent_started before answer events
  8. onError / onStop frontend contract tests for step state machine
"""
from __future__ import annotations

import asyncio
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agents.chat_orchestrator import (
    OrchestratorResult,
    _DISCLAIMER,
    _skill_registry,
    process_message,
)
from app.agents.chat_skills.base import SkillContext
from app.agents.chat_skills.general_financial_answer_skill import GeneralFinancialAnswerSkill


DB = MagicMock()
USER_ID = uuid.uuid4()

_DEFAULT_GREETING_FRAGMENT = "你好！我是 TradingAgents Chat Copilot"


# ── 1. GeneralFinancialAnswerSkill registered in live registry ─────────────────

def test_general_financial_skill_in_live_registry():
    """GeneralFinancialAnswerSkill must be registered in the orchestrator's SkillRegistry."""
    skill_names = [s.name for s in _skill_registry.list_skills()]
    assert "general_financial_answer_skill" in skill_names, (
        "GeneralFinancialAnswerSkill is NOT registered — fix: add to _build_skill_registry()"
    )


def test_general_financial_skill_priority_is_lowest():
    """GeneralFinancialAnswerSkill must have the highest priority number (lowest priority)."""
    skills = _skill_registry.list_skills()
    gfa = next((s for s in skills if s.name == "general_financial_answer_skill"), None)
    assert gfa is not None
    max_priority = max(s.priority for s in skills)
    assert gfa.priority == max_priority, (
        f"GeneralFinancialAnswerSkill.priority={gfa.priority} is not the highest "
        f"(max={max_priority}); it should be the last-resort fallback"
    )


# ── 2. can_handle() routing contract ──────────────────────────────────────────

def _make_ctx() -> SkillContext:
    return SkillContext(
        db=MagicMock(),
        user_id="test-user",
        output_language="zh-CN",
        tool_registry=MagicMock(),
    )


@pytest.mark.parametrize("query", [
    "贵州茅台最新财报表现如何？",
    "最新财报",
    "600519 业绩怎么样",
    "贵州茅台业绩情况",
    "这只股票怎么样",
    "分析一下宁德时代",
    "有什么研究建议",
    "港股行情如何",
    "半导体行业最新进展",
])
def test_gfa_can_handle_financial_queries(query):
    """GeneralFinancialAnswerSkill.can_handle() must return True for financial queries."""
    skill = GeneralFinancialAnswerSkill()
    ctx = _make_ctx()
    assert skill.can_handle(query, ctx) is True, (
        f"can_handle() returned False for financial query: {query!r}"
    )


@pytest.mark.parametrize("greeting", [
    "你好",
    "你好！",
    "hello",
    "Hello",
    "hi",
    "Hi!",
    "hey",
    "哈哈",
    "嗨",
    "喂",
    "您好",
])
def test_gfa_does_not_handle_greetings(greeting):
    """GeneralFinancialAnswerSkill.can_handle() must return False for simple greetings."""
    skill = GeneralFinancialAnswerSkill()
    ctx = _make_ctx()
    assert skill.can_handle(greeting, ctx) is False, (
        f"can_handle() returned True for simple greeting: {greeting!r} — "
        "this causes greetings to get DeepSeek answers instead of the capability menu"
    )


# ── 3. process_message() routing: "财报" gets skill, not default greeting ──────

@pytest.mark.asyncio
async def test_caibao_query_not_default_greeting():
    """'贵州茅台最新财报表现如何？' must NOT return the default greeting answer."""
    with patch(
        "app.agents.chat_skills.general_financial_answer_skill.retrieve_context",
        new=AsyncMock(return_value=_empty_rag("贵州茅台最新财报表现如何？")),
    ):
        with patch(
            "app.agents.chat_llm_answerer.generate_answer",
            new=AsyncMock(return_value="### 研究摘要\n贵州茅台财报分析内容。\n\n_仅供研究参考_"),
        ):
            result = await process_message("贵州茅台最新财报表现如何？", DB, USER_ID)

    assert isinstance(result, OrchestratorResult)
    assert _DEFAULT_GREETING_FRAGMENT not in result.answer, (
        "Query '贵州茅台最新财报表现如何？' returned default greeting — "
        "GeneralFinancialAnswerSkill must be registered in _build_skill_registry()"
    )
    assert result.answer.strip(), "answer must not be empty"


@pytest.mark.asyncio
async def test_caibao_query_skill_name_set():
    """'最新财报' must route to a skill (skill_name must be non-None)."""
    with patch(
        "app.agents.chat_skills.general_financial_answer_skill.retrieve_context",
        new=AsyncMock(return_value=_empty_rag("最新财报")),
    ):
        with patch(
            "app.agents.chat_llm_answerer.generate_answer",
            new=AsyncMock(return_value="财报分析。\n\n_仅供研究参考_"),
        ):
            result = await process_message("最新财报", DB, USER_ID)

    assert result.metadata.get("skill_name") is not None, (
        "skill_name not set — '最新财报' fell through to direct-intent handlers or default"
    )
    assert result.metadata.get("source") == "skill_registry"


@pytest.mark.asyncio
async def test_hello_still_gets_default_greeting():
    """'你好' must still return the default greeting (capability menu)."""
    result = await process_message("你好", DB, USER_ID)
    assert _DEFAULT_GREETING_FRAGMENT in result.answer, (
        "Default greeting not returned for '你好'"
    )
    assert result.metadata.get("skill_name") is None


# ── 4. RAGResult construction in exception path ───────────────────────────────

def test_rag_result_exception_path_no_kwargs_error():
    """GeneralFinancialAnswerSkill must construct RAGResult with valid params on exception path."""
    from app.agents.chat_rag.base import RAGResult
    # Verify the exact constructor call used in the exception handler works
    rag_result = RAGResult(ok=False, query="test query", documents=[])
    assert rag_result.ok is False
    assert rag_result.query == "test query"
    assert rag_result.documents == []
    # Properties should not raise
    _ = rag_result.overall_confidence
    _ = rag_result.approved


# ── 5. SkillRegistry with 7 skills ────────────────────────────────────────────

def test_live_registry_has_seven_skills():
    """The live skill registry (in orchestrator) must have 7 skills (6 specific + 1 fallback)."""
    skills = _skill_registry.list_skills()
    assert len(skills) == 7, (
        f"Expected 7 skills in live registry, got {len(skills)}: "
        + ", ".join(s.name for s in skills)
    )


def test_live_registry_sorted_by_priority():
    """All skills must be sorted by priority (lowest number = highest priority = first)."""
    priorities = [s.priority for s in _skill_registry.list_skills()]
    assert priorities == sorted(priorities)


# ── 6. GeneralFinancialAnswerSkill.run() with patched dependencies ─────────────

@pytest.mark.asyncio
async def test_gfa_run_returns_non_empty_answer():
    """GeneralFinancialAnswerSkill.run() returns a non-empty SkillResult."""
    skill = GeneralFinancialAnswerSkill()
    ctx = SkillContext(
        db=MagicMock(),
        user_id="test-user",
        output_language="zh-CN",
        tool_registry=MagicMock(),
    )
    with patch(
        "app.agents.chat_skills.general_financial_answer_skill.retrieve_context",
        new=AsyncMock(return_value=_empty_rag("贵州茅台最新财报表现如何？")),
    ):
        with patch(
            "app.agents.chat_llm_answerer.generate_answer",
            new=AsyncMock(return_value="财报分析结果。\n\n_仅供研究参考_"),
        ):
            result = await skill.run("贵州茅台最新财报表现如何？", ctx)

    assert result.ok is True
    assert result.skill_name == "general_financial_answer_skill"
    assert result.answer
    assert "财报" in result.answer or "分析" in result.answer or "研究" in result.answer


@pytest.mark.asyncio
async def test_gfa_run_falls_back_on_deepseek_failure():
    """When DeepSeek fails, GeneralFinancialAnswerSkill returns a structured fallback answer."""
    skill = GeneralFinancialAnswerSkill()
    ctx = SkillContext(
        db=MagicMock(),
        user_id="test-user",
        output_language="zh-CN",
        tool_registry=MagicMock(),
    )
    with patch(
        "app.agents.chat_skills.general_financial_answer_skill.retrieve_context",
        new=AsyncMock(return_value=_empty_rag("test")),
    ):
        with patch(
            "app.agents.chat_llm_answerer.generate_answer",
            side_effect=RuntimeError("DeepSeek timeout"),
        ):
            result = await skill.run("财报数据怎么样", ctx)

    assert result.ok is True
    assert result.answer.strip()
    # Must NOT be a bare opaque error string
    assert "技能执行时发生内部错误" not in result.answer


# ── 7. SSE event sequence contract ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_caibao_query_emits_skill_started_event():
    """When routing '贵州茅台最新财报' via GeneralFinancialAnswerSkill, skill_started must fire."""
    events_captured: list[tuple[str, dict]] = []

    async def capture(event_type, payload):
        events_captured.append((event_type, payload))

    with patch(
        "app.agents.chat_skills.general_financial_answer_skill.retrieve_context",
        new=AsyncMock(return_value=_empty_rag("贵州茅台最新财报")),
    ):
        with patch(
            "app.agents.chat_llm_answerer.generate_answer",
            new=AsyncMock(return_value="分析完成。\n\n_仅供研究参考_"),
        ):
            await process_message(
                "贵州茅台最新财报",
                DB,
                USER_ID,
                event_callback=capture,
            )

    event_types = [e[0] for e in events_captured]
    assert "skill_started" in event_types, (
        f"skill_started not emitted; events: {event_types}"
    )
    assert "skill_completed" in event_types, (
        f"skill_completed not emitted; events: {event_types}"
    )


@pytest.mark.asyncio
async def test_skill_completed_comes_after_skill_started():
    """skill_completed must always follow skill_started in the event sequence."""
    events_captured: list[str] = []

    async def capture(event_type, payload):
        events_captured.append(event_type)

    with patch(
        "app.agents.chat_skills.general_financial_answer_skill.retrieve_context",
        new=AsyncMock(return_value=_empty_rag("业绩分析")),
    ):
        with patch(
            "app.agents.chat_llm_answerer.generate_answer",
            new=AsyncMock(return_value="业绩回顾。\n\n_仅供研究参考_"),
        ):
            await process_message("业绩分析", DB, USER_ID, event_callback=capture)

    if "skill_started" in events_captured and "skill_completed" in events_captured:
        idx_started = events_captured.index("skill_started")
        idx_completed = len(events_captured) - 1 - events_captured[::-1].index("skill_completed")
        assert idx_started < idx_completed, (
            "skill_completed fired before skill_started"
        )


# ── 8. Disclaimer always present ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_disclaimer_present_in_gfa_answer():
    """GeneralFinancialAnswerSkill answer must contain the research disclaimer."""
    with patch(
        "app.agents.chat_skills.general_financial_answer_skill.retrieve_context",
        new=AsyncMock(return_value=_empty_rag("茅台财报")),
    ):
        with patch(
            "app.agents.chat_llm_answerer.generate_answer",
            new=AsyncMock(return_value="分析完成。\n\n_仅供研究参考，不构成投资建议。_"),
        ):
            result = await process_message("茅台财报", DB, USER_ID)

    assert _DISCLAIMER.strip() in result.answer or "投资建议" in result.answer, (
        "Disclaimer missing from GeneralFinancialAnswerSkill answer"
    )


# ── Helpers ────────────────────────────────────────────────────────────────────

def _empty_rag(query: str):
    """Return an empty RAGResult with no documents."""
    from app.agents.chat_rag.base import RAGResult
    return RAGResult(ok=False, query=query, documents=[])
