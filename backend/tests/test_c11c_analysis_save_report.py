"""
C11-c: analysis_save_report chain tests.

Verifies that:
1. The "scope" key fix is in place — params.get("scope") not params.get("analysis_scope")
2. save_to_history and requested_from flow through to the tool_event detail
3. Orchestrator sets all required params (market, symbol, name, scope, save_to_history, requested_from)
4. Confirmation dict uses key "type" == "create_analysis_run"
5. execute_create_analysis_run picks up the correct scope from confirmation params
"""

import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ── helpers ───────────────────────────────────────────────────────────────────

def _make_db():
    return AsyncMock()


def _make_user_id():
    return uuid.UUID("00000000-0000-0000-0000-000000000001")


# ── 1. Orchestrator params shape ──────────────────────────────────────────────

class TestOrchestratorConfirmationParams:
    """Confirm the orchestrator sets the right params in the confirmation dict."""

    @pytest.mark.asyncio
    async def test_confirmation_type_key(self):
        from app.agents.chat_orchestrator import _handle_analysis_save_report

        result = await _handle_analysis_save_report(
            "帮我分析茅台的基本面并保存历史报告",
            _make_db(),
            _make_user_id(),
        )
        conf = result.confirmation
        assert conf is not None, "Must return a confirmation dict"
        assert conf.get("type") == "create_analysis_run"

    @pytest.mark.asyncio
    async def test_confirmation_params_contains_required_keys(self):
        from app.agents.chat_orchestrator import _handle_analysis_save_report

        result = await _handle_analysis_save_report(
            "分析贵州茅台基本面并保存到历史报告",
            _make_db(),
            _make_user_id(),
        )
        params = result.confirmation.get("params", {})
        for key in ("market", "symbol", "name", "scope", "save_to_history"):
            assert key in params, f"params must contain '{key}'"

    @pytest.mark.asyncio
    async def test_save_to_history_is_true(self):
        from app.agents.chat_orchestrator import _handle_analysis_save_report

        result = await _handle_analysis_save_report(
            "分析茅台基本面然后保存报告",
            _make_db(),
            _make_user_id(),
        )
        params = result.confirmation.get("params", {})
        assert params.get("save_to_history") is True

    @pytest.mark.asyncio
    async def test_requested_from_is_chat_agent(self):
        from app.agents.chat_orchestrator import _handle_analysis_save_report

        result = await _handle_analysis_save_report(
            "生成报告并保存",
            _make_db(),
            _make_user_id(),
        )
        params = result.confirmation.get("params", {})
        assert params.get("requested_from") == "chat_agent"

    @pytest.mark.asyncio
    async def test_scope_fundamental_when_message_mentions_ji_ben_mian(self):
        from app.agents.chat_orchestrator import _handle_analysis_save_report

        result = await _handle_analysis_save_report(
            "分析贵州茅台的基本面并保存到历史报告",
            _make_db(),
            _make_user_id(),
        )
        params = result.confirmation.get("params", {})
        assert params.get("scope") == "fundamental"

    @pytest.mark.asyncio
    async def test_scope_technical_when_message_mentions_technical(self):
        from app.agents.chat_orchestrator import _handle_analysis_save_report

        result = await _handle_analysis_save_report(
            "帮我做技术面分析并保存历史报告",
            _make_db(),
            _make_user_id(),
        )
        params = result.confirmation.get("params", {})
        assert params.get("scope") == "technical"

    @pytest.mark.asyncio
    async def test_scope_defaults_to_comprehensive(self):
        from app.agents.chat_orchestrator import _handle_analysis_save_report

        result = await _handle_analysis_save_report(
            "生成报告并保存",
            _make_db(),
            _make_user_id(),
        )
        params = result.confirmation.get("params", {})
        assert params.get("scope") == "comprehensive"


# ── 2. execute_create_analysis_run key fix ────────────────────────────────────

class TestExecuteCreateAnalysisRunKeyFix:
    """
    Verify that execute_create_analysis_run reads 'scope' (not 'analysis_scope')
    from params, so a chat-initiated run with scope=fundamental is correctly wired.
    """

    @pytest.mark.asyncio
    async def test_scope_key_is_read_correctly(self):
        """Passing 'scope': 'fundamental' must reach registry.create_run as analysis_scope='fundamental'."""
        from app.agents.chat_tools.action_tools import execute_create_analysis_run

        captured = {}

        async def _fake_create_run(**kw):
            captured.update(kw)
            ref = MagicMock()
            ref.run_id = "run-test-001"
            return ref

        mock_registry = AsyncMock()
        mock_registry.create_run = _fake_create_run

        mock_llm = MagicMock()

        with (
            patch("app.agents.chat_tools.action_tools.get_llm_client", return_value=mock_llm),
            patch("app.agents.chat_tools.action_tools.get_run_registry", return_value=mock_registry),
            patch("app.agents.chat_tools.action_tools.RealtimeAnalysisRunner"),
            patch("asyncio.create_task"),
        ):
            result = await execute_create_analysis_run(
                params={
                    "market": "CN",
                    "symbol": "600519",
                    "name":   "贵州茅台",
                    "scope":  "fundamental",
                    "save_to_history": True,
                    "requested_from":  "chat_agent",
                },
                db=_make_db(),
                user_id=_make_user_id(),
            )

        assert result.ok is True
        assert captured.get("analysis_scope") == "fundamental", (
            f"Expected analysis_scope='fundamental', got {captured.get('analysis_scope')!r}. "
            "Fix: params.get('scope') not params.get('analysis_scope')"
        )

    @pytest.mark.asyncio
    async def test_old_analysis_scope_key_would_default_to_comprehensive(self):
        """
        This is a regression guard: if someone passes 'analysis_scope' directly
        in params (old bug), the result should still be 'comprehensive' because
        the correct key is 'scope'.
        """
        from app.agents.chat_tools.action_tools import execute_create_analysis_run

        captured = {}

        async def _fake_create_run(**kw):
            captured.update(kw)
            ref = MagicMock()
            ref.run_id = "run-test-002"
            return ref

        mock_registry = AsyncMock()
        mock_registry.create_run = _fake_create_run

        with (
            patch("app.agents.chat_tools.action_tools.get_llm_client", return_value=MagicMock()),
            patch("app.agents.chat_tools.action_tools.get_run_registry", return_value=mock_registry),
            patch("app.agents.chat_tools.action_tools.RealtimeAnalysisRunner"),
            patch("asyncio.create_task"),
        ):
            await execute_create_analysis_run(
                params={
                    "market": "CN",
                    "symbol": "000001",
                    "name":   "平安银行",
                    # Note: passing wrong key to simulate old bug
                    "analysis_scope": "technical",
                    # 'scope' is absent — should fall back to 'comprehensive'
                },
                db=_make_db(),
                user_id=_make_user_id(),
            )

        # Without 'scope' key, default must be 'comprehensive'
        assert captured.get("analysis_scope") == "comprehensive"

    @pytest.mark.asyncio
    async def test_save_to_history_appears_in_tool_event(self):
        """save_to_history=True must appear in the tool_event detail string."""
        from app.agents.chat_tools.action_tools import execute_create_analysis_run

        async def _fake_create_run(**kw):
            ref = MagicMock()
            ref.run_id = "run-test-003"
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
                    "market": "CN",
                    "symbol": "600519",
                    "name":   "贵州茅台",
                    "scope":  "comprehensive",
                    "save_to_history": True,
                    "requested_from":  "chat_agent",
                },
                db=_make_db(),
                user_id=_make_user_id(),
            )

        assert result.ok is True
        assert result.tool_events, "Must emit at least one tool_event"
        detail = result.tool_events[0].get("detail", "")
        assert "save_to_history=true" in detail, (
            f"Expected 'save_to_history=true' in tool_event detail, got: {detail!r}"
        )

    @pytest.mark.asyncio
    async def test_requested_from_appears_in_tool_event(self):
        """requested_from=chat_agent must appear in the tool_event detail string."""
        from app.agents.chat_tools.action_tools import execute_create_analysis_run

        async def _fake_create_run(**kw):
            ref = MagicMock()
            ref.run_id = "run-test-004"
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
                    "market": "CN",
                    "symbol": "600519",
                    "name":   "贵州茅台",
                    "scope":  "comprehensive",
                    "save_to_history": True,
                    "requested_from":  "chat_agent",
                },
                db=_make_db(),
                user_id=_make_user_id(),
            )

        detail = result.tool_events[0].get("detail", "")
        assert "chat_agent" in detail, (
            f"Expected 'chat_agent' in tool_event detail, got: {detail!r}"
        )
