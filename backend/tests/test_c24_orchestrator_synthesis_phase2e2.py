"""
tests/test_c24_orchestrator_synthesis_phase2e2.py — Phase 2E-2 Test Suite.

Covers:
  T1  SynthesisAgent LLM success — valid JSON output
  T2  LLM Markdown JSON block parsed correctly
  T3  LLM output with missing fields — safe defaults filled
  T4  LLM output non-JSON — fallback to template (no exception)
  T5  LLM fabricates source URL — filtered out
  T6  post RiskReview cleans violation phrases
  T7  SynthesisAgent timeout — fallback template, final_answer still emitted
  T8  All 6 new SSE event types emitted by orchestrator (end-to-end)
  T9  subagent_result payload has display_name + sources_count
  T10 Without orchestrator enabled, orchestrator events not emitted
  T11 Full regression — existing 1113 tests must still pass (run separately)

Run:
    uv run pytest tests/test_c24_orchestrator_synthesis_phase2e2.py -v
"""
from __future__ import annotations

import asyncio
import json
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ── Fixtures & helpers ─────────────────────────────────────────────────────────

def _mock_db():
    db = AsyncMock()
    db.execute = AsyncMock(return_value=SimpleNamespace(
        scalars=lambda: SimpleNamespace(all=lambda: []),
        scalar_one_or_none=lambda: None,
        scalar=lambda: None,
    ))
    db.commit  = AsyncMock()
    db.refresh = AsyncMock()
    db.add     = MagicMock()
    return db


def _make_evidence_pack(
    *,
    findings=None,
    sources=None,
    data_quality=None,
    warnings=None,
):
    return {
        "query":        "茅台2026年经营分析",
        "intent":       {"symbol": "600519", "market": "CN", "company_name": "贵州茅台"},
        "findings":     findings or [],
        "sources":      sources or [],
        "data_quality": data_quality or {"report_verified": False, "warnings": []},
        "warnings":     warnings or [],
    }


def _make_risk_review(*, passed=True, blocked=False, issues=None, required_edits=None):
    return {
        "passed":          passed,
        "blocked":         blocked,
        "issues":          issues or [],
        "required_edits":  required_edits or [],
        "compliance_notes": [],
    }


# ══════════════════════════════════════════════════════════════════════════════
# T1 — SynthesisAgent: LLM returns valid JSON
# ══════════════════════════════════════════════════════════════════════════════

class TestSynthesisLLMSuccess:

    @pytest.mark.asyncio
    async def test_llm_json_parsed_correctly(self):
        from app.agents.orchestrator.synthesis_agent import SynthesisAgent

        llm_output = json.dumps({
            "summary":            "茅台2026年经营稳健。",
            "business_analysis":  "收入增长符合预期，利润率维持高位。",
            "market_analysis":    "近一个月股价区间震荡。",
            "news_analysis":      "",
            "linkage_analysis":   "基本面与行情均较为稳定。",
            "data_points":        ["收入增长5%", "净利润率45%"],
            "risk_points":        ["宏观经济波动风险"],
            "sources":            [],
            "data_quality":       {"report_verified": False},
            "disclaimer":         "仅供研究参考，不构成投资建议。",
        })

        async def _fake_llm(prompt: str) -> str:
            return llm_output

        agent = SynthesisAgent(llm_fn=_fake_llm)
        ep    = _make_evidence_pack()
        rr    = _make_risk_review()

        result = await agent.run(ep, rr)

        assert result["summary"] == "茅台2026年经营稳健。"
        assert result["business_analysis"] == "收入增长符合预期，利润率维持高位。"
        assert result["linkage_analysis"]  == "基本面与行情均较为稳定。"
        assert "仅供研究参考" in result["disclaimer"]
        assert isinstance(result["data_points"], list)

    @pytest.mark.asyncio
    async def test_disclaimer_always_present(self):
        from app.agents.orchestrator.synthesis_agent import SynthesisAgent

        # LLM omits disclaimer
        async def _fake_llm(prompt: str) -> str:
            return json.dumps({
                "summary": "Test summary.",
                "business_analysis": "ok",
                "market_analysis": "ok",
                "news_analysis": "",
                "linkage_analysis": "",
                "data_points": [],
                "risk_points": [],
                "sources": [],
                "data_quality": {},
                # No disclaimer field
            })

        agent = SynthesisAgent(llm_fn=_fake_llm)
        result = await agent.run(_make_evidence_pack(), _make_risk_review())
        assert "仅供研究参考" in result.get("disclaimer", "")


# ══════════════════════════════════════════════════════════════════════════════
# T2 — parse_synthesis_llm_output: Markdown JSON block
# ══════════════════════════════════════════════════════════════════════════════

class TestSynthesisMarkdownJSON:

    def test_markdown_json_block_parsed(self):
        from app.agents.orchestrator.synthesis_agent import parse_synthesis_llm_output

        markdown_output = """这是我的分析：

```json
{
  "summary": "综合研究摘要",
  "business_analysis": "基本面稳健",
  "market_analysis": "行情平稳",
  "news_analysis": "",
  "linkage_analysis": "联动分析",
  "data_points": ["数据1"],
  "risk_points": [],
  "sources": [],
  "data_quality": {},
  "disclaimer": "仅供研究参考，不构成投资建议。"
}
```
"""
        ep = _make_evidence_pack()
        result = parse_synthesis_llm_output(markdown_output, ep)

        assert result is not None
        assert result["summary"] == "综合研究摘要"
        assert result["business_analysis"] == "基本面稳健"
        assert result["linkage_analysis"] == "联动分析"

    def test_raw_json_parsed(self):
        from app.agents.orchestrator.synthesis_agent import parse_synthesis_llm_output

        raw = json.dumps({
            "summary": "raw json summary",
            "business_analysis": "b", "market_analysis": "m",
            "news_analysis": "", "linkage_analysis": "l",
            "data_points": [], "risk_points": [],
            "sources": [], "data_quality": {},
            "disclaimer": "仅供研究参考，不构成投资建议。",
        })
        result = parse_synthesis_llm_output(raw, _make_evidence_pack())
        assert result is not None
        assert result["summary"] == "raw json summary"


# ══════════════════════════════════════════════════════════════════════════════
# T3 — parse_synthesis_llm_output: missing fields auto-filled
# ══════════════════════════════════════════════════════════════════════════════

class TestSynthesisMissingFields:

    def test_missing_risk_points_filled(self):
        from app.agents.orchestrator.synthesis_agent import parse_synthesis_llm_output

        # Only minimal fields present
        raw = json.dumps({
            "summary": "minimal",
            "business_analysis": "ba",
        })
        result = parse_synthesis_llm_output(raw, _make_evidence_pack())
        assert result is not None
        assert isinstance(result["risk_points"], list)
        assert isinstance(result["sources"], list)
        assert isinstance(result["data_points"], list)
        assert result.get("disclaimer", "") != ""

    def test_data_quality_inherited_from_evidencepack(self):
        from app.agents.orchestrator.synthesis_agent import parse_synthesis_llm_output

        ep = _make_evidence_pack(data_quality={
            "report_verified": True,
            "warnings": ["some_warning"],
        })
        # LLM returns empty data_quality
        raw = json.dumps({
            "summary": "ok", "business_analysis": "ba",
            "market_analysis": "", "news_analysis": "",
            "linkage_analysis": "", "data_points": [],
            "risk_points": [], "sources": [], "data_quality": {},
            "disclaimer": "仅供研究参考，不构成投资建议。",
        })
        result = parse_synthesis_llm_output(raw, ep)
        assert result is not None
        # EP's report_verified should be inherited
        assert result["data_quality"].get("report_verified") is True
        # EP's warnings must be preserved
        assert "some_warning" in result["data_quality"].get("warnings", [])

    def test_ep_warnings_not_removed_by_llm(self):
        from app.agents.orchestrator.synthesis_agent import parse_synthesis_llm_output

        ep = _make_evidence_pack(data_quality={"warnings": ["critical_warning"]})
        # LLM tries to set empty warnings
        raw = json.dumps({
            "summary": "ok", "business_analysis": "b", "market_analysis": "",
            "news_analysis": "", "linkage_analysis": "", "data_points": [],
            "risk_points": [], "sources": [],
            "data_quality": {"warnings": []},   # LLM tries to clear it
            "disclaimer": "仅供研究参考，不构成投资建议。",
        })
        result = parse_synthesis_llm_output(raw, ep)
        assert result is not None
        assert "critical_warning" in result["data_quality"].get("warnings", [])


# ══════════════════════════════════════════════════════════════════════════════
# T4 — parse_synthesis_llm_output: invalid JSON → returns None
# ══════════════════════════════════════════════════════════════════════════════

class TestSynthesisInvalidJSON:

    def test_garbage_text_returns_none(self):
        from app.agents.orchestrator.synthesis_agent import parse_synthesis_llm_output

        result = parse_synthesis_llm_output("这不是 JSON 格式的文本。", _make_evidence_pack())
        assert result is None

    def test_empty_string_returns_none(self):
        from app.agents.orchestrator.synthesis_agent import parse_synthesis_llm_output

        assert parse_synthesis_llm_output("", _make_evidence_pack()) is None
        assert parse_synthesis_llm_output("   ", _make_evidence_pack()) is None

    @pytest.mark.asyncio
    async def test_invalid_json_falls_back_to_template(self):
        from app.agents.orchestrator.synthesis_agent import SynthesisAgent

        async def _bad_llm(prompt: str) -> str:
            return "这根本不是 JSON，哈哈。"

        agent  = SynthesisAgent(llm_fn=_bad_llm)
        result = await agent.run(_make_evidence_pack(), _make_risk_review())

        # Must not raise; must return a valid response
        assert result is not None
        assert "disclaimer" in result
        assert "仅供研究参考" in result["disclaimer"]


# ══════════════════════════════════════════════════════════════════════════════
# T5 — LLM fabricates source URLs → filtered out
# ══════════════════════════════════════════════════════════════════════════════

class TestSynthesisFabricatedSourceFiltered:

    def test_invented_url_stripped(self):
        from app.agents.orchestrator.synthesis_agent import parse_synthesis_llm_output

        # EvidencePack has one known URL
        ep = _make_evidence_pack(sources=[
            {"title": "Real Report", "url": "https://real.example.com/report.pdf",
             "source": "cninfo", "published_at": "2026-04-01"},
        ])

        # LLM output includes the real URL plus an invented one
        raw = json.dumps({
            "summary": "s", "business_analysis": "b", "market_analysis": "",
            "news_analysis": "", "linkage_analysis": "", "data_points": [],
            "risk_points": [],
            "sources": [
                {"title": "Real Report",    "url": "https://real.example.com/report.pdf"},
                {"title": "Invented Report", "url": "https://llm-invented.fake/report.pdf"},
                {"title": "No URL source",  "url": ""},   # no-URL → allowed
            ],
            "data_quality": {},
            "disclaimer": "仅供研究参考，不构成投资建议。",
        })

        result = parse_synthesis_llm_output(raw, ep)
        assert result is not None

        result_urls = [s.get("url", "") for s in result["sources"]]
        assert "https://llm-invented.fake/report.pdf" not in result_urls, (
            "Invented URL must be filtered"
        )
        assert "https://real.example.com/report.pdf" in result_urls, (
            "Known URL must be preserved"
        )

    def test_all_invented_urls_falls_back_to_ep_sources(self):
        from app.agents.orchestrator.synthesis_agent import parse_synthesis_llm_output

        ep = _make_evidence_pack(sources=[
            {"title": "EP Source", "url": "https://ep.real.com/doc.pdf",
             "source": "sse", "published_at": "2026-04-01"},
        ])
        raw = json.dumps({
            "summary": "s", "business_analysis": "b", "market_analysis": "",
            "news_analysis": "", "linkage_analysis": "", "data_points": [],
            "risk_points": [],
            "sources": [
                {"title": "Fake1", "url": "https://fake1.llm/a"},
                {"title": "Fake2", "url": "https://fake2.llm/b"},
            ],
            "data_quality": {},
            "disclaimer": "仅供研究参考，不构成投资建议。",
        })

        result = parse_synthesis_llm_output(raw, ep)
        assert result is not None
        # All LLM URLs filtered → fallback to EP sources
        result_urls = [s.get("url", "") for s in result["sources"]]
        assert "https://ep.real.com/doc.pdf" in result_urls


# ══════════════════════════════════════════════════════════════════════════════
# T6 — post RiskReview cleans violation phrases from synthesis output
# ══════════════════════════════════════════════════════════════════════════════

class TestPostRiskReviewCleans:

    @pytest.mark.asyncio
    async def test_violation_phrases_replaced(self):
        from app.agents.orchestrator.financial_orchestrator import _post_synthesis_review
        from app.agents.orchestrator.risk_review_agent import RiskReviewAgent

        orch_response = {
            "summary":            "综合来看，建议买入该股票，必涨。",
            "business_analysis":  "基本面数据显示稳赚不赔，强烈推荐。",
            "market_analysis":    "近期行情较好。",
            "news_analysis":      "",
            "linkage_analysis":   "",
            "risk_points":        [],
            "sources":            [],
            "data_quality":       {},
            "disclaimer":         "仅供研究参考，不构成投资建议。",
        }

        events_collected: list[dict] = []

        async def _cb(event_type: str, payload: dict) -> None:
            events_collected.append({"event_type": event_type, **payload})

        ep = _make_evidence_pack()
        result = await _post_synthesis_review(
            orch_response, ep, RiskReviewAgent(), _cb, "req-test"
        )

        # Violation phrases must be gone from final output
        full_text = " ".join([
            result.get("summary", ""),
            result.get("business_analysis", ""),
        ])
        for phrase in ["买入", "必涨", "稳赚", "强烈推荐"]:
            assert phrase not in full_text, (
                f"Violation phrase '{phrase}' still present after post-review cleanup"
            )

    @pytest.mark.asyncio
    async def test_post_review_emits_stage_post_synthesis(self):
        from app.agents.orchestrator.financial_orchestrator import _post_synthesis_review
        from app.agents.orchestrator.risk_review_agent import RiskReviewAgent

        events: list[dict] = []
        async def _cb(event_type: str, payload: dict) -> None:
            events.append({"event_type": event_type, **payload})

        orch_response = {
            "summary": "clean text", "business_analysis": "clean",
            "market_analysis": "", "news_analysis": "", "linkage_analysis": "",
            "risk_points": [], "sources": [], "data_quality": {},
            "disclaimer": "仅供研究参考，不构成投资建议。",
        }

        await _post_synthesis_review(
            orch_response, _make_evidence_pack(), RiskReviewAgent(), _cb, "req-post"
        )

        etypes = [e["event_type"] for e in events]
        assert "risk_review_start"  in etypes
        assert "risk_review_result" in etypes

        # Check stage field
        rr_result_event = next(
            e for e in events if e["event_type"] == "risk_review_result"
        )
        assert rr_result_event.get("stage") == "post_synthesis"


# ══════════════════════════════════════════════════════════════════════════════
# T7 — SynthesisAgent timeout → fallback template, final_answer still emitted
# ══════════════════════════════════════════════════════════════════════════════

class TestSynthesisTimeout:

    @pytest.mark.asyncio
    async def test_synthesis_timeout_triggers_fallback(self):
        from app.agents.orchestrator.financial_orchestrator import FinancialOrchestrator
        from app.agents.orchestrator.risk_review_agent import RiskReviewAgent

        class _TimeoutSynthesis:
            async def run(self, evidence_pack, risk_review, **kwargs):
                await asyncio.sleep(999)  # will be cancelled by timeout
                return {}

        events: list[dict] = []
        async def _cb(event_type: str, payload: dict) -> None:
            events.append({"event_type": event_type, **payload})

        intent = {
            "query": "test", "symbol": "600519", "market": "CN",
            "need_fundamental": False, "need_market": False, "need_news": False,
            "need_report": False, "need_kline": False, "need_rag": False,
            "need_quote": False, "report_year": None, "report_type": "annual_report",
            "kline_period": "daily", "kline_limit": 30, "risk_level": "normal",
        }

        orch = FinancialOrchestrator(
            _mock_db(),
            synthesis_agent=_TimeoutSynthesis(),
            risk_review_agent=RiskReviewAgent(),
        )

        with patch(
            "app.agents.orchestrator.financial_orchestrator.build_task_intent",
            return_value=intent,
        ):
            with patch(
                "app.agents.orchestrator.financial_orchestrator.parse_financial_analysis_intent",
                return_value=intent,
            ):
                # Override synthesis timeout to something small for test speed
                import app.agents.orchestrator.financial_orchestrator as fo_module
                original_timeout = fo_module._TIMEOUT_SYNTHESIS
                fo_module._TIMEOUT_SYNTHESIS = 0.1
                try:
                    result = await orch.run_stream("test timeout", "req-t7", _cb)
                finally:
                    fo_module._TIMEOUT_SYNTHESIS = original_timeout

        # Must still produce final_answer and done
        event_types = [e["event_type"] for e in events]
        assert "final_answer"    in event_types, f"events: {event_types}"
        assert "agent_completed" in event_types, f"events: {event_types}"
        # Result must be ok=True (synthesis fallback, not blocked)
        assert result.get("final_answer") is not None


# ══════════════════════════════════════════════════════════════════════════════
# T8 — All 6 new SSE event types emitted in a full orchestrator run
# ══════════════════════════════════════════════════════════════════════════════

class TestAllNewSSEEventTypes:

    @pytest.mark.asyncio
    async def test_six_new_event_types_emitted(self):
        from app.agents.orchestrator.financial_orchestrator import FinancialOrchestrator
        from app.agents.orchestrator.fundamental_agent import FundamentalAgent
        from app.agents.orchestrator.risk_review_agent import RiskReviewAgent
        from app.agents.orchestrator.synthesis_agent import SynthesisAgent

        events: list[dict] = []
        async def _cb(event_type: str, payload: dict) -> None:
            events.append({"event_type": event_type, **payload})

        async def _empty_rag(*a, **kw):
            return {"results": [], "total": 0, "mode": "keyword", "diagnostics": {}}

        intent = {
            "query": "茅台综合分析", "symbol": "600519", "market": "CN",
            "need_fundamental": True, "need_market": False, "need_news": False,
            "need_report": True, "need_kline": False, "need_rag": True,
            "need_quote": False, "report_year": 2026, "report_type": "annual_report",
            "kline_period": "daily", "kline_limit": 30, "risk_level": "normal",
        }

        orch = FinancialOrchestrator(
            _mock_db(),
            fundamental_agent=FundamentalAgent(rag_search_fn=_empty_rag),
            risk_review_agent=RiskReviewAgent(),
            synthesis_agent=SynthesisAgent(llm_fn=None),   # template mode
        )

        with patch(
            "app.agents.orchestrator.financial_orchestrator.build_task_intent",
            return_value=intent,
        ), patch(
            "app.agents.orchestrator.financial_orchestrator.parse_financial_analysis_intent",
            return_value=intent,
        ):
            await orch.run_stream("茅台综合分析", "req-t8", _cb)

        event_types = {e["event_type"] for e in events}

        # The 6 new types from Phase 2E-2 spec
        new_types = {
            "orchestrator_start",
            "subagent_start",
            "subagent_result",
            "risk_review_start",
            "risk_review_result",
            "synthesis_start",
        }
        for etype in new_types:
            assert etype in event_types, (
                f"Missing event type '{etype}'; got: {sorted(event_types)}"
            )


# ══════════════════════════════════════════════════════════════════════════════
# T9 — subagent_result payload has display_name + sources_count
# ══════════════════════════════════════════════════════════════════════════════

class TestSubagentResultPayload:

    @pytest.mark.asyncio
    async def test_subagent_result_has_display_name_and_sources_count(self):
        from app.agents.orchestrator.financial_orchestrator import FinancialOrchestrator
        from app.agents.orchestrator.fundamental_agent import FundamentalAgent
        from app.agents.orchestrator.risk_review_agent import RiskReviewAgent
        from app.agents.orchestrator.synthesis_agent import SynthesisAgent

        events: list[dict] = []
        async def _cb(event_type: str, payload: dict) -> None:
            events.append({"event_type": event_type, **payload})

        async def _empty_rag(*a, **kw):
            return {"results": [], "total": 0, "mode": "keyword", "diagnostics": {}}

        intent = {
            "query": "test", "symbol": "600519", "market": "CN",
            "need_fundamental": True, "need_market": False, "need_news": False,
            "need_report": True, "need_kline": False, "need_rag": True,
            "need_quote": False, "report_year": 2026, "report_type": "annual_report",
            "kline_period": "daily", "kline_limit": 30, "risk_level": "normal",
        }

        orch = FinancialOrchestrator(
            _mock_db(),
            fundamental_agent=FundamentalAgent(rag_search_fn=_empty_rag),
            risk_review_agent=RiskReviewAgent(),
            synthesis_agent=SynthesisAgent(llm_fn=None),
        )

        with patch(
            "app.agents.orchestrator.financial_orchestrator.build_task_intent",
            return_value=intent,
        ), patch(
            "app.agents.orchestrator.financial_orchestrator.parse_financial_analysis_intent",
            return_value=intent,
        ):
            await orch.run_stream("test", "req-t9", _cb)

        subagent_results = [e for e in events if e["event_type"] == "subagent_result"]
        assert subagent_results, "Expected at least one subagent_result event"

        for sr in subagent_results:
            assert "display_name"   in sr, f"display_name missing in {sr}"
            assert "sources_count"  in sr, f"sources_count missing in {sr}"
            assert isinstance(sr["sources_count"], int)


# ══════════════════════════════════════════════════════════════════════════════
# T10 — Orchestrator disabled → no orchestrator events in process_message
# ══════════════════════════════════════════════════════════════════════════════

class TestNoOrchestratorEventsWhenDisabled:

    @pytest.mark.asyncio
    async def test_disabled_orchestrator_emits_no_orchestrator_start(self):
        """
        When ENABLE_MULTI_AGENT_ORCHESTRATOR=false (default),
        process_message must NOT emit orchestrator_start events.
        The FinancialAgent / SkillRegistry path is used instead.
        """
        from app.agents.chat_orchestrator import process_message

        db      = _mock_db()
        user_id = uuid.uuid4()

        events: list[dict] = []

        async def _cb(event_type: str, payload: dict) -> None:
            events.append({"event_type": event_type, **payload})

        # Orchestrator explicitly disabled
        with patch(
            "app.agents.orchestrator.financial_orchestrator.is_orchestrator_enabled",
            return_value=False,
        ):
            # Patch SkillRegistry to return a minimal result quickly
            with patch("app.agents.chat_orchestrator._skill_registry") as mock_registry:
                from dataclasses import dataclass

                @dataclass
                class _FakeResult:
                    answer: str = "Disabled-path answer."
                    tool_events: list = None
                    cards: list = None
                    confirmation: object = None
                    metadata: dict = None
                    skill_name: str = "general_financial_answer"
                    safety_flags: list = None

                    def __post_init__(self):
                        if self.tool_events  is None: self.tool_events  = []
                        if self.cards        is None: self.cards        = []
                        if self.metadata     is None: self.metadata     = {}
                        if self.safety_flags is None: self.safety_flags = []

                mock_registry.run = AsyncMock(return_value=_FakeResult())

                result = await process_message(
                    "AAPL 今天价格多少？",
                    db,
                    user_id,
                    event_callback=_cb,
                )

        # Orchestrator events must NOT appear
        orch_event_types = {
            e["event_type"] for e in events
            if e["event_type"] in {
                "orchestrator_start", "subagent_start", "subagent_result",
            }
        }
        assert not orch_event_types, (
            f"Orchestrator events found but orchestrator was disabled: {orch_event_types}"
        )
        # Must still get a result
        assert result is not None
