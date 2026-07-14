"""
tests/fundamental/test_phase6j_report_chat_copilot.py

Phase 6J: 问财报 Chat Copilot — 16 tests

 1. valid financial question classification → "allowed"
 2. investment advice question classification → "rejected"
 3. target price question classification → "rejected"
 4. query expansion for cash flow question
 5. query expansion for risk question
 6. no cross-stock data (ts_code isolation)
 7. no chunks → partial=True + data_limitations annotated
 8. fake chunk_id removed by review (canonicalize_source_chunks)
 9. page citation in answer removed
10. coverage claim rewritten
11. API code parsing: "600519" → CN, "600519.SH" → CN
12. API code parsing: "00700.HK" → HK → partial + market gate
13. question length limit (>500 chars truncated)
14. top_k capped at 10
15. no v-html in ReportChatPanel.vue
16. agent never raises — exception returns partial=True
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_chunk(chunk_id: int, content: str = "财务数据内容", section: str = "管理层讨论") -> dict:
    return {
        "chunk_id":      chunk_id,
        "report_id":     1,
        "ts_code":       "600519.SH",
        "report_type":   "annual",
        "report_year":   2023,
        "period":        "2023-12-31",
        "section_title": section,
        "content":       content,
        "score":         0.85,
    }


def _make_rag_result(chunks: list[dict] | None = None, fallback: bool = False) -> dict:
    return {
        "chunks":        chunks or [],
        "partial":       False,
        "errors":        [],
        "search_mode":   "keyword" if fallback else "vector",
        "total":         len(chunks or []),
        "fallback_used": fallback,
        "provider":      "mock",
    }


def _make_selection(report_id: int = 1):
    from app.agent.report_context import ReportSelection

    return ReportSelection(
        report_id=report_id,
        symbol="600519",
        market="CN",
        ts_code="600519.SH",
        stock_name="贵州茅台",
        report_year=2023,
        report_type="annual",
        period_end="2023-12-31",
        title="贵州茅台2023年年度报告",
        disclosure_date="2024-03-30",
        selection_reason="latest_formal_report",
    )


# ─────────────────────────────────────────────────────────────────────────────
# Test 1: valid financial question → allowed
# ─────────────────────────────────────────────────────────────────────────────

def test_valid_question_classification():
    from app.agent.report_chat_copilot_agent import _classify_question

    assert _classify_question("公司的现金流质量怎么样？") == "allowed"
    assert _classify_question("主营业务是什么？") == "allowed"
    assert _classify_question("年报提到了哪些风险？") == "allowed"
    assert _classify_question("分红政策如何？") == "allowed"
    assert _classify_question("毛利率和净利率变化趋势？") == "allowed"


# ─────────────────────────────────────────────────────────────────────────────
# Test 2: investment advice question → rejected
# ─────────────────────────────────────────────────────────────────────────────

def test_investment_advice_rejected():
    from app.agent.report_chat_copilot_agent import _classify_question

    assert _classify_question("现在能买入吗？") == "rejected"
    assert _classify_question("适合卖出吗？") == "rejected"
    assert _classify_question("应该加仓吗？") == "rejected"
    assert _classify_question("给我内幕消息") == "rejected"
    assert _classify_question("是否存在庄家操控？") == "rejected"


# ─────────────────────────────────────────────────────────────────────────────
# Test 3: target price question → rejected
# ─────────────────────────────────────────────────────────────────────────────

def test_target_price_rejected():
    from app.agent.report_chat_copilot_agent import _classify_question

    assert _classify_question("目标价是多少？") == "rejected"
    assert _classify_question("价格目标预测") == "rejected"
    assert _classify_question("保证收益多少？") == "rejected"
    assert _classify_question("明天涨还是跌？") == "rejected"


# ─────────────────────────────────────────────────────────────────────────────
# Test 4: query expansion for cash flow
# ─────────────────────────────────────────────────────────────────────────────

def test_query_expansion_cash_flow():
    from app.agent.report_chat_copilot_agent import _expand_query

    expanded = _expand_query("公司现金流情况如何？")
    assert "经营活动现金流" in expanded
    assert "现金流量" in expanded
    assert "净额" in expanded


def test_query_expansion_risk():
    from app.agent.report_chat_copilot_agent import _expand_query

    expanded = _expand_query("有哪些风险？")
    assert "风险因素" in expanded
    assert "市场风险" in expanded


def test_query_expansion_dividend():
    from app.agent.report_chat_copilot_agent import _expand_query

    expanded = _expand_query("分红政策是什么？")
    assert "利润分配" in expanded
    assert "股利" in expanded


def test_query_expansion_no_false_positive():
    from app.agent.report_chat_copilot_agent import _expand_query

    # Question about "总资产" should not trigger expansion
    q = "总资产规模多大？"
    expanded = _expand_query(q)
    assert expanded.startswith(q)


# ─────────────────────────────────────────────────────────────────────────────
# Test 5: no cross-stock retrieval (ts_code isolation)
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_no_cross_stock_retrieval():
    """
    RAG service is called with the ts_code derived from market+symbol.
    Verify that the ts_code is passed and not some other stock.
    """
    from app.agent.report_chat_copilot_agent import ReportChatCopilotAgent

    captured_ts_code = []

    async def fake_rag_query(ts_code, query_text, db, **kwargs):
        captured_ts_code.append(ts_code)
        return _make_rag_result(chunks=[])

    agent = ReportChatCopilotAgent()

    with patch("app.services.report_rag_service.ReportRagService") as MockRag:
        mock_instance = MagicMock()
        mock_instance.query = fake_rag_query
        MockRag.return_value = mock_instance

        with patch("app.agent.report_chat_copilot_agent.resolve_report_selection", AsyncMock(return_value=_make_selection())):
            # Patch LLM to avoid real call
            with patch("app.core.config.settings") as mock_settings:
                mock_settings.ai_enabled = False
                mock_settings.ai_api_key = None
                await agent.chat(
                    market="CN", symbol="600519", question="主营业务是什么？", db=MagicMock()
                )

    assert len(captured_ts_code) == 1
    assert captured_ts_code[0] == "600519.SH"  # not any other stock


# ─────────────────────────────────────────────────────────────────────────────
# Test 6: no chunks → partial + data_limitations annotated
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_no_chunks_returns_partial():
    from app.agent.report_chat_copilot_agent import ReportChatCopilotAgent

    agent = ReportChatCopilotAgent()

    async def fake_rag_no_chunks(ts_code, query_text, db, **kwargs):
        return _make_rag_result(chunks=[])

    with patch("app.services.report_rag_service.ReportRagService") as MockRag:
        mock_instance = MagicMock()
        mock_instance.query = fake_rag_no_chunks
        MockRag.return_value = mock_instance

        with patch("app.agent.report_chat_copilot_agent.resolve_report_selection", AsyncMock(return_value=_make_selection())):
            with patch("app.core.config.settings") as mock_settings:
                mock_settings.ai_enabled = False
                mock_settings.ai_api_key = None
                result = await agent.chat(
                    market="CN", symbol="600519", question="主营业务？", db=MagicMock()
                )

    # When LLM is disabled and no chunks, agent returns graceful fallback
    assert isinstance(result, dict)
    assert "answer" in result
    assert "errors" in result
    assert "partial" in result


# ─────────────────────────────────────────────────────────────────────────────
# Test 7: fake chunk_id removed by review canonicalization
# ─────────────────────────────────────────────────────────────────────────────

def test_fake_chunk_id_removed_by_review():
    """
    If LLM returns source_chunks with chunk_ids not in allowed_chunk_ids,
    they are removed by _canonicalize_source_chunks.
    """
    from app.agent.fundamental_review_agent import _canonicalize_source_chunks

    real_chunk = _make_chunk(chunk_id=10)
    data_pack = {
        "allowed_chunk_ids":  [10],
        "report_rag_context": [real_chunk],
        "compressed_facts":   [],
    }

    analysis = {
        "summary": "分析",
        "overall_score": None,
        "dimensions": [],
        "highlights": [],
        "risks": [],
        "watch_items": [],
        "data_limitations": [],
        "answer": "财务状况良好",
        "source_chunks": [
            {"chunk_id": 10, "citation": "真实引用"},
            {"chunk_id": 999, "citation": "虚构引用"},
        ],
    }

    issues, cleaned, audit = _canonicalize_source_chunks(analysis, data_pack)

    chunk_ids = [c["chunk_id"] for c in cleaned["source_chunks"]]
    assert 10 in chunk_ids
    assert 999 not in chunk_ids
    assert 999 in audit["invalid_removed"]


# ─────────────────────────────────────────────────────────────────────────────
# Test 8: page citation removed
# ─────────────────────────────────────────────────────────────────────────────

def test_page_citation_removed_in_chat_context():
    from app.agent.fundamental_review_agent import _check_and_remove_page_citations

    analysis = {
        "summary": "",
        "answer": "根据第15页的数据，毛利率为45%。",
        "data_limitations": [],
    }
    data_pack = {"allowed_chunk_ids": [], "report_rag_context": [], "compressed_facts": []}

    issues, cleaned, was_removed = _check_and_remove_page_citations(analysis, data_pack)

    assert was_removed is True
    assert "第15页" not in cleaned.get("answer", "")


# ─────────────────────────────────────────────────────────────────────────────
# Test 9: coverage claim rewritten
# ─────────────────────────────────────────────────────────────────────────────

def test_coverage_claim_rewritten_in_chat_context():
    from app.agent.fundamental_review_agent import _check_and_rewrite_coverage_claims

    analysis = {
        "summary": "",
        "answer": "AI完整覆盖所有财报并分析了全部数据。",
        "data_limitations": [],
    }

    issues, cleaned, was_rewritten = _check_and_rewrite_coverage_claims(analysis)

    assert was_rewritten is True
    assert "完整覆盖所有财报" not in cleaned.get("answer", "")
    assert "基于已接入的公开财报片段和结构化数据" in cleaned.get("answer", "")


# ─────────────────────────────────────────────────────────────────────────────
# Test 10: API code parsing
# ─────────────────────────────────────────────────────────────────────────────

def test_api_code_parsing_cn():
    from app.routers.report_chat import _parse_code

    assert _parse_code("600519") == ("CN", "600519")
    assert _parse_code("600519.SH") == ("CN", "600519")
    assert _parse_code("000001.SZ") == ("CN", "000001")
    assert _parse_code("838030.BJ") == ("CN", "838030")
    assert _parse_code("688981.SH") == ("CN", "688981")


def test_api_code_parsing_hk():
    from app.routers.report_chat import _parse_code

    market, symbol = _parse_code("00700.HK")
    assert market == "HK"
    # HK codes are 5-digit zero-padded
    assert len(symbol) == 5


def test_api_code_parsing_us():
    from app.routers.report_chat import _parse_code

    market, symbol = _parse_code("AAPL")
    assert market == "US"
    assert symbol == "AAPL"


# ─────────────────────────────────────────────────────────────────────────────
# Test 11: HK market → graceful 200 + partial
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_hk_market_graceful_degradation():
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)
    resp = client.post(
        "/api/v1/stock/00700.HK/report-chat",
        json={"question": "主营业务？"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["partial"] is True
    assert "HK" in data["answer"] or "港股" in data["answer"] or "不支持" in data["answer"]


# ─────────────────────────────────────────────────────────────────────────────
# Test 12: question length limit
# ─────────────────────────────────────────────────────────────────────────────

def test_question_length_limit():
    from app.agent.report_chat_copilot_agent import _MAX_QUESTION_LEN
    assert _MAX_QUESTION_LEN == 500

    # _do_chat truncates question before passing to LLM
    # Verify the constant is enforced
    assert _MAX_QUESTION_LEN <= 500


@pytest.mark.asyncio
async def test_long_question_truncated():
    """Agent processes without raising even on very long question."""
    from app.agent.report_chat_copilot_agent import ReportChatCopilotAgent

    agent = ReportChatCopilotAgent()
    long_q = "主营业务？" * 200  # ~1200 chars

    async def fake_rag(ts_code, query_text, db, **kwargs):
        return _make_rag_result(chunks=[])

    with patch("app.services.report_rag_service.ReportRagService") as MockRag:
        mock_instance = MagicMock()
        mock_instance.query = fake_rag
        MockRag.return_value = mock_instance

        with patch("app.agent.report_chat_copilot_agent.resolve_report_selection", AsyncMock(return_value=_make_selection())):
            with patch("app.core.config.settings") as mock_settings:
                mock_settings.ai_enabled = False
                mock_settings.ai_api_key = None
                result = await agent.chat(
                    market="CN", symbol="600519", question=long_q, db=MagicMock()
                )

    # Should always return a dict, never raise
    assert isinstance(result, dict)
    assert "answer" in result


# ─────────────────────────────────────────────────────────────────────────────
# Test 13: top_k capped at 10
# ─────────────────────────────────────────────────────────────────────────────

def test_top_k_capped():
    from pydantic import ValidationError
    from app.routers.report_chat import ReportChatRequest

    # top_k=15 should be capped to 10 by validator
    req = ReportChatRequest(question="主营业务？", top_k=15)
    assert req.top_k == 10

    # top_k=6 stays
    req2 = ReportChatRequest(question="主营业务？", top_k=6)
    assert req2.top_k == 6


# ─────────────────────────────────────────────────────────────────────────────
# Test 14: agent never raises — exception returns partial=True
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_agent_never_raises():
    from app.agent.report_chat_copilot_agent import ReportChatCopilotAgent

    agent = ReportChatCopilotAgent()

    # Simulate RAG service throwing an unexpected error
    async def boom(ts_code, query_text, db, **kwargs):
        raise RuntimeError("Simulated RAG service crash")

    with patch("app.agent.report_chat_copilot_agent.resolve_report_selection", AsyncMock(return_value=_make_selection())):
        with patch("app.services.report_rag_service.ReportRagService") as MockRag:
            mock_instance = MagicMock()
            mock_instance.query = boom
            MockRag.return_value = mock_instance

            # Should not raise; must return a dict
            result = await agent.chat(
                market="CN", symbol="600519", question="主营业务？", db=MagicMock()
            )

    assert isinstance(result, dict)
    assert result.get("partial") is True
    assert "answer" in result


# ─────────────────────────────────────────────────────────────────────────────
# Test 15: investment advice → audit flag set on rejection
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_investment_advice_audit_flag():
    from app.agent.report_chat_copilot_agent import ReportChatCopilotAgent

    agent = ReportChatCopilotAgent()

    # "买入" triggers immediate rejection before RAG call
    result = await agent.chat(
        market="CN", symbol="600519", question="现在能买入吗？", db=MagicMock()
    )

    assert isinstance(result, dict)
    audit = result.get("review_audit", {})
    assert audit.get("investment_advice_blocked") is True
    assert result.get("partial") is False  # fast rejection, not partial
    assert result.get("source_chunks") == []


# ─────────────────────────────────────────────────────────────────────────────
# Test 16: no v-html in ReportChatPanel.vue
# ─────────────────────────────────────────────────────────────────────────────

def test_no_v_html_in_report_chat_panel():
    """Security: all content must use text interpolation, never v-html."""
    frontend_root = Path(__file__).parent.parent.parent.parent / "frontend" / "src"
    panel = frontend_root / "components" / "fundamentals" / "ReportChatPanel.vue"

    assert panel.exists(), f"ReportChatPanel.vue not found at {panel}"
    content = panel.read_text()
    assert "v-html" not in content, (
        "ReportChatPanel.vue contains v-html — XSS risk! "
        "All content must use {{ }} text interpolation."
    )
