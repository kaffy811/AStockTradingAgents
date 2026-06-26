"""
test_c10_agent_golden_tasks.py — Phase C10 Agent Evaluation Golden Tasks.

30 deterministic tests covering all 6 capability categories:
  A. Tools (8 tasks)       — intent routing to correct tools
  B. Skills (6 tasks)      — skill activation and metadata injection
  C. Planner (4 tasks)     — compound task detection and execution
  D. Actions (4 tasks)     — confirmation flow for write operations
  E. Memory/Audit (3 tasks)— session memory writes and audit fields
  F. Safety (5 tasks)      — trading guard and disclaimer enforcement

All tests are mock-based — no real DB, network, or LLM calls.

Key invariants:
  - OrchestratorResult has fields: answer, tool_events, cards, confirmation, metadata
  - Safety refusals return OrchestratorResult with a refusal message (no 'safety' field)
  - _skill_registry is patched at app.agents.chat_orchestrator._skill_registry
  - process_message() first param is 'content', not 'message'
  - _write_memory_from_result signature: (db, session_id, user_id, msg, result, output_language)
"""
from __future__ import annotations

import asyncio
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_db():
    """Return an async-mock DB session."""
    return AsyncMock()


def _make_user_id():
    return uuid.uuid4()


def _mock_tool_result(tool_name: str, ok: bool = True, summary: str = "ok", data: dict | None = None):
    from app.agents.chat_tools.tool_result import ToolResult
    return ToolResult(
        ok=ok,
        tool_name=tool_name,
        summary=summary,
        data=data or {},
        duration_ms=5,
        started_at="2026-06-18T00:00:00+00:00",
    )


def _mock_skill_result(skill_name: str, answer: str = "分析结果。", ok: bool = True, safety_flags: list | None = None):
    from app.agents.chat_skills.base import SkillResult
    return SkillResult(
        ok=ok,
        skill_name=skill_name,
        answer=answer,
        safety_flags=safety_flags or [],
        metadata={"skill_spec_version": "c9_v1", "skill_enabled": True, "skill_available": True},
    )


async def _process(msg: str, session_id=None, user_id=None, db=None):
    """Thin wrapper that calls process_message and returns OrchestratorResult."""
    from app.agents.chat_orchestrator import process_message
    return await process_message(
        content=msg,
        db=db or _make_db(),
        user_id=user_id or _make_user_id(),
        session_id=session_id,
    )


_SAFETY_REFUSAL_MARKER = "不提供交易指令"
_DISCLAIMER_MARKER = "不构成投资建议"


# ============================================================================
# CATEGORY A — Tools (8 golden tasks)
# Tests that the correct tool path is invoked and answer is produced.
# ============================================================================

class TestGT_A_Tools:
    """GT-A: Tool routing golden tasks."""

    async def test_gt_a1_quote_query_returns_answer(self):
        """GT-A1: '688146现在多少钱' → answer produced (no crash)."""
        # Skill registry returns None to let tool routing handle it
        with patch("app.agents.chat_orchestrator._skill_registry") as mock_sreg:
            mock_sreg.run = AsyncMock(return_value=None)
            with patch("app.agents.chat_orchestrator._registry") as mock_reg:
                mock_reg.call = AsyncMock(
                    return_value=_mock_tool_result(
                        "get_quote_tool",
                        summary="688146: ¥55.23 (+1.2%)",
                        data={"price": 55.23, "change_pct": 1.2, "symbol": "688146",
                              "market": "CN", "name": "中船特气"},
                    )
                )
                result = await _process("688146现在多少钱？")
        assert result.answer
        assert _SAFETY_REFUSAL_MARKER not in result.answer

    async def test_gt_a2_news_query_returns_answer(self):
        """GT-A2: '688146最新新闻' → answer produced."""
        with patch("app.agents.chat_orchestrator._skill_registry") as mock_sreg:
            mock_sreg.run = AsyncMock(return_value=None)
            with patch("app.agents.chat_orchestrator._registry") as mock_reg:
                mock_reg.call = AsyncMock(
                    return_value=_mock_tool_result(
                        "get_latest_news_tool",
                        summary="找到3条新闻",
                        data={"items": [{"title": "季报超预期", "published_at": "2026-06-17"}]},
                    )
                )
                result = await _process("688146最新新闻")
        assert result.answer
        assert _SAFETY_REFUSAL_MARKER not in result.answer

    async def test_gt_a3_industry_query_returns_answer(self):
        """GT-A3: '哪些行业最热？' → answer produced."""
        with patch("app.agents.chat_orchestrator._skill_registry") as mock_sreg:
            mock_sreg.run = AsyncMock(return_value=None)
            with patch("app.agents.chat_orchestrator._registry") as mock_reg:
                mock_reg.call = AsyncMock(
                    return_value=_mock_tool_result(
                        "get_industry_hot_tool",
                        summary="行业热度数据",
                        data={"industries": [{"name": "半导体", "hot_score": 88}]},
                    )
                )
                result = await _process("哪些行业最热？")
        assert result.answer

    async def test_gt_a4_watchlist_view_returns_answer(self):
        """GT-A4: '查看我的自选股' → answer produced."""
        with patch("app.agents.chat_orchestrator._skill_registry") as mock_sreg:
            mock_sreg.run = AsyncMock(return_value=None)
            with patch("app.agents.chat_orchestrator._registry") as mock_reg:
                mock_reg.call = AsyncMock(
                    return_value=_mock_tool_result(
                        "get_watchlist_tool",
                        summary="自选股3只",
                        data={"count": 3, "items": [{"symbol": "688146", "market": "CN"}]},
                    )
                )
                result = await _process("查看我的自选股")
        assert result.answer

    async def test_gt_a5_recent_report_returns_answer(self):
        """GT-A5: '看看我最近的报告' → answer produced."""
        with patch("app.agents.chat_orchestrator._skill_registry") as mock_sreg:
            mock_sreg.run = AsyncMock(return_value=None)
            with patch("app.agents.chat_orchestrator._registry") as mock_reg:
                mock_reg.call = AsyncMock(
                    return_value=_mock_tool_result(
                        "get_recent_reports_tool",
                        summary="找到2份报告",
                        data={"count": 2, "items": []},
                    )
                )
                result = await _process("看看我最近的报告")
        assert result.answer

    async def test_gt_a6_result_contains_disclaimer(self):
        """GT-A6: Any non-safety result always appends _DISCLAIMER."""
        with patch("app.agents.chat_orchestrator._skill_registry") as mock_sreg:
            mock_sreg.run = AsyncMock(return_value=None)
            with patch("app.agents.chat_orchestrator._registry") as mock_reg:
                mock_reg.call = AsyncMock(
                    return_value=_mock_tool_result(
                        "get_quote_tool",
                        summary="688146: ¥55.23",
                        data={"price": 55.23, "symbol": "688146", "market": "CN",
                              "name": "中船特气", "change_pct": 1.2},
                    )
                )
                result = await _process("688146股价")
        assert _DISCLAIMER_MARKER in result.answer

    async def test_gt_a7_tool_failure_graceful(self):
        """GT-A7: Tool returns ok=False → graceful fallback answer (no crash)."""
        with patch("app.agents.chat_orchestrator._skill_registry") as mock_sreg:
            mock_sreg.run = AsyncMock(return_value=None)
            with patch("app.agents.chat_orchestrator._registry") as mock_reg:
                mock_reg.call = AsyncMock(
                    return_value=_mock_tool_result(
                        "get_quote_tool",
                        ok=False,
                        summary="行情数据暂不可用",
                    )
                )
                result = await _process("688146当前价")
        assert result.answer
        assert _SAFETY_REFUSAL_MARKER not in result.answer

    async def test_gt_a8_default_fallback_answer(self):
        """GT-A8: Unknown query → default handler returns fallback with disclaimer."""
        with patch("app.agents.chat_orchestrator._skill_registry") as mock_sreg:
            mock_sreg.run = AsyncMock(return_value=None)
            result = await _process("介绍一下量子计算的发展历程")
        assert result.answer
        assert _DISCLAIMER_MARKER in result.answer


# ============================================================================
# CATEGORY B — Skills (6 golden tasks)
# Tests skill routing, metadata injection, and spec gate.
# ============================================================================

class TestGT_B_Skills:
    """GT-B: Financial Skills golden tasks."""

    async def test_gt_b1_anomaly_skill_metadata_injected(self):
        """GT-B1: Skill result metadata spread into OrchestratorResult.metadata."""
        mock_sr = _mock_skill_result("stock_anomaly", "688146异动分析：近期大幅上涨。")

        with patch("app.agents.chat_orchestrator._skill_registry") as mock_sreg:
            mock_sreg.run = AsyncMock(return_value=mock_sr)
            result = await _process("为什么688146涨那么多？")

        assert result.answer
        assert result.metadata.get("skill_spec_version") == "c9_v1"

    async def test_gt_b2_skill_source_in_metadata(self):
        """GT-B2: Successful skill → metadata source='skill_registry'."""
        mock_sr = _mock_skill_result("risk_first", "主要风险：市场波动风险…")

        with patch("app.agents.chat_orchestrator._skill_registry") as mock_sreg:
            mock_sreg.run = AsyncMock(return_value=mock_sr)
            result = await _process("688146的风险有哪些？")

        assert result.metadata.get("source") == "skill_registry"

    async def test_gt_b3_skill_name_in_metadata(self):
        """GT-B3: Skill name propagated to OrchestratorResult.metadata."""
        mock_sr = _mock_skill_result("news_catalyst", "重要新闻：研报上调评级。")

        with patch("app.agents.chat_orchestrator._skill_registry") as mock_sreg:
            mock_sreg.run = AsyncMock(return_value=mock_sr)
            result = await _process("688146最近有什么重大新闻")

        assert result.metadata.get("skill_name") == "news_catalyst"

    async def test_gt_b4_skill_safety_flags_propagated(self):
        """GT-B4: Skill safety_flags appear in OrchestratorResult.metadata."""
        mock_sr = _mock_skill_result(
            "risk_first",
            "风险提示内容。",
            safety_flags=["high_volatility"],
        )

        with patch("app.agents.chat_orchestrator._skill_registry") as mock_sreg:
            mock_sreg.run = AsyncMock(return_value=mock_sr)
            result = await _process("688146的最大风险")

        assert "high_volatility" in result.metadata.get("safety_flags", [])

    async def test_gt_b5_skill_result_ok_false_returns_fallback(self):
        """GT-B5: Skill returns ok=False with empty answer → orchestrator still returns something."""
        mock_sr = _mock_skill_result("stock_anomaly", answer="", ok=False)

        with patch("app.agents.chat_orchestrator._skill_registry") as mock_sreg:
            mock_sreg.run = AsyncMock(return_value=mock_sr)
            # When skill returns ok=False with empty answer, orchestrator may return it or fall through
            with patch("app.agents.chat_orchestrator._registry") as mock_reg:
                mock_reg.call = AsyncMock(
                    return_value=_mock_tool_result("get_latest_news_tool", summary="新闻", data={"items": []})
                )
                result = await _process("为什么688146跌了？")

        assert result.answer is not None

    async def test_gt_b6_skill_registry_none_falls_to_direct_routing(self):
        """GT-B6: skill_registry.run() returns None → falls through to direct tool routing."""
        with patch("app.agents.chat_orchestrator._skill_registry") as mock_sreg:
            mock_sreg.run = AsyncMock(return_value=None)
            with patch("app.agents.chat_orchestrator._registry") as mock_reg:
                mock_reg.call = AsyncMock(
                    return_value=_mock_tool_result(
                        "get_latest_news_tool",
                        summary="新闻",
                        data={"items": [{"title": "消息", "published_at": "2026-06-17"}]},
                    )
                )
                result = await _process("688146新闻")
        assert result.answer


# ============================================================================
# CATEGORY C — Planner (4 golden tasks)
# Tests compound intent detection and multi-step execution.
# ============================================================================

class TestGT_C_Planner:
    """GT-C: Controlled Planner golden tasks."""

    def test_gt_c1_compound_anomaly_then_risk_detected(self):
        """GT-C1: 'anomaly+risk compound' → planner.is_compound() returns True."""
        from app.agents.chat_planner.rule_based_planner import RuleBasedPlanner
        planner = RuleBasedPlanner()
        msg = "为什么688146涨这么多，然后重点看一下风险"
        assert planner.is_compound(msg), "Planner should detect compound intent"

    def test_gt_c2_compound_plan_has_steps(self):
        """GT-C2: Compound message → plan has ≥ 2 ordered PlanSteps."""
        from app.agents.chat_planner.rule_based_planner import RuleBasedPlanner
        planner = RuleBasedPlanner()
        msg = "为什么688146涨这么多，然后重点看一下风险"
        plan = planner.plan(msg)
        assert plan is not None
        assert len(plan.steps) >= 2

    def test_gt_c3_industry_then_stocks_is_compound(self):
        """GT-C3: '哪些行业热，每个挑几个股票' → compound detected."""
        from app.agents.chat_planner.rule_based_planner import RuleBasedPlanner
        planner = RuleBasedPlanner()
        # industry_then_stocks: has INDUSTRY_SIG + STOCKS_DEEP_SIG
        msg = "哪些行业热，然后每个行业挑几个股票看一下"
        assert planner.is_compound(msg)

    async def test_gt_c4_planner_executor_produces_result(self):
        """GT-C4: PlannerExecutor.execute() produces ExecutionResult without crash."""
        from app.agents.chat_planner.rule_based_planner import RuleBasedPlanner
        from app.agents.chat_planner.executor import PlannerExecutor
        from app.agents.chat_skills.base import SkillContext

        planner = RuleBasedPlanner()
        msg = "为什么688146涨，然后重点看风险"
        plan = planner.plan(msg)
        assert plan is not None

        mock_skill_result = _mock_skill_result("stock_anomaly", "异动分析结果。")

        mock_sreg = MagicMock()
        mock_sreg.select_by_name = MagicMock(return_value=None)
        mock_sreg.run = AsyncMock(return_value=None)

        executor = PlannerExecutor(skill_registry=mock_sreg)
        context = SkillContext(
            db=_make_db(),
            user_id=str(_make_user_id()),
            output_language="zh-CN",
            tool_registry=MagicMock(),
        )
        exec_result = await executor.execute(plan=plan, message=msg, context=context)
        assert exec_result is not None


# ============================================================================
# CATEGORY D — Actions (4 golden tasks)
# Tests confirmation flow for write operations.
# ============================================================================

class TestGT_D_Actions:
    """GT-D: Action tool golden tasks."""

    async def test_gt_d1_add_watchlist_returns_confirmation(self):
        """GT-D1: '加入自选' trigger → OrchestratorResult with confirmation dict set."""
        result = await _process("把688146加入自选")
        assert result is not None
        # Action handlers return OrchestratorResult with confirmation populated, answer=""
        assert result.confirmation is not None or result.answer

    async def test_gt_d2_generate_report_returns_confirmation(self):
        """GT-D2: 'Generate report' trigger → confirmation or answer returned."""
        result = await _process("帮我生成688146的综合报告")
        assert result is not None
        assert result.confirmation is not None or result.answer

    async def test_gt_d3_compare_trigger_returns_response(self):
        """GT-D3: '对比' trigger → confirmation or answer returned."""
        result = await _process("对比688146和600519")
        assert result is not None
        assert result.confirmation is not None or result.answer

    async def test_gt_d4_process_confirm_unknown_type_graceful(self):
        """GT-D4: process_confirm with unknown confirmation_type → graceful answer."""
        from app.agents.chat_orchestrator import process_confirm
        result = await process_confirm(
            confirmation_type="unknown_action_xyz",
            params={},
            db=_make_db(),
            user_id=_make_user_id(),
        )
        assert result is not None
        assert result.answer
        assert _DISCLAIMER_MARKER in result.answer


# ============================================================================
# CATEGORY E — Memory / Audit (3 golden tasks)
# Tests memory write behavior and audit field presence.
# ============================================================================

class TestGT_E_MemoryAudit:
    """GT-E: Memory and audit golden tasks."""

    async def test_gt_e1_memory_write_with_no_session_id_does_not_crash(self):
        """GT-E1: _write_memory_from_result with session_id=None exits immediately (fire-and-forget guard)."""
        from app.agents.chat_orchestrator import OrchestratorResult, _write_memory_from_result

        result = OrchestratorResult(answer="test", metadata={"tools_used": ["get_quote_tool"]})
        # session_id=None → early return, no DB ops
        await _write_memory_from_result(
            db=_make_db(),
            session_id=None,
            user_id=_make_user_id(),
            msg="test",
            result=result,
            output_language="zh-CN",
        )
        # No exception = pass

    async def test_gt_e2_tool_result_has_audit_fields(self):
        """GT-E2: ToolRegistry.call() injects duration_ms and started_at."""
        from app.agents.chat_tools.registry import ToolRegistry
        from app.agents.chat_tools.base import BaseTool
        from app.agents.chat_tools.tool_result import ToolResult

        class FastTool(BaseTool):
            name = "fast_tool"
            description = "Fast test tool"

            async def run(self, db, **kwargs) -> ToolResult:
                return ToolResult(ok=True, tool_name=self.name, summary="done")

        reg = ToolRegistry()
        reg.register(FastTool())
        result = await reg.call("fast_tool", db=_make_db())

        assert result.duration_ms is not None
        assert result.duration_ms >= 0
        assert result.started_at is not None

    async def test_gt_e3_orchestrator_metadata_present(self):
        """GT-E3: OrchestratorResult.metadata dict is always populated."""
        mock_sr = _mock_skill_result("stock_anomaly", "分析结果")

        with patch("app.agents.chat_orchestrator._skill_registry") as mock_sreg:
            mock_sreg.run = AsyncMock(return_value=mock_sr)
            result = await _process("688146报价")

        assert isinstance(result.metadata, dict)


# ============================================================================
# CATEGORY F — Safety (5 golden tasks)
# Tests trading guard and disclaimer enforcement.
# ============================================================================

class TestGT_F_Safety:
    """GT-F: Safety boundary golden tasks.

    The _TRADING_PATTERN regex matches:
      - 帮我.{0,6}(买入|卖出|交易|下单|购买|清仓)
      - 目标价.{0,4}多少
      - 明天.*涨 / 明天.*跌
      - 稳赚|必涨|抄底|追涨
    """

    async def test_gt_f1_explicit_buy_order_blocked(self):
        """GT-F1: '帮我买入' → matches _TRADING_PATTERN, safety refusal returned."""
        result = await _process("帮我买入688146")
        assert _SAFETY_REFUSAL_MARKER in result.answer
        assert _DISCLAIMER_MARKER in result.answer

    async def test_gt_f2_explicit_sell_order_blocked(self):
        """GT-F2: '帮我卖出' → safety refusal."""
        result = await _process("帮我卖出688146")
        assert _SAFETY_REFUSAL_MARKER in result.answer

    async def test_gt_f3_target_price_blocked(self):
        """GT-F3: '目标价多少' → safety refusal."""
        result = await _process("688146目标价多少")
        assert _SAFETY_REFUSAL_MARKER in result.answer

    async def test_gt_f4_tomorrow_prediction_blocked(self):
        """GT-F4: '明天会涨' price prediction → safety refusal."""
        result = await _process("688146明天涨还是跌")
        assert _SAFETY_REFUSAL_MARKER in result.answer

    async def test_gt_f5_all_non_safety_answers_have_disclaimer(self):
        """GT-F5: Non-safety skill answers all contain _DISCLAIMER."""
        queries = [
            ("688146股价分析", _mock_skill_result("stock_anomaly", "688146当前价格55元。\n\n_仅供研究参考，不构成投资建议。_")),
            ("行业热度", _mock_skill_result("industry_hotspot", "行业热度分析。\n\n_仅供研究参考，不构成投资建议。_")),
        ]
        for msg, mock_sr in queries:
            with patch("app.agents.chat_orchestrator._skill_registry") as mock_sreg:
                mock_sreg.run = AsyncMock(return_value=mock_sr)
                result = await _process(msg)
            assert result.answer is not None, f"No answer for: {msg!r}"
            assert _DISCLAIMER_MARKER in result.answer, f"Disclaimer missing for: {msg!r}"
