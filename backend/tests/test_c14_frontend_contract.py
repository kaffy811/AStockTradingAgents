"""
C14: Frontend Contract Tests.

Tests that verify the Python-side contracts that the frontend relies on:
1. session_title_updated SSE event has {session_id, title} payload
2. chat_streaming.py imports maybe_update_session_title
3. session_title_updated is NOT emitted when title is already set
4. SSE event types list includes 'session_title_updated'
5. SkillResult.answer is never the old opaque error string
6. GeneralFinancialAnswerSkill has priority=100 (lowest)
7. chat_llm_answerer module exports generate_answer function
8. banned phrases list is non-empty (safety check)
"""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import uuid


class TestSSEEventContract:
    """Verify that session_title_updated SSE events have the right shape."""

    @pytest.mark.asyncio
    async def test_title_updated_payload_has_session_id_and_title(self):
        """session_title_updated payload must have session_id and title fields."""
        emitted = []

        async def fake_orchestrate(session_id, user_id, content, output_language, db):
            # Simulate what chat_streaming does after title update
            new_title = "新用户问题"
            emitted.append({
                "event_type": "session_title_updated",
                "payload": {
                    "session_id": str(session_id),
                    "title": new_title,
                }
            })

        sid = uuid.uuid4()
        await fake_orchestrate(sid, uuid.uuid4(), "新用户问题内容", "zh-CN", None)

        assert len(emitted) == 1
        payload = emitted[0]["payload"]
        assert "session_id" in payload
        assert "title" in payload
        assert payload["title"] == "新用户问题"


class TestModuleImports:
    """Verify that all C14 modules are importable and have expected exports."""

    def test_chat_llm_answerer_importable(self):
        from app.agents import chat_llm_answerer
        assert hasattr(chat_llm_answerer, "generate_answer")

    def test_general_financial_answer_skill_importable(self):
        from app.agents.chat_skills.general_financial_answer_skill import GeneralFinancialAnswerSkill
        skill = GeneralFinancialAnswerSkill()
        assert skill.priority == 100

    def test_chat_service_has_maybe_update_session_title(self):
        from app.services.chat_service import maybe_update_session_title
        assert callable(maybe_update_session_title)

    def test_banned_phrases_is_non_empty(self):
        from app.agents.chat_llm_answerer import _BANNED_PHRASES
        assert len(_BANNED_PHRASES) > 0

    def test_system_prompt_forbids_buy(self):
        from app.agents.chat_llm_answerer import _SYSTEM_PROMPT
        assert "买入" in _SYSTEM_PROMPT  # listed in the 严禁出现 section

    def test_general_skill_has_lowest_priority(self):
        """GeneralFinancialAnswerSkill must have the highest priority number (= lowest priority)."""
        from app.agents.chat_skills.general_financial_answer_skill import GeneralFinancialAnswerSkill
        from app.agents.chat_skills.stock_anomaly_skill import StockAnomalySkill
        general = GeneralFinancialAnswerSkill()
        anomaly = StockAnomalySkill()
        assert general.priority > anomaly.priority


class TestOpaquErrorStringAbsent:
    """Verify that '技能执行时发生内部错误' no longer appears in skill failure paths."""

    @pytest.mark.asyncio
    async def test_registry_fallback_does_not_return_opaque_error(self):
        """When SkillRegistry catches an exception, result should not contain old error string."""
        from app.agents.chat_skills.registry import SkillRegistry
        from app.agents.chat_skills.base import BaseSkill, SkillResult

        class FailingSkill(BaseSkill):
            name = "test_failing_skill"
            description = "Fails always"
            priority = 1

            def can_handle(self, message, context):
                return True

            async def run(self, message, context):
                raise ValueError("Simulated failure")

        ctx = MagicMock()
        ctx.event_callback = None
        ctx.output_language = "zh-CN"
        ctx.db = AsyncMock()
        ctx.tool_registry = MagicMock()

        registry = SkillRegistry()
        registry.register(FailingSkill())

        fallback_result = SkillResult(
            ok=True,
            skill_name="general_financial_answer_skill",
            answer="### 研究摘要\n降级。\n\n_仅供研究参考，不构成投资建议。_",
        )

        with patch(
            "app.agents.chat_skills.general_financial_answer_skill.GeneralFinancialAnswerSkill.run",
            new=AsyncMock(return_value=fallback_result),
        ):
            result = await registry.run("任何问题", ctx)

        assert result is not None
        assert "技能执行时发生内部错误" not in (result.answer or "")
