"""
C12: Analysis Save to History — E2E Contract Tests.

Verifies the complete "analyze + save to history" workflow:
1. Intent detection for "分析并保存到历史报告"
2. Confirmation params include all required fields
3. execute_create_analysis_run creates a real analysis run
4. Analysis run card links to /history
5. Answer does NOT say "已保存成功" before actual completion
6. action audit contains correct fields
"""

import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


def _make_uid():
    return uuid.UUID("00000000-0000-0000-0000-000000000042")


def _make_db():
    return AsyncMock()


# ── 1. E2E intent → confirmation → action ────────────────────────────────────

class TestAnalysisSaveE2E:

    @pytest.mark.asyncio
    async def test_full_intent_produces_confirmation(self):
        """The user intent 'analyze Maotai fundamental + save' must produce a confirmation."""
        from app.agents.chat_orchestrator import process_message

        result = await process_message(
            "请帮我分析茅台的基本面，并帮我放到历史报告当中。",
            _make_db(),
            _make_uid(),
        )
        assert result.confirmation is not None, "Must return a confirmation for save intent"
        assert result.confirmation.get("type") == "create_analysis_run"

    @pytest.mark.asyncio
    async def test_confirmation_params_all_required_fields(self):
        """Confirmation params must include all required fields for audit."""
        from app.agents.chat_orchestrator import process_message

        result = await process_message(
            "帮我做一个茅台的技术面报告并保存到历史报告中",
            _make_db(),
            _make_uid(),
        )
        params = result.confirmation.get("params", {})
        required_fields = ["market", "symbol", "name", "scope", "save_to_history", "requested_from"]
        for field in required_fields:
            assert field in params, f"Missing required param: {field}"

    @pytest.mark.asyncio
    async def test_save_to_history_is_true_in_params(self):
        """save_to_history must be True in confirmation params."""
        from app.agents.chat_orchestrator import process_message

        result = await process_message(
            "分析贵州茅台基本面并保存到历史报告",
            _make_db(),
            _make_uid(),
        )
        assert result.confirmation.get("params", {}).get("save_to_history") is True

    @pytest.mark.asyncio
    async def test_requested_from_is_chat_agent(self):
        """requested_from must be 'chat_agent' in confirmation params."""
        from app.agents.chat_orchestrator import process_message

        result = await process_message(
            "分析茅台基本面然后保存历史报告",
            _make_db(),
            _make_uid(),
        )
        assert result.confirmation.get("params", {}).get("requested_from") == "chat_agent"

    @pytest.mark.asyncio
    async def test_scope_fundamental_when_mentioned(self):
        """Scope must be 'fundamental' when user mentions 基本面."""
        from app.agents.chat_orchestrator import process_message

        result = await process_message(
            "帮我分析贵州茅台的基本面并保存到历史报告",
            _make_db(),
            _make_uid(),
        )
        assert result.confirmation.get("params", {}).get("scope") == "fundamental"

    @pytest.mark.asyncio
    async def test_scope_technical_when_mentioned(self):
        """Scope must be 'technical' when user mentions 技术面."""
        from app.agents.chat_orchestrator import process_message

        result = await process_message(
            "帮我做一个技术面分析并保存到历史报告",
            _make_db(),
            _make_uid(),
        )
        assert result.confirmation.get("params", {}).get("scope") == "technical"


# ── 2. execute_create_analysis_run contract ───────────────────────────────────

class TestExecuteCreateAnalysisRun:

    @pytest.mark.asyncio
    async def test_creates_analysis_run_with_correct_scope(self):
        """execute_create_analysis_run must pass scope=fundamental to registry."""
        from app.agents.chat_tools.action_tools import execute_create_analysis_run

        captured = {}

        async def _fake_create_run(**kw):
            captured.update(kw)
            ref = MagicMock()
            ref.run_id = "run-e2e-001"
            return ref

        mock_registry = AsyncMock()
        mock_registry.create_run = _fake_create_run

        with (
            patch("app.agents.chat_tools.action_tools.get_llm_client", return_value=MagicMock()),
            patch("app.agents.chat_tools.action_tools.get_run_registry", return_value=mock_registry),
            patch("app.agents.chat_tools.action_tools.RealtimeAnalysisRunner"),
            patch("asyncio.create_task"),
        ):
            result = await execute_create_analysis_run(
                params={
                    "market": "CN", "symbol": "600519", "name": "贵州茅台",
                    "scope": "fundamental",
                    "save_to_history": True, "requested_from": "chat_agent",
                },
                db=_make_db(),
                user_id=_make_uid(),
            )

        assert result.ok is True
        assert captured.get("analysis_scope") == "fundamental"

    @pytest.mark.asyncio
    async def test_result_card_links_to_history(self):
        """analysis_run card must include a link to /history."""
        from app.agents.chat_tools.action_tools import execute_create_analysis_run

        async def _fake_create_run(**kw):
            ref = MagicMock()
            ref.run_id = "run-e2e-002"
            return ref

        mock_registry = AsyncMock()
        mock_registry.create_run = _fake_create_run

        with (
            patch("app.agents.chat_tools.action_tools.get_llm_client", return_value=MagicMock()),
            patch("app.agents.chat_tools.action_tools.get_run_registry", return_value=mock_registry),
            patch("app.agents.chat_tools.action_tools.RealtimeAnalysisRunner"),
            patch("asyncio.create_task"),
        ):
            result = await execute_create_analysis_run(
                params={
                    "market": "CN", "symbol": "600519", "name": "贵州茅台",
                    "scope": "comprehensive",
                },
                db=_make_db(),
                user_id=_make_uid(),
            )

        assert result.cards, "Must return at least one card"
        card = result.cards[0]
        assert card.get("type") == "analysis_run"
        links = card.get("data", {}).get("links", [])
        assert any("/history" in (lnk.get("path") or "") for lnk in links), (
            "analysis_run card must link to /history"
        )

    @pytest.mark.asyncio
    async def test_answer_does_not_say_saved_successfully(self):
        """
        Answer must NOT say '已保存成功' — report is queued, not completed.
        The truth is: report will be in /history after 30-60 seconds.
        """
        from app.agents.chat_tools.action_tools import execute_create_analysis_run

        async def _fake_create_run(**kw):
            ref = MagicMock()
            ref.run_id = "run-e2e-003"
            return ref

        mock_registry = AsyncMock()
        mock_registry.create_run = _fake_create_run

        with (
            patch("app.agents.chat_tools.action_tools.get_llm_client", return_value=MagicMock()),
            patch("app.agents.chat_tools.action_tools.get_run_registry", return_value=mock_registry),
            patch("app.agents.chat_tools.action_tools.RealtimeAnalysisRunner"),
            patch("asyncio.create_task"),
        ):
            result = await execute_create_analysis_run(
                params={
                    "market": "CN", "symbol": "600519", "name": "贵州茅台",
                    "scope": "comprehensive", "save_to_history": True,
                },
                db=_make_db(),
                user_id=_make_uid(),
            )

        # Must NOT claim completion
        assert "已保存成功" not in result.answer, (
            "Answer must not say '已保存成功' — report is async and not yet complete"
        )
        assert "已完成" not in result.answer or "约 30" in result.answer, (
            "If answer mentions completion, it must also indicate async wait time"
        )

    @pytest.mark.asyncio
    async def test_tool_event_includes_audit_fields(self):
        """Tool event detail must include save_to_history and requested_from."""
        from app.agents.chat_tools.action_tools import execute_create_analysis_run

        async def _fake_create_run(**kw):
            ref = MagicMock()
            ref.run_id = "run-e2e-004"
            return ref

        mock_registry = AsyncMock()
        mock_registry.create_run = _fake_create_run

        with (
            patch("app.agents.chat_tools.action_tools.get_llm_client", return_value=MagicMock()),
            patch("app.agents.chat_tools.action_tools.get_run_registry", return_value=mock_registry),
            patch("app.agents.chat_tools.action_tools.RealtimeAnalysisRunner"),
            patch("asyncio.create_task"),
        ):
            result = await execute_create_analysis_run(
                params={
                    "market": "CN", "symbol": "600519", "name": "贵州茅台",
                    "scope": "fundamental",
                    "save_to_history": True, "requested_from": "chat_agent",
                },
                db=_make_db(),
                user_id=_make_uid(),
            )

        detail = result.tool_events[0].get("detail", "")
        assert "save_to_history=true" in detail
        assert "chat_agent" in detail


# ── 3. Banned phrases in analysis run answers ─────────────────────────────────

class TestAnalysisRunBannedPhrases:

    BANNED = [
        "买入", "卖出", "持有", "清仓", "推荐购买",
        "目标价", "必涨", "必跌", "稳赚", "一定会涨",
    ]

    @pytest.mark.asyncio
    async def test_action_tools_answer_no_banned_phrases(self):
        """execute_create_analysis_run answer must not contain banned trading advice."""
        from app.agents.chat_tools.action_tools import execute_create_analysis_run

        async def _fake_create_run(**kw):
            ref = MagicMock()
            ref.run_id = "run-ban-001"
            return ref

        mock_registry = AsyncMock()
        mock_registry.create_run = _fake_create_run

        with (
            patch("app.agents.chat_tools.action_tools.get_llm_client", return_value=MagicMock()),
            patch("app.agents.chat_tools.action_tools.get_run_registry", return_value=mock_registry),
            patch("app.agents.chat_tools.action_tools.RealtimeAnalysisRunner"),
            patch("asyncio.create_task"),
        ):
            result = await execute_create_analysis_run(
                params={"market": "CN", "symbol": "600519", "name": "贵州茅台", "scope": "comprehensive"},
                db=_make_db(),
                user_id=_make_uid(),
            )

        for word in self.BANNED:
            assert word not in result.answer, (
                f"Banned phrase '{word}' found in analysis run answer: {result.answer!r}"
            )
