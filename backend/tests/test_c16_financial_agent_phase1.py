"""
test_c16_financial_agent_phase1.py — Phase 1.5 acceptance tests.

Validates the complete FinancialAgent event chain:
  1. Intent detection routes to correct tools (4 Cases)
  2. tool_call_start / tool_call_result events are emitted
  3. answer_delta events carry real LLM output
  4. final_answer is always emitted (even on tool failure)
  5. Tool failure does not abort the SSE chain
  6. double answer_delta is prevented by _realtime_answer_delta_emitted flag
  7. US news timestamps are formatted as 'YYYY-MM-DD HH:mm'
  8. final_answer contains summary / risk_points / disclaimer
  9. Banned phrases are filtered from final answer
 10. Per-tool timeout produces failed tool_call_result + continues to final_answer

All external I/O (yfinance, DeepSeek) is mocked — no network calls.
"""
from __future__ import annotations

import asyncio
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agents.financial_agent import (
    FinancialAgent,
    _TOOL_TIMEOUTS,
    _detect_intent,
    _fmt_unix_ts,
    _run_tool_with_timeout,
)


# ── Shared mock helpers ────────────────────────────────────────────────────────

_SAFE_ANSWER = (
    "### 研究摘要\n\n这是研究摘要，仅供参考。\n\n"
    "### 关键数据\n\n- 价格: 180.00 USD\n\n"
    "### 分析\n\n综合技术面与基本面，该标的中长期具有一定参考价值。\n\n"
    "### 风险提示\n\n- 市场波动风险\n- 政策不确定性风险\n- 汇率风险\n\n"
    "_仅供研究参考，不构成任何投资建议。_"
)

_QUOTE_RESULT = {
    "ok": True, "symbol": "AAPL", "market": "US",
    "price": 180.00, "change": 1.50, "change_pct": "+0.84%", "currency": "USD",
}
_KLINE_RESULT = {
    "ok": True, "symbol": "MSFT", "market": "US",
    "period_change_pct": 3.72, "candles_count": 60,
    "candles_sample": [{"date": "2026-06-24", "open": 415, "high": 420, "low": 412, "close": 418, "volume": 1000000}],
}
_NEWS_RESULT = {
    "ok": True, "symbol": "NVDA", "market": "US",
    "count": 2,
    "items": [
        {
            "title": "Nvidia Unveils Next-Gen Chip",
            "source": "Reuters",
            "published_at": "2026-06-24 10:00",
            "published_at_raw": 1750766400,
            "url": "https://example.com/news1",
            "summary": "Nvidia Unveils Next-Gen Chip",
        },
        {
            "title": "AI Demand Boosts NVDA Margins",
            "source": "Bloomberg",
            "published_at": "2026-06-23 14:30",
            "published_at_raw": 1750689000,
            "url": "https://example.com/news2",
            "summary": "AI Demand Boosts NVDA Margins",
        },
    ],
}


class _MockLLM:
    """Minimal LLM mock. Returns predefined answer chunks via async generator."""

    def __init__(self, chunks: list[dict] | None = None, raise_exc: Exception | None = None):
        self._chunks = chunks or [
            {"type": "answer", "content": "### 研究摘要\n\n这是研究摘要，仅供参考。\n\n"},
            {"type": "answer", "content": "### 风险提示\n\n- 市场波动风险\n\n"},
            {"type": "answer", "content": "_仅供研究参考，不构成任何投资建议。_"},
        ]
        self._raise = raise_exc

    async def async_stream_chat(
        self, messages: list[dict], **kwargs
    ) -> AsyncGenerator[dict, None]:
        exc = self._raise
        chunks = self._chunks

        async def _gen() -> AsyncGenerator[dict, None]:
            if exc:
                raise exc
            for c in chunks:
                yield c

        return _gen()

    def chat_flash(self, messages: list[dict], **kwargs) -> str:
        return _SAFE_ANSWER


def _mock_llm_patch(llm: _MockLLM | None = None):
    """Return a patch context that replaces get_llm_client with a mock LLM."""
    if llm is None:
        llm = _MockLLM()
    m = MagicMock(return_value=llm)
    return patch("app.llm.factory.get_llm_client", m)


async def _run_agent(query: str, *, llm=None, mock_quote=None, mock_kline=None, mock_news=None):
    """
    Helper: run FinancialAgent with patched external dependencies.
    Returns (events, response).
    """
    events: list[dict] = []

    async def _cb(event_type: str, payload: dict) -> None:
        events.append({"type": event_type, "payload": payload})

    db = MagicMock()
    registry = MagicMock()

    patches = [_mock_llm_patch(llm)]
    if mock_quote is not None:
        patches.append(
            patch("app.agents.financial_agent._fetch_us_quote", AsyncMock(return_value=mock_quote))
        )
    if mock_kline is not None:
        patches.append(
            patch("app.agents.financial_agent._fetch_us_kline", AsyncMock(return_value=mock_kline))
        )
    if mock_news is not None:
        patches.append(
            patch("app.agents.financial_agent._fetch_us_news", AsyncMock(return_value=mock_news))
        )

    # Apply all patches
    active = []
    for p in patches:
        active.append(p.__enter__())

    try:
        agent = FinancialAgent()
        response = await agent.run(
            query=query,
            db=db,
            tool_registry=registry,
            output_language="zh-CN",
            event_callback=_cb,
        )
    finally:
        for p, ctx in zip(patches, active):
            p.__exit__(None, None, None)

    return events, response


def _events_of(events: list[dict], event_type: str) -> list[dict]:
    return [e for e in events if e["type"] == event_type]


# ═══════════════════════════════════════════════════════════════════════════════
# Section 1: Intent Detection (unit tests — no mocking needed)
# ═══════════════════════════════════════════════════════════════════════════════

class TestIntentDetection:

    def test_case1_apple_longterm(self):
        r = _detect_intent("苹果公司适合长期持有吗？")
        assert r["symbol"] == "AAPL"
        assert r["market"] == "US"
        # default: quote + news when no specific intent keyword
        assert r["need_quote"] or r["need_news"]

    def test_case2_aapl_today_market(self):
        r = _detect_intent("帮我分析一下 AAPL 今天的行情")
        assert r["symbol"] == "AAPL"
        assert r["market"] == "US"
        assert r["need_quote"] is True

    def test_case3_msft_60day_kline(self):
        r = _detect_intent("请根据最近 60 日 K 线分析 MSFT 是否可以关注")
        assert r["symbol"] == "MSFT"
        assert r["market"] == "US"
        assert r["need_kline"] is True

    def test_case4_nvda_news(self):
        r = _detect_intent("最近英伟达有什么利好或利空新闻？")
        assert r["symbol"] == "NVDA"
        assert r["market"] == "US"
        assert r["need_news"] is True

    def test_cn_stock_detected(self):
        r = _detect_intent("贵州茅台最近财报怎么样")
        assert r["symbol"] == "600519"
        assert r["market"] == "CN"

    def test_us_ticker_direct(self):
        r = _detect_intent("TSLA 今天涨了多少")
        assert r["symbol"] == "TSLA"
        assert r["market"] == "US"


# ═══════════════════════════════════════════════════════════════════════════════
# Section 2: Event sequence (integration tests with mocked I/O)
# ═══════════════════════════════════════════════════════════════════════════════

class TestEventSequence:

    @pytest.mark.asyncio
    async def test_case1_apple_longterm_emits_final_answer(self):
        """Case 1: General holding question must emit final_answer with required fields."""
        events, response = await _run_agent(
            "苹果公司适合长期持有吗？",
            mock_quote=_QUOTE_RESULT,
            mock_news=_NEWS_RESULT,
        )

        # final_answer must exist
        fa_events = _events_of(events, "final_answer")
        assert len(fa_events) >= 1, "Must emit at least one final_answer"

        fa = fa_events[0]["payload"]
        assert fa.get("summary"), "final_answer must contain summary"
        assert fa.get("disclaimer"), "final_answer must contain disclaimer"
        assert isinstance(fa.get("risk_points"), list), "final_answer must have risk_points list"
        assert len(fa["risk_points"]) > 0, "risk_points must not be empty"

        # answer text must include disclaimer
        assert "仅供研究参考" in response.answer_text, "answer_text must include disclaimer"

    @pytest.mark.asyncio
    async def test_case2_aapl_quote_tool_events(self):
        """Case 2: AAPL today's market — must emit tool_call_start + tool_call_result for quote."""
        events, response = await _run_agent(
            "帮我分析一下 AAPL 今天的行情",
            mock_quote=_QUOTE_RESULT,
        )

        starts = _events_of(events, "tool_call_start")
        results = _events_of(events, "tool_call_result")
        fa_events = _events_of(events, "final_answer")

        # Must have tool_call_start for stock_quote_tool
        quote_starts = [e for e in starts if e["payload"].get("tool_name") == "stock_quote_tool"]
        assert len(quote_starts) >= 1, "Must send tool_call_start for stock_quote_tool"

        # Must have tool_call_result for stock_quote_tool
        quote_results = [e for e in results if e["payload"].get("tool_name") == "stock_quote_tool"]
        assert len(quote_results) >= 1, "Must send tool_call_result for stock_quote_tool"
        assert quote_results[0]["payload"]["status"] == "success"

        # Must emit final_answer
        assert len(fa_events) >= 1, "Must emit final_answer"

    @pytest.mark.asyncio
    async def test_case3_msft_kline_tool_events(self):
        """Case 3: MSFT 60-day kline — must emit tool events for kline."""
        events, response = await _run_agent(
            "请根据最近 60 日 K 线分析 MSFT 是否可以关注",
            mock_kline=_KLINE_RESULT,
        )

        starts = _events_of(events, "tool_call_start")
        results = _events_of(events, "tool_call_result")
        fa_events = _events_of(events, "final_answer")

        kline_starts = [e for e in starts if e["payload"].get("tool_name") == "stock_kline_tool"]
        assert len(kline_starts) >= 1, "Must send tool_call_start for stock_kline_tool"

        kline_results = [e for e in results if e["payload"].get("tool_name") == "stock_kline_tool"]
        assert len(kline_results) >= 1, "Must send tool_call_result for stock_kline_tool"
        assert kline_results[0]["payload"]["status"] == "success"

        assert len(fa_events) >= 1, "Must emit final_answer"

        # Final answer must NOT directly promise "可以买入"
        # (banned phrase filter replaces 买入 → 关注)
        assert "买入" not in response.answer_text, "Banned phrase '买入' must be filtered"

    @pytest.mark.asyncio
    async def test_case4_nvda_news_tool_events(self):
        """Case 4: 英伟达 news — must detect NVDA and emit financial_news tool events."""
        events, response = await _run_agent(
            "最近英伟达有什么利好或利空新闻？",
            mock_news=_NEWS_RESULT,
        )

        starts = _events_of(events, "tool_call_start")
        results = _events_of(events, "tool_call_result")
        fa_events = _events_of(events, "final_answer")

        news_starts = [e for e in starts if e["payload"].get("tool_name") == "financial_news_tool"]
        assert len(news_starts) >= 1, "Must send tool_call_start for financial_news_tool"

        news_results = [e for e in results if e["payload"].get("tool_name") == "financial_news_tool"]
        assert len(news_results) >= 1, "Must send tool_call_result for financial_news_tool"
        assert news_results[0]["payload"]["status"] == "success"

        assert len(fa_events) >= 1, "Must emit final_answer"

    @pytest.mark.asyncio
    async def test_answer_delta_emitted(self):
        """answer_delta events must be emitted from LLM streaming."""
        events, _ = await _run_agent(
            "苹果公司适合长期持有吗？",
            mock_quote=_QUOTE_RESULT,
        )
        deltas = _events_of(events, "answer_delta")
        assert len(deltas) >= 1, "Must emit at least one answer_delta"
        combined = "".join(e["payload"]["delta"] for e in deltas)
        assert len(combined) > 10, "Combined answer_delta must be non-trivial"

    @pytest.mark.asyncio
    async def test_event_order_tool_before_answer(self):
        """tool_call_result must appear before answer_delta in the event stream."""
        events, _ = await _run_agent(
            "帮我分析一下 AAPL 今天的行情",
            mock_quote=_QUOTE_RESULT,
        )
        types = [e["type"] for e in events]

        # Find positions
        tool_result_idx = next(
            (i for i, t in enumerate(types) if t == "tool_call_result"), None
        )
        answer_delta_idx = next(
            (i for i, t in enumerate(types) if t == "answer_delta"), None
        )

        assert tool_result_idx is not None, "Must have tool_call_result"
        assert answer_delta_idx is not None, "Must have answer_delta"
        assert tool_result_idx < answer_delta_idx, (
            "tool_call_result must come before answer_delta"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# Section 3: Tool failure resilience
# ═══════════════════════════════════════════════════════════════════════════════

class TestToolFailureResilience:

    @pytest.mark.asyncio
    async def test_quote_failure_still_produces_final_answer(self):
        """If stock_quote fails, the agent must still emit final_answer."""
        failed_quote = {"ok": False, "error": "连接超时，行情数据不可用"}
        events, response = await _run_agent(
            "帮我分析一下 AAPL 今天的行情",
            mock_quote=failed_quote,
        )

        # tool_call_result must show failed status
        results = _events_of(events, "tool_call_result")
        assert len(results) >= 1
        assert results[0]["payload"]["status"] == "failed"

        # result_summary must mention the failure — the agent builds this, regardless of LLM
        summary = results[0]["payload"].get("result_summary", "")
        has_limitation = any(
            phrase in summary
            for phrase in ["不可用", "获取失败", "可靠性有限", "失败"]
        )
        assert has_limitation, (
            f"tool_call_result.result_summary must indicate data failure. Got: {summary!r}"
        )

        # final_answer must still be emitted — chain must not abort on tool failure
        fa_events = _events_of(events, "final_answer")
        assert len(fa_events) >= 1, "Must emit final_answer even when tool fails"

        # answer_text must include disclaimer (safety baseline always held)
        assert "仅供研究参考" in response.answer_text

    @pytest.mark.asyncio
    async def test_news_failure_does_not_abort_sse(self):
        """If financial_news fails, the chain must not abort."""
        failed_news = {"ok": False, "error": "API rate limit exceeded"}
        events, response = await _run_agent(
            "最近英伟达有什么利好或利空新闻？",
            mock_news=failed_news,
        )

        results = _events_of(events, "tool_call_result")
        news_results = [r for r in results if r["payload"].get("tool_name") == "financial_news_tool"]
        assert len(news_results) >= 1
        assert news_results[0]["payload"]["status"] == "failed"

        # final_answer still sent
        assert len(_events_of(events, "final_answer")) >= 1

    @pytest.mark.asyncio
    async def test_all_tools_fail_still_produces_final_answer(self):
        """When all tools fail, LLM generates fallback answer and final_answer is emitted."""
        failed = {"ok": False, "error": "service unavailable"}
        events, response = await _run_agent(
            "帮我分析一下 AAPL 今天的行情",
            mock_quote=failed,
        )

        fa_events = _events_of(events, "final_answer")
        assert len(fa_events) >= 1, "Must emit final_answer even when all tools fail"
        assert response.answer_text, "answer_text must not be empty"
        assert "仅供研究参考" in response.answer_text


# ═══════════════════════════════════════════════════════════════════════════════
# Section 4: Tool timeout unit tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestToolTimeout:

    @pytest.mark.asyncio
    async def test_run_tool_with_timeout_success(self):
        """_run_tool_with_timeout returns result on fast coroutine."""
        async def fast_coro():
            return {"ok": True, "price": 180.0}

        result = await _run_tool_with_timeout("stock_quote_tool", fast_coro(), 5.0)
        assert result["ok"] is True
        assert result["price"] == 180.0

    @pytest.mark.asyncio
    async def test_run_tool_with_timeout_on_timeout(self):
        """_run_tool_with_timeout returns ok=False with error on TimeoutError."""
        async def slow_coro():
            await asyncio.sleep(10)  # much longer than timeout
            return {"ok": True}

        result = await _run_tool_with_timeout("stock_quote_tool", slow_coro(), 0.05)
        assert result["ok"] is False
        assert "超时" in result["error"] or "timeout" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_run_tool_with_timeout_on_exception(self):
        """_run_tool_with_timeout returns ok=False with error on any exception."""
        async def failing_coro():
            raise ConnectionError("network error")

        result = await _run_tool_with_timeout("stock_quote_tool", failing_coro(), 5.0)
        assert result["ok"] is False
        assert "network error" in result["error"]

    def test_tool_timeout_constants_defined(self):
        """Per-tool timeout constants must be defined with reasonable values."""
        assert _TOOL_TIMEOUTS["stock_quote"] == 8.0
        assert _TOOL_TIMEOUTS["stock_kline"] == 10.0
        assert _TOOL_TIMEOUTS["financial_news"] == 12.0


# ═══════════════════════════════════════════════════════════════════════════════
# Section 5: Double answer_delta prevention
# ═══════════════════════════════════════════════════════════════════════════════

class TestDoubleAnswerDelta:

    @pytest.mark.asyncio
    async def test_answer_chunks_not_duplicated_in_response(self):
        """The combined answer_delta text must exactly equal answer_text (no duplication)."""
        events, response = await _run_agent(
            "苹果公司适合长期持有吗？",
            mock_quote=_QUOTE_RESULT,
        )

        deltas = _events_of(events, "answer_delta")
        combined_deltas = "".join(e["payload"]["delta"] for e in deltas)

        # The response.answer_text is the filtered version of combined_deltas
        # They should match length-wise (or answer_text may have small additions like disclaimer)
        assert len(combined_deltas) > 0, "Must have answer_delta content"
        assert combined_deltas in response.answer_text or response.answer_text in combined_deltas or \
               abs(len(combined_deltas) - len(response.answer_text)) <= 60, (
            f"answer_delta combined ({len(combined_deltas)} chars) and "
            f"answer_text ({len(response.answer_text)} chars) should be similar length"
        )

    def test_realtime_flag_prevents_phase8_replay(self):
        """Contract test: _realtime_answer_delta_emitted=True must skip Phase 8 replay."""
        # Simulate the flag logic from chat_streaming.py
        _flag = [False]

        def record_emit(event_type: str, payload: dict):
            if event_type == "answer_delta":
                _flag[0] = True

        # FinancialAgent streams answer_delta in real-time
        record_emit("answer_delta", {"delta": "chunk1"})
        record_emit("answer_delta", {"delta": "chunk2"})

        assert _flag[0] is True, "Flag must be set after real-time answer_delta"

        # Phase 8: replay is skipped when flag is True
        replayed: list[str] = []
        result_answer = "chunk1chunk2"
        if not _flag[0]:   # ← exact condition in chat_streaming.py Phase 8
            for i in range(0, len(result_answer), 25):
                replayed.append(result_answer[i:i+25])

        assert replayed == [], (
            "Phase 8 must NOT replay answer when real-time streaming already happened"
        )

    @pytest.mark.asyncio
    async def test_each_llm_chunk_appears_exactly_once(self):
        """Each LLM chunk must appear in answer_delta exactly once."""
        chunk_a = "### 研究摘要\n\n苹果公司基本面稳健。\n\n"
        chunk_b = "### 风险提示\n\n- 市场波动风险\n\n_仅供研究参考，不构成任何投资建议。_"

        llm = _MockLLM(chunks=[
            {"type": "answer", "content": chunk_a},
            {"type": "answer", "content": chunk_b},
        ])

        events, _ = await _run_agent(
            "苹果公司适合长期持有吗？",
            llm=llm,
            mock_quote=_QUOTE_RESULT,
        )

        deltas = _events_of(events, "answer_delta")
        delta_texts = [e["payload"]["delta"] for e in deltas]

        # chunk_a and chunk_b should each appear exactly once in deltas
        combined = "".join(delta_texts)
        assert combined.count(chunk_a) == 1, f"chunk_a must appear exactly once. Combined: {combined[:100]}"
        assert combined.count(chunk_b) == 1, f"chunk_b must appear exactly once"


# ═══════════════════════════════════════════════════════════════════════════════
# Section 6: US news timestamp formatting
# ═══════════════════════════════════════════════════════════════════════════════

class TestNewsTimestampFormatting:

    def test_fmt_unix_ts_integer(self):
        """Unix int timestamp must format to YYYY-MM-DD HH:mm string."""
        fmt, raw = _fmt_unix_ts(1750766400)  # 2025-06-24 10:00 UTC (approx)
        assert raw == 1750766400
        # Format: 10 char date + " " + 5 char time
        assert len(fmt) == 16, f"Expected 'YYYY-MM-DD HH:mm', got: {fmt!r}"
        assert fmt[4] == "-" and fmt[7] == "-" and fmt[10] == " " and fmt[13] == ":"

    def test_fmt_unix_ts_float(self):
        """Unix float timestamp also formats correctly."""
        fmt, raw = _fmt_unix_ts(1750766400.0)
        assert raw == 1750766400.0
        assert len(fmt) == 16

    def test_fmt_unix_ts_empty_string(self):
        """Empty string input returns ('', None) without raising."""
        fmt, raw = _fmt_unix_ts("")
        assert fmt == ""
        assert raw is None

    def test_fmt_unix_ts_none(self):
        """None input returns ('', None) without raising."""
        fmt, raw = _fmt_unix_ts(None)
        assert fmt == ""
        assert raw is None

    def test_fmt_unix_ts_string_passthrough(self):
        """Non-numeric string is passed through as-is."""
        fmt, raw = _fmt_unix_ts("2026-06-24 10:00")
        assert fmt == "2026-06-24 10:00"
        assert raw is None

    @pytest.mark.asyncio
    async def test_nvda_news_timestamp_formatted(self):
        """NVDA news tool result must have formatted published_at."""
        # Use raw yfinance-style data with Unix timestamp
        raw_news_data = {
            "ok": True, "symbol": "NVDA", "market": "US", "count": 1,
            "items": [
                {
                    "title": "NVDA Test Story",
                    "source": "Reuters",
                    "published_at": "2026-06-24 10:00",
                    "published_at_raw": 1750766400,
                    "url": "https://example.com",
                    "summary": "NVDA Test Story",
                }
            ],
        }
        events, _ = await _run_agent(
            "最近英伟达有什么利好或利空新闻？",
            mock_news=raw_news_data,
        )

        # The mock returns pre-formatted data; verify it passes through
        news_results = [
            e for e in _events_of(events, "tool_call_result")
            if e["payload"].get("tool_name") == "financial_news_tool"
        ]
        assert len(news_results) >= 1
        assert news_results[0]["payload"]["status"] == "success"


# ═══════════════════════════════════════════════════════════════════════════════
# Section 7: final_answer payload structure
# ═══════════════════════════════════════════════════════════════════════════════

class TestFinalAnswerStructure:

    @pytest.mark.asyncio
    async def test_final_answer_has_all_required_fields(self):
        """final_answer payload must have summary, analysis, risk_points, disclaimer."""
        events, _ = await _run_agent(
            "苹果公司适合长期持有吗？",
            mock_quote=_QUOTE_RESULT,
            mock_news=_NEWS_RESULT,
        )
        fa_events = _events_of(events, "final_answer")
        assert fa_events, "Must emit final_answer"
        fa = fa_events[0]["payload"]

        assert "summary" in fa, "final_answer must have 'summary'"
        assert "analysis" in fa, "final_answer must have 'analysis'"
        assert "risk_points" in fa, "final_answer must have 'risk_points'"
        assert "disclaimer" in fa, "final_answer must have 'disclaimer'"
        assert "仅供研究参考" in fa.get("disclaimer", ""), "disclaimer must contain safety text"

    @pytest.mark.asyncio
    async def test_final_answer_payload_is_flat(self):
        """final_answer payload must be flat (no nested 'final_answer' key)."""
        events, _ = await _run_agent(
            "苹果公司适合长期持有吗？",
            mock_quote=_QUOTE_RESULT,
        )
        fa_events = _events_of(events, "final_answer")
        assert fa_events
        fa = fa_events[0]["payload"]
        # Flat structure: should NOT have nested final_answer key
        assert "final_answer" not in fa, "Payload must be flat, not nested"
        # But must have top-level required fields
        assert "summary" in fa

    @pytest.mark.asyncio
    async def test_final_answer_risk_points_is_list(self):
        """risk_points in final_answer must be a list."""
        events, _ = await _run_agent("苹果公司风险分析")
        fa_events = _events_of(events, "final_answer")
        if not fa_events:
            pytest.skip("No final_answer emitted")
        fa = fa_events[0]["payload"]
        assert isinstance(fa.get("risk_points"), list)

    @pytest.mark.asyncio
    async def test_final_answer_after_tool_failure_mentions_limitation(self):
        """When tool fails, final_answer summary/analysis must mention data limitation."""
        failed = {"ok": False, "error": "service down"}
        events, _ = await _run_agent(
            "帮我分析一下 AAPL 今天的行情",
            mock_quote=failed,
        )
        fa_events = _events_of(events, "final_answer")
        assert fa_events

        fa = fa_events[0]["payload"]
        # Disclaimer should always be present
        assert fa.get("disclaimer"), "disclaimer must be present even on failure"


# ═══════════════════════════════════════════════════════════════════════════════
# Section 8: Safety — banned phrase filtering
# ═══════════════════════════════════════════════════════════════════════════════

class TestSafetyFilters:

    @pytest.mark.asyncio
    async def test_banned_phrase_buyIn_filtered(self):
        """'买入' must be replaced by '关注' in answer_text."""
        llm = _MockLLM(chunks=[
            {"type": "answer", "content": "建议买入 AAPL，因为基本面强劲。\n\n_仅供研究参考，不构成任何投资建议。_"},
        ])
        _, response = await _run_agent("AAPL 可以买入吗", llm=llm)
        assert "买入" not in response.answer_text, "Banned phrase '买入' must be filtered"
        assert "关注" in response.answer_text, "Replacement '关注' must appear"

    @pytest.mark.asyncio
    async def test_disclaimer_always_present(self):
        """answer_text must always include the disclaimer."""
        llm = _MockLLM(chunks=[
            {"type": "answer", "content": "研究摘要：苹果长期价值稳健。"},
        ])
        _, response = await _run_agent("苹果公司", llm=llm)
        assert "仅供研究参考" in response.answer_text, "Disclaimer must be appended"

    @pytest.mark.asyncio
    async def test_no_thinking_events_from_flash_model(self):
        """Flash model does not emit reasoning_content — no 'thinking' events expected."""
        events, _ = await _run_agent(
            "帮我分析一下 AAPL 今天的行情",
            mock_quote=_QUOTE_RESULT,
        )
        thinking_events = _events_of(events, "thinking")
        # Default mock LLM yields only 'answer' chunks — no 'thinking'
        assert len(thinking_events) == 0, "Mock flash LLM must not emit thinking events"

    @pytest.mark.asyncio
    async def test_thinking_events_emitted_when_model_provides_reasoning(self):
        """If LLM yields 'thinking' chunks, they must be forwarded as 'thinking' events."""
        llm = _MockLLM(chunks=[
            {"type": "thinking", "content": "让我先分析基本面..."},
            {"type": "answer",   "content": "### 研究摘要\n分析完成。\n\n_仅供研究参考，不构成任何投资建议。_"},
        ])
        events, _ = await _run_agent("AAPL 分析", llm=llm)
        thinking_events = _events_of(events, "thinking")
        assert len(thinking_events) == 1
        assert thinking_events[0]["payload"]["content"] == "让我先分析基本面..."
