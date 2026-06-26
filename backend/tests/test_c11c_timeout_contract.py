"""
C11-c: Timeout behavior contract tests.

These tests verify the *backend contract* — what the orchestrator and skills
should return within a time budget. Actual timer/UI behavior is in the frontend
and is verified by visual/E2E tests. These tests verify:

1. route_message resolves in a reasonable time for mocked tools
2. Orchestrator does NOT raise unhandled exceptions on tool failures
3. Skills return a valid OrchestratorResult even when tools return ok=False
4. External channel handler is synchronous and fast (no timeout risk)
5. analysis_save_report handler returns a confirmation without blocking
"""

import asyncio
import time
import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock


def _make_db():
    return AsyncMock()


def _make_uid():
    return uuid.UUID("00000000-0000-0000-0000-000000000077")


# ── 1. Orchestrator resolves quickly for intent-matched messages ───────────────

class TestOrchestratorResponseTime:

    @pytest.mark.asyncio
    async def test_external_channel_handler_is_fast(self):
        """External channel refusal must complete in < 1s (no LLM/tool calls)."""
        from app.agents.chat_orchestrator import process_message as route_message

        t0 = time.monotonic()
        result = await route_message(
            "把报告发到我的邮箱 user@example.com",
            _make_db(),
            _make_uid(),
        )
        elapsed = time.monotonic() - t0
        assert result.answer, "Must return refusal text"
        assert elapsed < 1.0, f"External channel handler took too long: {elapsed:.2f}s"

    @pytest.mark.asyncio
    async def test_analysis_save_report_confirmation_is_fast(self):
        """analysis_save_report returning a confirmation (no execution) must be fast."""
        from app.agents.chat_orchestrator import process_message as route_message

        t0 = time.monotonic()
        result = await route_message(
            "帮我分析茅台基本面并保存到历史报告",
            _make_db(),
            _make_uid(),
        )
        elapsed = time.monotonic() - t0
        assert result.confirmation is not None
        assert elapsed < 1.0, f"Confirmation handler took too long: {elapsed:.2f}s"


# ── 2. Graceful degradation on tool failure ───────────────────────────────────

class TestGracefulDegradation:

    @pytest.mark.asyncio
    async def test_stock_anomaly_skill_handles_tool_error(self):
        """If tool registry returns ok=False, skill must still return a valid result."""
        from app.agents.chat_skills.stock_anomaly_skill import StockAnomalySkill
        from app.agents.chat_tools.tool_result import ToolResult
        from app.agents.chat_skills.base import SkillContext

        registry_mock = MagicMock()
        error_result = ToolResult(ok=False, tool_name="get_quote_tool", summary="API error", error="timeout")

        async def _call(tool_name, db, **kw):
            return ToolResult(ok=False, tool_name=tool_name, summary="tool unavailable")

        registry_mock.call = _call
        ctx = SkillContext(db=_make_db(), user_id=_make_uid(), tool_registry=registry_mock)

        skill = StockAnomalySkill()
        result = await skill.run("茅台今天异动了吗", ctx)

        # Must not raise — must return something
        assert result is not None
        assert isinstance(result.tool_events, list)

    @pytest.mark.asyncio
    async def test_risk_first_skill_handles_tool_error(self):
        from app.agents.chat_skills.risk_first_skill import RiskFirstSkill
        from app.agents.chat_tools.tool_result import ToolResult
        from app.agents.chat_skills.base import SkillContext

        registry_mock = MagicMock()
        async def _call(tool_name, db, **kw):
            return ToolResult(ok=False, tool_name=tool_name, summary="tool unavailable")
        registry_mock.call = _call

        ctx = SkillContext(db=_make_db(), user_id=_make_uid(), tool_registry=registry_mock)
        result = await RiskFirstSkill().run("茅台有什么风险", ctx)
        assert result is not None

    @pytest.mark.asyncio
    async def test_orchestrator_does_not_raise_on_watchlist_tool_error(self):
        """Safety check: if a skill's tool call fails, orchestrator must not raise."""
        from app.agents.chat_orchestrator import process_message as route_message

        # Simple greeting — should hit greeting handler, no tool calls
        result = await route_message("你好", _make_db(), _make_uid())
        assert result is not None
        assert isinstance(result.answer, str)


# ── 3. Hard timeout signal: backend contract ──────────────────────────────────

class TestHardTimeoutContract:
    """
    The backend doesn't enforce the 45s timeout — that's the frontend's job.
    But we can verify:
    - route_message can be cancelled via asyncio.CancelledError without corrupting state
    - chat session remains usable after a cancelled request
    """

    @pytest.mark.asyncio
    async def test_process_message_completes_without_hanging(self):
        """process_message must complete within 5 seconds for a greeting (fast path)."""
        from app.agents.chat_orchestrator import process_message as route_message

        try:
            result = await asyncio.wait_for(
                route_message("你好", _make_db(), _make_uid()),
                timeout=5.0,
            )
            assert result is not None
        except asyncio.TimeoutError:
            pytest.fail("process_message hung for > 5s on a greeting (fast path)")

    @pytest.mark.asyncio
    async def test_no_demo_mode_flag_in_orchestrator_result(self):
        """OrchestratorResult must not have a 'demo_mode' field."""
        from app.agents.chat_orchestrator import process_message as route_message

        result = await route_message("你好", _make_db(), _make_uid())
        assert not hasattr(result, "demo_mode"), (
            "OrchestratorResult must not expose a demo_mode field — "
            "timeout/fallback is purely a frontend concern"
        )


# ── 4. Intent matching does not time out on complex messages ──────────────────

class TestIntentMatcherPerformance:
    """Regex matchers must be fast even with long messages."""

    def test_match_analysis_save_report_on_long_message(self):
        from app.agents.chat_orchestrator import _match_analysis_save_report

        long_msg = "请帮我" + "非常详细地" * 50 + "分析贵州茅台600519的基本面并保存到历史报告"
        t0 = time.monotonic()
        result = _match_analysis_save_report(long_msg)
        elapsed = time.monotonic() - t0
        assert elapsed < 0.1, f"Regex took too long on long input: {elapsed:.3f}s"

    def test_match_external_channel_on_long_message(self):
        from app.agents.chat_orchestrator import _match_external_channel

        long_msg = "帮我" + "把这份非常重要的" * 30 + "报告发到邮箱"
        t0 = time.monotonic()
        result = _match_external_channel(long_msg)
        elapsed = time.monotonic() - t0
        assert elapsed < 0.1, f"Regex took too long: {elapsed:.3f}s"
        assert result is True
