"""
C14: Fallback Answer (GeneralFinancialAnswerSkill) Tests.

1. GeneralFinancialAnswerSkill.can_handle returns True for any non-empty message
2. GeneralFinancialAnswerSkill.can_handle returns False for empty message
3. GeneralFinancialAnswerSkill.run emits skill_started event
4. GeneralFinancialAnswerSkill.run emits skill_completed event
5. GeneralFinancialAnswerSkill.run returns SkillResult with ok=True
6. GeneralFinancialAnswerSkill.run answer contains disclaimer
7. SkillRegistry.run uses fallback on skill exception instead of returning opaque error
8. SkillRegistry.run fallback answer does not contain '技能执行时发生内部错误'
"""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


def _make_context():
    ctx = MagicMock()
    ctx.event_callback = None
    ctx.output_language = "zh-CN"
    ctx.db = AsyncMock()
    ctx.tool_registry = MagicMock()
    return ctx


class TestGeneralFinancialAnswerSkill:

    def test_can_handle_non_empty(self):
        from app.agents.chat_skills.general_financial_answer_skill import GeneralFinancialAnswerSkill
        skill = GeneralFinancialAnswerSkill()
        assert skill.can_handle("任何问题", _make_context()) is True

    def test_can_handle_empty_returns_false(self):
        from app.agents.chat_skills.general_financial_answer_skill import GeneralFinancialAnswerSkill
        skill = GeneralFinancialAnswerSkill()
        assert skill.can_handle("   ", _make_context()) is False

    @pytest.mark.asyncio
    async def test_run_emits_skill_started(self):
        from app.agents.chat_skills.general_financial_answer_skill import GeneralFinancialAnswerSkill

        events = []

        async def mock_callback(event_type, payload):
            events.append(event_type)

        ctx = _make_context()
        ctx.event_callback = mock_callback

        mock_rag = MagicMock()
        mock_rag.ok = True
        mock_rag.documents = []
        mock_rag.overall_confidence = "medium"
        mock_rag.approved = False

        mock_llm = MagicMock()
        mock_llm.chat_flash.return_value = "### 研究摘要\n测试答案"

        skill = GeneralFinancialAnswerSkill()
        with patch("app.agents.chat_skills.general_financial_answer_skill.retrieve_context", new=AsyncMock(return_value=mock_rag)):
            with patch("app.llm.factory.get_llm_client", return_value=mock_llm):
                result = await skill.run("688146 为什么涨", ctx)

        assert "skill_started" in events

    @pytest.mark.asyncio
    async def test_run_emits_skill_completed(self):
        from app.agents.chat_skills.general_financial_answer_skill import GeneralFinancialAnswerSkill

        events = []

        async def mock_callback(event_type, payload):
            events.append(event_type)

        ctx = _make_context()
        ctx.event_callback = mock_callback

        mock_rag = MagicMock()
        mock_rag.ok = True
        mock_rag.documents = []
        mock_rag.overall_confidence = "medium"
        mock_rag.approved = False

        mock_llm = MagicMock()
        mock_llm.chat_flash.return_value = "### 研究摘要\n测试答案"

        skill = GeneralFinancialAnswerSkill()
        with patch("app.agents.chat_skills.general_financial_answer_skill.retrieve_context", new=AsyncMock(return_value=mock_rag)):
            with patch("app.llm.factory.get_llm_client", return_value=mock_llm):
                result = await skill.run("688146 为什么涨", ctx)

        assert "skill_completed" in events

    @pytest.mark.asyncio
    async def test_run_returns_ok_result(self):
        from app.agents.chat_skills.general_financial_answer_skill import GeneralFinancialAnswerSkill

        ctx = _make_context()

        mock_rag = MagicMock()
        mock_rag.ok = True
        mock_rag.documents = []
        mock_rag.overall_confidence = "medium"
        mock_rag.approved = False

        mock_llm = MagicMock()
        mock_llm.chat_flash.return_value = "### 研究摘要\n研究内容"

        skill = GeneralFinancialAnswerSkill()
        with patch("app.agents.chat_skills.general_financial_answer_skill.retrieve_context", new=AsyncMock(return_value=mock_rag)):
            with patch("app.llm.factory.get_llm_client", return_value=mock_llm):
                result = await skill.run("688146", ctx)

        assert result.ok is True
        assert result.answer

    @pytest.mark.asyncio
    async def test_run_answer_has_disclaimer(self):
        from app.agents.chat_skills.general_financial_answer_skill import GeneralFinancialAnswerSkill

        ctx = _make_context()

        mock_rag = MagicMock()
        mock_rag.ok = True
        mock_rag.documents = []
        mock_rag.overall_confidence = "medium"
        mock_rag.approved = False

        mock_llm = MagicMock()
        mock_llm.chat_flash.return_value = "研究内容"

        skill = GeneralFinancialAnswerSkill()
        with patch("app.agents.chat_skills.general_financial_answer_skill.retrieve_context", new=AsyncMock(return_value=mock_rag)):
            with patch("app.llm.factory.get_llm_client", return_value=mock_llm):
                result = await skill.run("test", ctx)

        assert "仅供研究参考" in result.answer


class TestSkillRegistryFallback:

    @pytest.mark.asyncio
    async def test_registry_uses_fallback_on_skill_exception(self):
        """When a skill raises an exception, SkillRegistry should NOT return '技能执行时发生内部错误'."""
        from app.agents.chat_skills.registry import SkillRegistry
        from app.agents.chat_skills.base import BaseSkill, SkillResult

        class BrokenSkill(BaseSkill):
            name = "broken_skill"
            description = "Always fails"
            priority = 1

            def can_handle(self, message, context):
                return True

            async def run(self, message, context):
                raise RuntimeError("Simulated skill failure")

        ctx = MagicMock()
        ctx.event_callback = None
        ctx.output_language = "zh-CN"
        ctx.db = AsyncMock()
        ctx.tool_registry = MagicMock()

        registry = SkillRegistry()
        registry.register(BrokenSkill())

        # Mock GeneralFinancialAnswerSkill so we don't need real DeepSeek
        fallback_result = SkillResult(
            ok=True,
            skill_name="general_financial_answer_skill",
            answer="### 研究摘要\n\n降级回答。\n\n_仅供研究参考，不构成投资建议。_",
        )

        with patch(
            "app.agents.chat_skills.general_financial_answer_skill.GeneralFinancialAnswerSkill.run",
            new=AsyncMock(return_value=fallback_result),
        ):
            result = await registry.run("688146 涨了为什么", ctx)

        assert result is not None
        assert "技能执行时发生内部错误" not in result.answer
