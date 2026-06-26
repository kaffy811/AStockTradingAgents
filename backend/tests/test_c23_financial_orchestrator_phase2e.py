"""
tests/test_c23_financial_orchestrator_phase2e.py

Phase 2E-1: Multi-Agent Financial Orchestrator — 10 tests.

T1  Complex query routes to Orchestrator (intent parsing)
T2  Simple quote query does NOT route to Orchestrator
T3  FundamentalAgent: official report not found → status=partial
T4  MarketAgent success: returns data_points with kline stats
T5  NewsAgent not executed when need_news=False
T6  Sub-agent timeout does not crash orchestrator
T7  RiskReview blocks violation phrases
T8  Unverified report → data_quality.report_verified=False
T9  Full SSE event sequence from run_stream
T10 Orchestrator exception → fallback to FinancialAgent in process_message
"""
from __future__ import annotations

import asyncio
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ══════════════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════════════

def _mock_db() -> AsyncMock:
    """Return a minimal async DB mock that never raises."""
    db = AsyncMock()
    mr = MagicMock()
    mr.fetchall.return_value = []
    mr.fetchone.return_value  = None
    db.execute.return_value   = mr
    return db


def _make_tool_result(ok: bool = True, data: dict | None = None, summary: str = "") -> Any:
    """Build a ToolResult-like SimpleNamespace."""
    return SimpleNamespace(ok=ok, data=data or {}, summary=summary, cards=[], error=None)


# ══════════════════════════════════════════════════════════════════════════════
# T1 — Complex query routes to Orchestrator
# ══════════════════════════════════════════════════════════════════════════════

class TestComplexQueryRouting:

    def test_complex_query_is_detected(self):
        """
        茅台2026财报 + 一个月行情 → need_report=True, need_kline=True → complex.
        """
        from app.agents.orchestrator.schemas import (
            build_task_intent, is_complex_financial_query,
        )
        from app.agents.official_report_search import parse_financial_analysis_intent

        query  = "请帮我根据茅台2026财报分析茅台的2026年经营状况，并结合其一个月的股票数据进行分析"
        intent = parse_financial_analysis_intent(query)
        task   = build_task_intent(intent, query)

        assert task["need_report"] is True,   f"need_report should be True, got {task}"
        assert task["need_kline"]  is True,   f"need_kline should be True, got {task}"
        assert task["report_year"] == 2026,   f"report_year should be 2026, got {task}"
        assert task["kline_limit"] >= 20,     f"kline_limit should be ≥20, got {task}"
        assert is_complex_financial_query(task), "Should be classified as complex"

    def test_complex_flags_need_report_and_kline(self):
        from app.agents.orchestrator.schemas import is_complex_financial_query

        # At least 2 signals → complex
        assert is_complex_financial_query({"need_report": True, "need_kline": True})
        assert is_complex_financial_query({"need_report": True, "need_rag": True})
        assert is_complex_financial_query({"need_kline": True, "need_news": True})

    def test_symbol_extracted_for_moutai(self):
        from app.agents.official_report_search import parse_financial_analysis_intent

        query  = "请帮我根据茅台2026财报分析茅台的2026年经营状况，并结合其一个月的股票数据进行分析"
        intent = parse_financial_analysis_intent(query)
        assert intent.get("symbol") == "600519", f"Expected 600519, got {intent}"
        assert intent.get("market") == "CN",     f"Expected CN, got {intent}"


# ══════════════════════════════════════════════════════════════════════════════
# T2 — Simple query does NOT route to Orchestrator
# ══════════════════════════════════════════════════════════════════════════════

class TestSimpleQueryNotOrchestrated:

    def test_simple_price_query_not_complex(self):
        from app.agents.orchestrator.schemas import (
            build_task_intent, is_complex_financial_query,
        )
        from app.agents.official_report_search import parse_financial_analysis_intent

        query  = "AAPL 今天价格多少？"
        intent = parse_financial_analysis_intent(query)
        task   = build_task_intent(intent, query)

        # Simple price query → only need_quote, not complex
        assert not is_complex_financial_query(task), (
            f"Simple query should NOT be complex, got {task}"
        )

    def test_single_flag_not_complex(self):
        from app.agents.orchestrator.schemas import is_complex_financial_query

        # Only 1 signal → not complex
        assert not is_complex_financial_query({"need_report": True})
        assert not is_complex_financial_query({"need_kline": True})
        assert not is_complex_financial_query({})


# ══════════════════════════════════════════════════════════════════════════════
# T3 — FundamentalAgent: official report not found
# ══════════════════════════════════════════════════════════════════════════════

class TestFundamentalAgentReportNotFound:

    @pytest.mark.asyncio
    async def test_report_not_found_is_partial(self):
        from app.agents.orchestrator.fundamental_agent import FundamentalAgent

        # RAG search returns empty results
        async def _empty_rag(query, db, **kwargs):
            return {"ok": True, "results": []}

        agent  = FundamentalAgent(rag_search_fn=_empty_rag)
        intent = {
            "query":       "茅台2026财报分析",
            "symbol":      "600519",
            "market":      "CN",
            "need_report": True,
            "need_rag":    True,
            "report_year": 2026,
            "report_type": "annual_report",
        }
        result = await agent.run(intent, _mock_db())

        assert result["status"] == "partial",               f"status={result['status']}"
        assert "official_report_not_found" in result["risk_flags"], (
            f"risk_flags={result['risk_flags']}"
        )
        assert result["agent_name"] == "fundamental_agent"

    @pytest.mark.asyncio
    async def test_report_not_found_summary_mentions_no_fabrication(self):
        from app.agents.orchestrator.fundamental_agent import FundamentalAgent

        async def _empty_rag(query, db, **kwargs):
            return {"ok": True, "results": []}

        agent  = FundamentalAgent(rag_search_fn=_empty_rag)
        intent = {
            "query": "茅台年报", "symbol": "600519", "market": "CN",
            "need_report": True, "report_year": 2026, "report_type": "annual_report",
        }
        result = await agent.run(intent, _mock_db())

        # Summary must NOT claim analysis was performed on missing data
        assert "官方披露" in result["summary"] or "未找到" in result["summary"] or \
               "不能基于未披露" in result["summary"], (
            f"Summary should mention missing data: {result['summary']}"
        )


# ══════════════════════════════════════════════════════════════════════════════
# T4 — MarketAgent success with mocked kline tool
# ══════════════════════════════════════════════════════════════════════════════

class TestMarketAgentSuccess:

    @pytest.mark.asyncio
    async def test_market_agent_extracts_kline_stats(self):
        from app.agents.orchestrator.market_agent import MarketAgent

        # Build 30 mock bars
        bars = [
            {"high": 1800.0 + i, "low": 1700.0 + i, "volume": 1000000.0 + i * 1000}
            for i in range(5)  # bars_sample is last 5
        ]
        kline_result = _make_tool_result(
            ok=True,
            data={
                "bars_count":        30,
                "period_change_pct": -3.5,
                "bars_sample":       bars,
            },
            summary="获取 600519 K线数据成功",
        )
        mock_kline_tool = AsyncMock()
        mock_kline_tool.run = AsyncMock(return_value=kline_result)

        agent  = MarketAgent(kline_tool=mock_kline_tool)
        intent = {
            "symbol":     "600519",
            "market":     "CN",
            "need_kline": True,
            "need_quote": False,
            "kline_limit": 30,
        }
        result = await agent.run(intent, _mock_db())

        assert result["status"] == "success",    f"status={result['status']}"
        assert result["agent_name"] == "market_agent"
        assert result["data_quality"].get("market_data_available") is True

        dp_str = " ".join(result["data_points"])
        assert "30" in dp_str or "K线" in dp_str,      f"Missing bars_count in {dp_str}"
        assert "区间涨跌幅" in dp_str or "-3.5" in dp_str, f"Missing change_pct in {dp_str}"
        assert "最高价" in dp_str,                        f"Missing high in {dp_str}"
        assert "最低价" in dp_str,                        f"Missing low in {dp_str}"


# ══════════════════════════════════════════════════════════════════════════════
# T5 — NewsAgent not executed when need_news=False
# ══════════════════════════════════════════════════════════════════════════════

class TestNewsAgentSkipped:

    @pytest.mark.asyncio
    async def test_news_agent_not_run_when_not_needed(self):
        """Orchestrator should not call NewsAgent when intent.need_news=False."""
        from app.agents.orchestrator.news_agent import NewsAgent

        run_called = []

        class _MockNewsAgent:
            async def run(self, intent, db, **kwargs):
                run_called.append(True)
                return {"agent_name": "news_agent", "status": "success"}

        # Build a mock orchestrator with need_news=False
        from app.agents.orchestrator.financial_orchestrator import FinancialOrchestrator
        from app.agents.orchestrator.synthesis_agent import SynthesisAgent
        from app.agents.orchestrator.risk_review_agent import RiskReviewAgent
        from app.agents.orchestrator.fundamental_agent import FundamentalAgent
        from app.agents.orchestrator.market_agent import MarketAgent

        # FundamentalAgent returns success
        async def _rag_ok(query, db, **kwargs):
            return {"ok": True, "results": []}

        # MarketAgent mock returns success
        kline_result = _make_tool_result(
            ok=True,
            data={"bars_count": 10, "period_change_pct": 1.0, "bars_sample": []},
        )
        mock_kline = AsyncMock()
        mock_kline.run = AsyncMock(return_value=kline_result)

        orch = FinancialOrchestrator(
            _mock_db(),
            fundamental_agent=FundamentalAgent(rag_search_fn=_rag_ok),
            market_agent=MarketAgent(kline_tool=mock_kline),
            news_agent=_MockNewsAgent(),
            risk_review_agent=RiskReviewAgent(),
            synthesis_agent=SynthesisAgent(),
        )

        # Directly test: intent.need_news=False means news agent tasks list is empty
        intent = {
            "query":           "茅台2026财报",
            "symbol":          "600519",
            "market":          "CN",
            "need_fundamental": True,
            "need_market":     True,
            "need_news":       False,
            "need_report":     True,
            "need_kline":      True,
            "need_rag":        True,
            "need_quote":      False,
            "report_year":     2026,
            "report_type":     "annual_report",
            "kline_period":    "daily",
            "kline_limit":     30,
            "risk_level":      "normal",
        }

        # Patch intent parsing inside run_stream
        with patch(
            "app.agents.orchestrator.financial_orchestrator.build_task_intent",
            return_value=intent,
        ):
            with patch(
                "app.agents.orchestrator.financial_orchestrator.parse_financial_analysis_intent",
                return_value=intent,
            ):
                await orch.run_stream("茅台2026财报", "req-test")

        assert not run_called, "NewsAgent.run should NOT have been called"


# ══════════════════════════════════════════════════════════════════════════════
# T6 — Sub-agent timeout does not crash orchestrator
# ══════════════════════════════════════════════════════════════════════════════

class TestAgentTimeoutNoCrash:

    @pytest.mark.asyncio
    async def test_fundamental_timeout_still_returns_final_answer(self):
        from app.agents.orchestrator.financial_orchestrator import FinancialOrchestrator
        from app.agents.orchestrator.risk_review_agent import RiskReviewAgent
        from app.agents.orchestrator.synthesis_agent import SynthesisAgent
        from app.agents.orchestrator.market_agent import MarketAgent

        class _SlowFundamental:
            async def run(self, intent, db, **kwargs):
                await asyncio.sleep(999)  # will be cancelled by timeout
                return {}

        kline_result = _make_tool_result(
            ok=True,
            data={"bars_count": 5, "period_change_pct": 0.5, "bars_sample": []},
        )
        mock_kline = AsyncMock()
        mock_kline.run = AsyncMock(return_value=kline_result)

        events: list[dict] = []

        async def _cb(event_type: str, payload: dict) -> None:
            events.append({"event_type": event_type, **payload})

        orch = FinancialOrchestrator(
            _mock_db(),
            fundamental_agent=_SlowFundamental(),
            market_agent=MarketAgent(kline_tool=mock_kline),
            risk_review_agent=RiskReviewAgent(),
            synthesis_agent=SynthesisAgent(),
        )

        intent = {
            "query": "test", "symbol": "600519", "market": "CN",
            "need_fundamental": True, "need_market": True, "need_news": False,
            "need_report": True, "need_kline": True, "need_rag": True,
            "need_quote": False, "report_year": 2026, "report_type": "annual_report",
            "kline_period": "daily", "kline_limit": 5, "risk_level": "normal",
        }

        with patch(
            "app.agents.orchestrator.financial_orchestrator.build_task_intent",
            return_value=intent,
        ):
            with patch(
                "app.agents.orchestrator.financial_orchestrator.parse_financial_analysis_intent",
                return_value=intent,
            ):
                result = await orch.run_stream("test", "req-t6", _cb)

        # Must complete — no exception propagated
        assert "final_answer" in result
        # timeout warning in evidence pack → final_answer still sent
        final_event_types = [e["event_type"] for e in events]
        assert "final_answer"   in final_event_types, f"events: {final_event_types}"
        assert "agent_completed" in final_event_types, f"events: {final_event_types}"

        # Check agent_timeout warning propagated
        timeout_events = [
            e for e in events
            if e.get("event_type") == "subagent_result"
            and "agent_timeout" in e.get("risk_flags", [])
        ]
        assert timeout_events, "Expected subagent_result with agent_timeout"


# ══════════════════════════════════════════════════════════════════════════════
# T7 — RiskReviewAgent blocks violation phrases
# ══════════════════════════════════════════════════════════════════════════════

class TestRiskReviewBlocks:

    @pytest.mark.asyncio
    async def test_buy_recommendation_is_blocked(self):
        from app.agents.orchestrator.risk_review_agent import RiskReviewAgent

        agent        = RiskReviewAgent()
        evidence_pack = {"findings": [], "sources": [], "data_quality": {}, "warnings": []}
        draft_text   = "综合来看，强烈建议买入，必涨，稳赚不赔。"

        result = await agent.run(evidence_pack, draft_text)

        assert result["blocked"] is True, f"Should be blocked; result={result}"
        assert result["issues"],          f"Should have issues; result={result}"

    @pytest.mark.asyncio
    async def test_required_edits_listed_for_violations(self):
        from app.agents.orchestrator.risk_review_agent import RiskReviewAgent

        agent        = RiskReviewAgent()
        evidence_pack = {"findings": [], "sources": [], "data_quality": {}, "warnings": []}
        draft_text   = "建议买入茅台，目标价 2000 元。"

        result = await agent.run(evidence_pack, draft_text)

        assert result["issues"] or result["required_edits"], (
            "Should have issues or required_edits for violation phrases"
        )

    @pytest.mark.asyncio
    async def test_neutral_text_passes(self):
        from app.agents.orchestrator.risk_review_agent import RiskReviewAgent

        agent        = RiskReviewAgent()
        evidence_pack = {
            "findings": [], "sources": [{"title": "test"}],
            "data_quality": {}, "warnings": [],
        }
        draft_text   = "基于研究数据，茅台2026年营收增长显著，值得持续关注。仅供研究参考，不构成投资建议。"

        result = await agent.run(evidence_pack, draft_text)

        assert result["blocked"] is False, f"Neutral text should not be blocked: {result}"


# ══════════════════════════════════════════════════════════════════════════════
# T8 — Unverified report flagged in data_quality
# ══════════════════════════════════════════════════════════════════════════════

class TestUnverifiedReportDataQuality:

    def test_unverified_source_sets_report_verified_false(self):
        from app.agents.orchestrator.schemas import make_evidence_pack

        finding = {
            "agent_name":   "fundamental_agent",
            "status":       "partial",
            "summary":      "数据基于非官方来源",
            "evidence":     [],
            "data_points":  [],
            "risk_flags":   ["official_report_not_found"],
            "sources":      [{"verified": False, "source_level": "general"}],
            "data_quality": {"report_verified": False},
        }
        pack = make_evidence_pack("茅台分析", {}, [finding])

        assert pack["data_quality"]["report_verified"] is False, (
            f"report_verified should be False: {pack['data_quality']}"
        )

    @pytest.mark.asyncio
    async def test_risk_review_notes_unverified_fundamental(self):
        from app.agents.orchestrator.risk_review_agent import RiskReviewAgent
        from app.agents.orchestrator.schemas import make_evidence_pack

        finding = {
            "agent_name":   "fundamental_agent",
            "status":       "partial",
            "summary":      "基于公开信息分析",
            "evidence":     [],
            "data_points":  [],
            "risk_flags":   ["official_report_not_found"],
            "sources":      [{"verified": False}],
            "data_quality": {"report_verified": False},
        }
        pack  = make_evidence_pack("茅台分析", {}, [finding])
        agent = RiskReviewAgent()
        result = await agent.run(pack, "")

        # Should produce compliance_notes about unverified data
        all_issues = result["compliance_notes"] + result["required_edits"]
        assert any("未经官方" in n or "验证" in n or "非官方" in n for n in all_issues), (
            f"Expected unverified data compliance note; got: {all_issues}"
        )

    @pytest.mark.asyncio
    async def test_synthesis_marks_data_quality_unverified(self):
        from app.agents.orchestrator.synthesis_agent import SynthesisAgent
        from app.agents.orchestrator.schemas import make_evidence_pack, make_risk_review_result

        finding = {
            "agent_name":   "fundamental_agent",
            "status":       "partial",
            "summary":      "基于公开信息",
            "evidence":     [],
            "data_points":  [],
            "risk_flags":   ["official_report_not_found"],
            "sources":      [],
            "data_quality": {"report_verified": False},
        }
        pack   = make_evidence_pack("茅台分析", {"symbol": "600519"}, [finding])
        review = make_risk_review_result(passed=False, blocked=False,
                                         compliance_notes=["数据未经官方验证"])

        agent  = SynthesisAgent()
        result = await agent.run(pack, review)

        assert result["data_quality"].get("report_verified") is False, (
            f"data_quality.report_verified should be False: {result['data_quality']}"
        )


# ══════════════════════════════════════════════════════════════════════════════
# T9 — Full SSE event sequence from run_stream
# ══════════════════════════════════════════════════════════════════════════════

class TestSSEEventSequence:

    @pytest.mark.asyncio
    async def test_event_sequence_includes_all_required_types(self):
        from app.agents.orchestrator.financial_orchestrator import FinancialOrchestrator
        from app.agents.orchestrator.risk_review_agent import RiskReviewAgent
        from app.agents.orchestrator.synthesis_agent import SynthesisAgent
        from app.agents.orchestrator.fundamental_agent import FundamentalAgent

        async def _empty_rag(query, db, **kwargs):
            return {"ok": True, "results": []}

        events: list[str] = []

        async def _cb(event_type: str, payload: dict) -> None:
            events.append(event_type)

        intent = {
            "query": "茅台分析", "symbol": "600519", "market": "CN",
            "need_fundamental": True, "need_market": False, "need_news": False,
            "need_report": True, "need_kline": False, "need_rag": True,
            "need_quote": False, "report_year": 2026, "report_type": "annual_report",
            "kline_period": "daily", "kline_limit": 30, "risk_level": "normal",
        }

        orch = FinancialOrchestrator(
            _mock_db(),
            fundamental_agent=FundamentalAgent(rag_search_fn=_empty_rag),
            risk_review_agent=RiskReviewAgent(),
            synthesis_agent=SynthesisAgent(),
        )

        with patch(
            "app.agents.orchestrator.financial_orchestrator.build_task_intent",
            return_value=intent,
        ):
            with patch(
                "app.agents.orchestrator.financial_orchestrator.parse_financial_analysis_intent",
                return_value=intent,
            ):
                await orch.run_stream("茅台分析", "req-t9", _cb)

        # Required event types
        required = [
            "orchestrator_start",
            "subagent_start",
            "subagent_result",
            "risk_review_start",
            "risk_review_result",
            "synthesis_start",
            "final_answer",
            "agent_completed",
        ]
        for etype in required:
            assert etype in events, (
                f"Missing event type {etype!r}; got: {events}"
            )

        # Order constraints: orchestrator_start must be first
        assert events[0] == "orchestrator_start", (
            f"First event should be orchestrator_start; got: {events[0]}"
        )
        # final_answer before agent_completed
        fa_idx   = events.index("final_answer")
        done_idx = events.index("agent_completed")
        assert fa_idx < done_idx, "final_answer should precede agent_completed"


# ══════════════════════════════════════════════════════════════════════════════
# T10 — Orchestrator exception → fallback to FinancialAgent in process_message
# ══════════════════════════════════════════════════════════════════════════════

class TestOrchestratorFallback:

    @pytest.mark.asyncio
    async def test_fallback_when_orchestrator_raises(self):
        """
        When FinancialOrchestrator.run_stream raises, process_message
        must fall back to existing SkillRegistry path and return an answer.
        """
        from app.agents.chat_orchestrator import process_message

        db      = _mock_db()
        user_id = uuid.uuid4()

        # Enable orchestrator
        with patch(
            "app.agents.orchestrator.financial_orchestrator.is_orchestrator_enabled",
            return_value=True,
        ):
            # Make orchestrator raise
            with patch(
                "app.agents.orchestrator.financial_orchestrator.FinancialOrchestrator",
            ) as MockOrch:
                mock_instance = MagicMock()
                mock_instance.run_stream = AsyncMock(side_effect=RuntimeError("boom"))
                MockOrch.return_value = mock_instance

                # Also need is_complex to return True to enter orchestrator path
                with patch(
                    "app.agents.orchestrator.schemas.is_complex_financial_query",
                    return_value=True,
                ):
                    # SkillRegistry must return something
                    with patch(
                        "app.agents.chat_orchestrator._skill_registry.run",
                    ) as mock_skill_run:
                        from dataclasses import dataclass

                        @dataclass
                        class _FakeSkillResult:
                            answer: str = "Fallback answer."
                            tool_events: list = None
                            cards: list = None
                            confirmation: object = None
                            metadata: dict = None
                            skill_name: str = "fallback_skill"
                            safety_flags: list = None

                            def __post_init__(self):
                                if self.tool_events is None: self.tool_events = []
                                if self.cards is None: self.cards = []
                                if self.metadata is None: self.metadata = {}
                                if self.safety_flags is None: self.safety_flags = []

                        mock_skill_run.return_value = _FakeSkillResult()

                        result = await process_message(
                            "请帮我根据茅台2026财报分析茅台的2026年经营状况，并结合其一个月的股票数据进行分析",
                            db,
                            user_id,
                        )

        # Fallback must produce an answer (not crash)
        assert result is not None
        assert hasattr(result, "answer")
        assert result.answer  # non-empty answer


# ══════════════════════════════════════════════════════════════════════════════
# Type helper import
# ══════════════════════════════════════════════════════════════════════════════

from typing import Any  # noqa: E402 — must be at module level for isinstance checks
