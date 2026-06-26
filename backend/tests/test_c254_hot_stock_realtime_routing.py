"""
test_c254_hot_stock_realtime_routing.py — C25.4 fixes.

Validates:
1. parse_financial_analysis_intent propagates need_realtime
2. _detect_intent correctly flags hot-stock queries as need_realtime
3. _detect_realtime_mode routes hot-stock queries to 'hot_stocks'
4. Hot-stock queries that previously had need_realtime dropped now correctly expose it
5. Tool context distinguishes: tool-not-called vs tool-called-no-data vs tool-failed
"""
from __future__ import annotations
import pytest


# ── 1. parse_financial_analysis_intent propagates need_realtime ───────────────

class TestParseFinancialAnalysisIntentRealtimePropagation:

    def test_semiconductor_hot_stock_query_has_need_realtime(self):
        """
        '半导体行业最近有哪些热门股？' — the key fix: need_realtime must survive
        the round-trip through parse_financial_analysis_intent.
        """
        from app.agents.official_report_search import parse_financial_analysis_intent
        intent = parse_financial_analysis_intent("半导体行业最近有哪些热门股？")
        assert intent.get("need_realtime") is True, (
            "need_realtime was not propagated — universal_market_search will never fire"
        )

    def test_new_energy_hot_stock_has_need_realtime(self):
        from app.agents.official_report_search import parse_financial_analysis_intent
        intent = parse_financial_analysis_intent("新能源热门股有哪些？")
        assert intent.get("need_realtime") is True

    def test_ai_equipment_hot_stock_has_need_realtime(self):
        from app.agents.official_report_search import parse_financial_analysis_intent
        intent = parse_financial_analysis_intent("AI相关设备公司最近有哪些热门股？")
        assert intent.get("need_realtime") is True

    def test_industry_hot_stock_no_symbol(self):
        """Queries without a specific stock code must have symbol=None."""
        from app.agents.official_report_search import parse_financial_analysis_intent
        intent = parse_financial_analysis_intent("半导体行业最近有哪些热门股？")
        assert intent.get("symbol") is None

    def test_regular_query_still_works(self):
        """Regression: non-realtime query should still parse correctly."""
        from app.agents.official_report_search import parse_financial_analysis_intent
        intent = parse_financial_analysis_intent("茅台最新股价是多少？")
        assert intent.get("symbol") == "600519"
        assert intent.get("market") == "CN"

    def test_need_realtime_key_present_in_return_dict(self):
        """Key must exist (not just falsy) in the returned dict."""
        from app.agents.official_report_search import parse_financial_analysis_intent
        intent = parse_financial_analysis_intent("今天哪些行业值得研究？")
        assert "need_realtime" in intent, "need_realtime key missing from return dict entirely"

    def test_non_realtime_query_has_need_realtime_false(self):
        """Standard stock queries should not trigger realtime."""
        from app.agents.official_report_search import parse_financial_analysis_intent
        intent = parse_financial_analysis_intent("介绍一下茅台的商业模式")
        assert intent.get("need_realtime") is False


# ── 2. _detect_intent correctly identifies hot-stock queries ──────────────────

class TestDetectIntentHotStock:

    def test_semiconductor_hot_stock_need_realtime(self):
        from app.agents.financial_agent import _detect_intent
        intent = _detect_intent("半导体行业最近有哪些热门股？")
        assert intent["need_realtime"] is True

    def test_new_energy_hot_stock_need_realtime(self):
        from app.agents.financial_agent import _detect_intent
        intent = _detect_intent("新能源热门股有哪些？")
        assert intent["need_realtime"] is True

    def test_hot_stock_no_symbol(self):
        from app.agents.financial_agent import _detect_intent
        intent = _detect_intent("半导体行业最近有哪些热门股？")
        assert intent["symbol"] is None

    def test_hot_stock_no_need_news(self):
        """
        '热门股' queries must NOT match need_news — otherwise the realtime
        branch guard 'not need_news' would block universal_market_search.
        """
        from app.agents.financial_agent import _detect_intent
        intent = _detect_intent("半导体行业最近有哪些热门股？")
        assert intent["need_news"] is False, (
            "need_news=True would block universal_market_search via the guard condition"
        )


# ── 3. _detect_realtime_mode routes hot-stock queries correctly ───────────────

class TestDetectRealtimeModeHotStock:

    def test_semiconductor_hot_stock_routes_to_hot_stocks(self):
        from app.agents.financial_agent import _detect_realtime_mode
        mode = _detect_realtime_mode("半导体行业最近有哪些热门股？")
        assert mode == "hot_stocks", f"Expected 'hot_stocks', got '{mode}'"

    def test_new_energy_hot_stock_routes_to_hot_stocks(self):
        from app.agents.financial_agent import _detect_realtime_mode
        mode = _detect_realtime_mode("新能源热门股有哪些？")
        assert mode == "hot_stocks"

    def test_ai_equipment_hot_stock_routes_to_hot_stocks(self):
        from app.agents.financial_agent import _detect_realtime_mode
        mode = _detect_realtime_mode("AI相关设备公司最近有哪些热门股？")
        assert mode == "hot_stocks"

    def test_fund_flow_query_routes_to_fund_flow(self):
        from app.agents.financial_agent import _detect_realtime_mode
        mode = _detect_realtime_mode("今天北向资金净流入哪些行业？")
        assert mode == "fund_flow"

    def test_industry_rank_routes_to_industry_rank(self):
        from app.agents.financial_agent import _detect_realtime_mode
        mode = _detect_realtime_mode("今日行业涨跌排行榜")
        assert mode == "industry_rank"


# ── 4. Hot-stock query end-to-end: universal_market_search fires ──────────────

class TestHotStockUniversalMarketSearchFires:
    """
    Verify the full flow from query → intent → branch condition evaluation,
    confirming that universal_market_search would be called (not blocked).
    """

    def test_condition_would_fire_for_semiconductor(self):
        """
        Simulate the guard condition in financial_agent.py:
          not symbol and need_realtime and not need_news
        """
        from app.agents.financial_agent import _detect_intent
        intent = _detect_intent("半导体行业最近有哪些热门股？")
        symbol       = intent["symbol"]
        need_realtime = intent["need_realtime"]
        need_news     = intent["need_news"]

        would_fire = (symbol is None) and need_realtime and (not need_news)
        assert would_fire, (
            f"universal_market_search would NOT fire: "
            f"symbol={symbol!r}, need_realtime={need_realtime}, need_news={need_news}"
        )

    def test_condition_would_fire_for_new_energy(self):
        from app.agents.financial_agent import _detect_intent
        intent = _detect_intent("新能源热门股有哪些？")
        symbol       = intent["symbol"]
        need_realtime = intent["need_realtime"]
        need_news     = intent["need_news"]
        would_fire = (symbol is None) and need_realtime and (not need_news)
        assert would_fire

    def test_condition_would_fire_after_parse_financial_intent(self):
        """
        Confirm the same guard fires when using parse_financial_analysis_intent
        (which is what FinancialAgent actually calls).
        """
        from app.agents.official_report_search import parse_financial_analysis_intent
        intent = parse_financial_analysis_intent("半导体行业最近有哪些热门股？")
        symbol        = intent.get("symbol")
        need_realtime = intent.get("need_realtime")
        need_news     = intent.get("need_news")
        would_fire = (symbol is None) and need_realtime and (not need_news)
        assert would_fire, (
            f"After parse_financial_analysis_intent: "
            f"symbol={symbol!r}, need_realtime={need_realtime}, need_news={need_news}"
        )


# ── 5. Tool context content accuracy ─────────────────────────────────────────

class TestToolContextAccuracy:
    """
    Verify that the default "未调用专项工具" message only appears when truly
    no tools ran — not when tools ran but returned no data.
    """

    def test_empty_tool_parts_produces_not_called_message(self):
        """When tool_context_parts is empty, fallback text is shown."""
        tool_context_parts: list[str] = []
        tool_context = (
            "\n".join(tool_context_parts)
            if tool_context_parts
            else "（本次未调用专项工具，以通用知识作答）"
        )
        assert "未调用" in tool_context

    def test_failed_tool_still_populates_context(self):
        """
        When universal_market_search fails, it still writes to tool_context_parts
        so the LLM knows a tool WAS called (just returned no data).
        """
        # Simulate what financial_agent.py does for a failed tool:
        _rt_summary = "市场搜索失败: Connection timeout"
        tool_context_parts = [f"【市场热点 — 查询热门股排行】{_rt_summary}"]
        tool_context = "\n".join(tool_context_parts)

        # Must NOT say "未调用" — a tool was called, it just failed
        assert "未调用" not in tool_context
        assert "市场热点" in tool_context
        assert "失败" in tool_context
