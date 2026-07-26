from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _ctx(memory_context=None):
    return SimpleNamespace(
        db=MagicMock(),
        user_id="u1",
        session_id="s1",
        output_language="zh-CN",
        tool_registry=MagicMock(),
        event_callback=None,
        memory_context=memory_context,
    )


def _memory(active_entities=None, resolved_query=""):
    active_entities = active_entities or []
    return SimpleNamespace(
        active_entities=active_entities,
        resolved_query=resolved_query,
        is_empty=lambda: not active_entities and not resolved_query,
        to_prompt_block=lambda: "实体：" + ",".join(getattr(e, "name", "") for e in active_entities),
    )


def _stock(name="贵州茅台", code="600519", market="CN"):
    return SimpleNamespace(type="stock", name=name, code=code, market=market)


def test_phase6u_general_fixture_has_30_cases():
    fixture = Path(__file__).parents[1] / "fixtures" / "phase6u_general_financial_cases.json"
    cases = json.loads(fixture.read_text(encoding="utf-8"))
    assert len(cases) == 30
    assert {case["id"] for case in cases}


def test_phase6u_general_can_handle_boundaries():
    from app.agents.chat_skills.general_financial_answer_skill import GeneralFinancialAnswerSkill

    skill = GeneralFinancialAnswerSkill()
    context = _ctx()

    assert skill.can_handle("贵州茅台最近表现如何？", context) is True
    assert skill.can_handle("解释最近报告", context) is False
    assert skill.can_handle("贵州茅台近期有哪些新闻？", context) is False
    assert skill.can_handle("贵州茅台为什么大涨？", context) is False
    assert skill.can_handle("贵州茅台有哪些主要风险？", context) is False
    assert skill.can_handle("贵州茅台和宁德时代盈利能力对比。", context) is False
    assert skill.can_handle("综合分析贵州茅台。", context) is False
    assert skill.can_handle("你好", context) is False
    assert skill.can_handle("帮我写一首诗", context) is False


@pytest.mark.asyncio
async def test_phase6u_general_clarifies_missing_entity():
    from app.agents.chat_skills.general_financial_answer_skill import GeneralFinancialAnswerSkill

    result = await GeneralFinancialAnswerSkill().run("它怎么样？", _ctx())

    assert result.ok is True
    assert "请补充公司名称" in result.answer
    assert result.metadata["routing_decision"]["action"] == "clarify"


@pytest.mark.asyncio
async def test_phase6u_general_inherits_single_memory_symbol_and_new_entity_overrides():
    from app.agents.chat_skills.general_financial_answer_skill import GeneralFinancialAnswerSkill

    captured: list[str] = []

    async def fake_run(**kwargs):
        captured.append(kwargs["query"])
        return SimpleNamespace(answer_text="## 结论摘要\n已回答。\n\n_仅供研究参考，不构成投资建议。_", tool_calls=[])

    memory = _memory(active_entities=[_stock()])
    with patch("app.agents.financial_agent.FinancialAgent") as MockAgent:
        MockAgent.return_value.run = fake_run
        await GeneralFinancialAnswerSkill().run("它怎么样？", _ctx(memory))
        await GeneralFinancialAnswerSkill().run("宁德时代最近表现如何？", _ctx(memory))

    assert "贵州茅台" in captured[0]
    assert "宁德时代" in captured[1]
    assert "贵州茅台" not in captured[1]


def test_phase6u_comparison_target_deferred_to_compare_route():
    from app.agents.chat_skills.general_financial_answer_skill import GeneralFinancialAnswerSkill

    skill = GeneralFinancialAnswerSkill()
    memory = _memory(active_entities=[_stock()])

    assert skill.can_handle("和宁德时代相比呢？", _ctx(memory)) is False


def test_phase6u_final_answer_hardening_no_evidence_and_schema():
    from app.agents.financial_agent import _harden_final_answer, _render_final_answer
    from app.agents.schemas import DataQuality, FinalAnswer

    dq = DataQuality()
    fa = FinalAnswer(summary="贵州茅台价格为 999 元。", analysis="明天会涨 10%。")
    hardened = _harden_final_answer(fa, [], [], dq)
    text = _render_final_answer(hardened, "贵州茅台最近表现如何？")

    assert hardened.data_quality.level == "insufficient"
    assert "999" not in text
    assert "10%" not in text
    assert "工具异常不代表公司没有相关数据" in text
    assert hasattr(hardened, "summary")
    assert hasattr(hardened, "data_points")


def test_phase6u_sources_dedup_and_unsupported_numbers_removed():
    from app.agents.financial_agent import _harden_final_answer, _render_final_answer
    from app.agents.schemas import DataPoint, DataQuality, FinalAnswer, SourceRef, ToolCallRecord

    tc = ToolCallRecord(
        tool_name="stock_quote_tool",
        display_name="查询 600519 实时行情",
        status="success",
        result_summary="600519 价格: 100 涨跌: +1%",
    )
    fa = FinalAnswer(
        summary="价格 100，成交额 999。",
        data_points=[DataPoint(label="行情", value="600519 价格: 100 涨跌: +1%")],
        analysis="价格 100 来自行情，999 没有来源。",
        sources=[
            SourceRef(title="查询 600519 实时行情", source_type="market_quote", source="stock_quote_tool"),
            SourceRef(title="查询 600519 实时行情", source_type="market_quote", source="stock_quote_tool"),
        ],
        data_quality=DataQuality(level="medium"),
    )

    hardened = _harden_final_answer(fa, [tc], [], fa.data_quality)
    text = _render_final_answer(hardened, "贵州茅台最新价格是多少？")

    assert len(hardened.sources) == 1
    assert "100" in text
    assert "999" not in text
    assert "未提供数字" in text


@pytest.mark.asyncio
async def test_phase6u_fallback_without_evidence_does_not_call_llm_or_fabricate():
    from app.agents.chat_rag.base import RAGResult
    from app.agents.chat_skills.general_financial_answer_skill import GeneralFinancialAnswerSkill

    async def boom_run(**kwargs):
        raise RuntimeError("/tmp/provider traceback api_key=secret")

    with patch("app.agents.financial_agent.FinancialAgent") as MockAgent:
        MockAgent.return_value.run = boom_run
        with patch(
            "app.agents.chat_skills.general_financial_answer_skill.retrieve_context",
            new=AsyncMock(return_value=RAGResult(ok=True, query="贵州茅台最近表现如何？", documents=[])),
        ):
            with patch("app.llm.factory.get_llm_client") as mock_llm:
                result = await GeneralFinancialAnswerSkill().run("贵州茅台最近表现如何？", _ctx())

    mock_llm.assert_not_called()
    assert "没有可用的工具结果" in result.answer
    assert "api_key" not in result.answer.lower()
    assert "/tmp/" not in result.answer
    assert "买入" not in result.answer
    assert "chain of thought" not in result.answer.lower()


@pytest.mark.asyncio
async def test_phase6u_chat_llm_fallback_no_evidence_is_limited():
    from app.agents.chat_llm_answerer import generate_answer

    with patch("app.llm.factory.get_llm_client") as mock_llm:
        answer = await generate_answer(
            user_message="贵州茅台最近表现如何？",
            tool_results=[],
            rag_documents=[],
            fallback_mode=True,
            data_quality={"level": "insufficient"},
        )

    mock_llm.assert_not_called()
    assert "证据不足" in answer
    assert "具体股票事实" in answer


@pytest.mark.asyncio
async def test_phase6u_financial_agent_answer_text_is_final_answer_view():
    from app.agents.financial_agent import FinancialAgent

    events: list[dict] = []

    async def cb(event_type, payload):
        events.append({"type": event_type, "payload": payload})

    class LLM:
        async def async_stream_chat(self, messages, **kwargs):
            async def gen():
                yield {"type": "answer", "content": (
                    "### 研究摘要\n\nAAPL 价格为 180.00 USD。\n\n"
                    "### 关键数据\n\n- 价格: 180.00 USD\n\n"
                    "### 分析\n\n价格来自工具数据。\n\n"
                    "### 风险提示\n\n- 市场波动风险\n"
                )}
            return gen()

    with patch("app.llm.factory.get_llm_client", return_value=LLM()):
        with patch("app.agents.financial_agent._fetch_us_quote", AsyncMock(return_value={
            "ok": True,
            "symbol": "AAPL",
            "market": "US",
            "price": 180.00,
            "change": 1.50,
            "change_pct": "+0.84%",
            "currency": "USD",
        })):
            response = await FinancialAgent().run(
                query="AAPL 最新价格是多少？",
                db=MagicMock(),
                tool_registry=MagicMock(),
                event_callback=cb,
            )

    assert response.final_answer.summary in response.answer_text
    assert response.answer_text.count("## 结论") == 1
    assert "180.00" in response.answer_text
    assert any(e["type"] == "final_answer" for e in events)
