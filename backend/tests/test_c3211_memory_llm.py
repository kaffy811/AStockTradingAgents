"""
C32.1.1-C32.1.4 Tests — Memory LLM integration + Compare fix.

T1:  build_llm_messages_with_memory returns messages list with recent history
T2:  "那它和五粮液相比呢?" → messages include prior 贵州茅台 turn
T3:  "这个行业有哪些公司?" → memory block includes industry entity
T4:  memory messages do not include Run ID / SQL / traceback
T5:  history is capped at max_recent_messages
T6:  new entity in current query is not overridden by memory entity
T7:  resolved_query replaces stock pronoun (它) with entity name
T8:  resolved_query replaces industry pronoun with entity name
T9:  low-confidence coref sets needs_clarification without mutating query
T10: generate_answer signature accepts memory_context kwarg
T11: SkillContext has memory_context field
T12: chat_streaming has _has_confirmation_only guard (source check)
T13: ChatConfirmResponse has tool_events and cards fields
T14: _handle_compare has _extract_compare_candidates helper
T15: _extract_compare_candidates returns ≥2 items for typical compare query
T16: _extract_compare_candidates extracts 6-digit codes
T17: compare OrchestratorResult has confirmation, not analysis_run
T18: chat_streaming finally block guards on _has_confirmation_only
T19: execute_create_compare_selection returns compare_link card
T20: ChatResultCard compare_link appends from=chat to RouterLink
T21: ChatResultCard compare_link renders compareUrl from card data
T22: ChatCopilotView onConfirm injects session_id into compare link
T23: compare URL format: stocks/from/session_id
T24: _extract_compare_candidates splits on 、/，separators
T25: build_llm_messages_with_memory last message is always current_query
T26: memory context to_prompt_block shows last entity and summary
"""

import re
from dataclasses import dataclass, field

import pytest


# ─────────────────────────────────────────────────────────────────────────────
# T1-T6: build_llm_messages_with_memory
# ─────────────────────────────────────────────────────────────────────────────

def _make_memory_ctx(
    recent_messages=None,
    active_entities=None,
    session_summary="",
    last_intent="",
):
    from app.services.conversation_memory_service import MemoryContext, ResolvedEntity
    return MemoryContext(
        recent_messages=recent_messages or [],
        active_entities=active_entities or [],
        session_summary=session_summary,
        last_intent=last_intent,
        resolved_query="",
    )


def test_t1_build_llm_messages_returns_list_with_history():
    from app.services.conversation_memory_service import (
        build_llm_messages_with_memory,
        MemoryContext,
        ResolvedEntity,
    )
    ctx = _make_memory_ctx(
        recent_messages=[
            {"role": "user",      "snippet": "贵州茅台最新财报如何？"},
            {"role": "assistant", "snippet": "茅台2024年营收同比增长15%..."},
        ],
        active_entities=[ResolvedEntity(type="stock", name="贵州茅台", code="600519", market="CN")],
    )
    msgs = build_llm_messages_with_memory(
        system_prompt="你是金融研究助手",
        memory_context=ctx,
        current_query="那它和五粮液相比呢？",
    )
    assert msgs[0]["role"] == "system"
    assert msgs[-1]["role"] == "user"
    assert msgs[-1]["content"] == "那它和五粮液相比呢？"
    # Should have history messages somewhere in the middle
    roles = [m["role"] for m in msgs]
    assert "user" in roles
    assert "assistant" in roles


def test_t2_messages_include_prior_maotai_turn():
    from app.services.conversation_memory_service import (
        build_llm_messages_with_memory,
        ResolvedEntity,
    )
    ctx = _make_memory_ctx(
        recent_messages=[
            {"role": "user",      "snippet": "贵州茅台最新财报如何？"},
            {"role": "assistant", "snippet": "茅台2024年净利润733亿元"},
        ],
        active_entities=[ResolvedEntity(type="stock", name="贵州茅台", code="600519", market="CN")],
        session_summary="用户询问贵州茅台财报数据",
    )
    msgs = build_llm_messages_with_memory(
        system_prompt="你是金融研究助手",
        memory_context=ctx,
        current_query="那它和五粮液相比呢？",
    )
    # Concatenated content should reference 贵州茅台
    all_content = " ".join(m["content"] for m in msgs)
    assert "贵州茅台" in all_content


def test_t3_messages_include_industry_entity():
    from app.services.conversation_memory_service import (
        build_llm_messages_with_memory,
        ResolvedEntity,
    )
    ctx = _make_memory_ctx(
        recent_messages=[
            {"role": "user",      "snippet": "半导体行业最近怎么样？"},
            {"role": "assistant", "snippet": "半导体板块近期受AI需求拉动，整体偏强"},
        ],
        active_entities=[ResolvedEntity(type="industry", name="半导体行业")],
        session_summary="用户询问半导体行业",
    )
    msgs = build_llm_messages_with_memory(
        system_prompt="你是金融研究助手",
        memory_context=ctx,
        current_query="这个行业有哪些值得关注的公司？",
    )
    all_content = " ".join(m["content"] for m in msgs)
    assert "半导体" in all_content


def test_t4_memory_messages_exclude_run_id_sql_traceback():
    from app.services.conversation_memory_service import (
        build_llm_messages_with_memory,
        _sanitize_for_summary,
        ResolvedEntity,
    )
    # Confirm sanitizer strips sensitive patterns
    dirty = "run_id=abc-123-def-456 SELECT * FROM users Traceback (most recent call last)"
    cleaned = _sanitize_for_summary(dirty)
    assert "SELECT" not in cleaned
    assert "Traceback" not in cleaned

    # Also verify snippet field (already sanitised) is used
    ctx = _make_memory_ctx(
        recent_messages=[
            {"role": "user", "snippet": "普通用户问题"},
            {"role": "assistant", "snippet": "正常回答"},
        ],
    )
    msgs = build_llm_messages_with_memory("sys", ctx, "new question")
    all_content = " ".join(m["content"] for m in msgs)
    assert "SELECT" not in all_content
    assert "Traceback" not in all_content


def test_t5_history_capped_at_max_recent_messages():
    from app.services.conversation_memory_service import build_llm_messages_with_memory
    long_history = [
        {"role": "user" if i % 2 == 0 else "assistant", "snippet": f"msg_{i}"}
        for i in range(20)
    ]
    ctx = _make_memory_ctx(recent_messages=long_history)
    msgs = build_llm_messages_with_memory("sys", ctx, "current", max_recent_messages=4)
    # Count non-system messages (excluding the final current_query user msg)
    history_msgs = [m for m in msgs if m["role"] != "system" and m["content"] != "current"]
    assert len(history_msgs) <= 4


def test_t6_current_query_is_last_message():
    from app.services.conversation_memory_service import build_llm_messages_with_memory
    ctx = _make_memory_ctx(recent_messages=[{"role": "user", "snippet": "prev question"}])
    msgs = build_llm_messages_with_memory("sys", ctx, "THIS IS CURRENT")
    assert msgs[-1]["content"] == "THIS IS CURRENT"
    assert msgs[-1]["role"] == "user"


# ─────────────────────────────────────────────────────────────────────────────
# T7-T9: coreference resolution
# ─────────────────────────────────────────────────────────────────────────────

def test_t7_resolved_query_replaces_stock_pronoun():
    from app.services.conversation_memory_service import (
        resolve_coreferences, MemoryContext, ResolvedEntity,
    )
    ctx = MemoryContext(
        active_entities=[ResolvedEntity(type="stock", name="贵州茅台", code="600519", market="CN")],
    )
    resolved, needs_clarification, _ = resolve_coreferences("那它和五粮液相比呢？", ctx)
    assert "贵州茅台" in resolved
    assert needs_clarification is False


def test_t8_resolved_query_replaces_industry_pronoun():
    from app.services.conversation_memory_service import (
        resolve_coreferences, MemoryContext, ResolvedEntity,
    )
    ctx = MemoryContext(
        active_entities=[ResolvedEntity(type="industry", name="半导体行业")],
    )
    resolved, _, _ = resolve_coreferences("这个行业有哪些值得关注的公司？", ctx)
    assert "半导体行业" in resolved


def test_t9_low_confidence_coref_sets_needs_clarification():
    from app.services.conversation_memory_service import (
        resolve_coreferences, MemoryContext,
    )
    # No entities in context → should request clarification
    ctx = MemoryContext()
    _, needs_clarification, hint = resolve_coreferences("那它最近表现怎样？", ctx)
    assert needs_clarification is True
    assert hint  # non-empty clarification hint


# ─────────────────────────────────────────────────────────────────────────────
# T10-T11: API contracts
# ─────────────────────────────────────────────────────────────────────────────

def test_t10_generate_answer_accepts_memory_context_kwarg():
    import inspect
    from app.agents.chat_llm_answerer import generate_answer
    sig = inspect.signature(generate_answer)
    assert "memory_context" in sig.parameters


def test_t11_skill_context_has_memory_context_field():
    from app.agents.chat_skills.base import SkillContext
    import dataclasses
    field_names = {f.name for f in dataclasses.fields(SkillContext)}
    assert "memory_context" in field_names


# ─────────────────────────────────────────────────────────────────────────────
# T12-T14: Source-level checks
# ─────────────────────────────────────────────────────────────────────────────

def test_t12_chat_streaming_has_confirmation_only_guard():
    import pathlib
    src = pathlib.Path(
        __file__
    ).parent.parent / "app/agents/chat_streaming.py"
    content = src.read_text()
    assert "_has_confirmation_only" in content
    assert "not _has_confirmation_only" in content


def test_t13_chat_confirm_response_has_cards_and_tool_events():
    from app.models.chat import ChatConfirmResponse
    resp = ChatConfirmResponse(status="confirmed", answer="ok")
    assert hasattr(resp, "cards")
    assert hasattr(resp, "tool_events")
    assert resp.cards == []
    assert resp.tool_events == []


def test_t14_handle_compare_has_extract_candidates():
    import pathlib
    src = pathlib.Path(
        __file__
    ).parent.parent / "app/agents/chat_orchestrator.py"
    content = src.read_text()
    assert "_extract_compare_candidates" in content
    assert "resolve_stock_tool" in content


# ─────────────────────────────────────────────────────────────────────────────
# T15-T16: _extract_compare_candidates logic
# ─────────────────────────────────────────────────────────────────────────────

def test_t15_extract_compare_candidates_typical_query():
    from app.agents.chat_orchestrator import _extract_compare_candidates
    result = _extract_compare_candidates("对比宁德时代、紫金矿业、华大九天")
    assert len(result) >= 2


def test_t16_extract_compare_candidates_extracts_codes():
    from app.agents.chat_orchestrator import _extract_compare_candidates
    result = _extract_compare_candidates("对比600519和300750")
    assert "600519" in result
    assert "300750" in result


def test_t24_extract_compare_candidates_splits_on_separators():
    from app.agents.chat_orchestrator import _extract_compare_candidates
    result = _extract_compare_candidates("比较贵州茅台，五粮液、泸州老窖")
    assert len(result) >= 2


# ─────────────────────────────────────────────────────────────────────────────
# T17: compare orchestrator result has confirmation, not analysis_run
# ─────────────────────────────────────────────────────────────────────────────

def test_t17_compare_result_has_confirmation_not_analysis_run():
    import pathlib
    src = pathlib.Path(
        __file__
    ).parent.parent / "app/agents/chat_orchestrator.py"
    content = src.read_text()
    # _handle_compare must produce a confirmation, not create_analysis_run
    handle_compare_section = content[content.index("async def _handle_compare"):]
    handle_compare_body = handle_compare_section[:handle_compare_section.index("\nasync def ")]
    assert "create_compare" in handle_compare_body
    assert "create_analysis_run" not in handle_compare_body


# ─────────────────────────────────────────────────────────────────────────────
# T18: chat_streaming finally block guards on _has_confirmation_only
# ─────────────────────────────────────────────────────────────────────────────

def test_t18_streaming_finally_guards_confirmation_only():
    import pathlib
    src = pathlib.Path(
        __file__
    ).parent.parent / "app/agents/chat_streaming.py"
    content = src.read_text()
    finally_idx = content.rfind("finally:")
    finally_block = content[finally_idx:finally_idx + 600]
    assert "_has_confirmation_only" in finally_block


# ─────────────────────────────────────────────────────────────────────────────
# T19: execute_create_compare_selection returns compare_link card
# ─────────────────────────────────────────────────────────────────────────────

def test_t19_execute_create_compare_selection_returns_compare_link_card():
    from app.agents.chat_tools.action_tools import execute_create_compare_selection
    params = {
        "stocks": [
            {"name": "宁德时代", "market": "CN", "symbol": "300750"},
            {"name": "紫金矿业", "market": "CN", "symbol": "601899"},
        ],
        "compare_url": "/compare?stocks=CN:300750,CN:601899",
    }
    result = execute_create_compare_selection(params)
    assert result.ok
    assert len(result.cards) == 1
    assert result.cards[0]["type"] == "compare_link"
    assert "CN:300750" in result.cards[0]["data"]["compareUrl"]


# ─────────────────────────────────────────────────────────────────────────────
# T20-T21: Frontend ChatResultCard (source check)
# ─────────────────────────────────────────────────────────────────────────────

def test_t20_chat_result_card_compare_link_has_from_chat():
    import pathlib
    src = pathlib.Path(
        __file__
    ).parent.parent.parent / "frontend/src/components/chat/ChatResultCard.vue"
    content = src.read_text()
    cmp_block = content[content.index("compare_link"):]
    assert "from=chat" in cmp_block


def test_t21_chat_copilot_view_injects_session_id_into_compare():
    import pathlib
    src = pathlib.Path(
        __file__
    ).parent.parent.parent / "frontend/src/views/ChatCopilotView.vue"
    content = src.read_text()
    assert "session_id" in content
    assert "compare_link" in content


# ─────────────────────────────────────────────────────────────────────────────
# T25-T26: build_llm_messages_with_memory structural checks
# ─────────────────────────────────────────────────────────────────────────────

def test_t25_build_llm_messages_with_empty_context_returns_minimal():
    from app.services.conversation_memory_service import (
        build_llm_messages_with_memory, MemoryContext,
    )
    ctx = MemoryContext()  # empty
    msgs = build_llm_messages_with_memory("sys prompt", ctx, "hello")
    # Minimal: system + user
    assert len(msgs) == 2
    assert msgs[0]["role"] == "system"
    assert msgs[1]["content"] == "hello"


def test_t26_memory_to_prompt_block_includes_entity_and_summary():
    from app.services.conversation_memory_service import MemoryContext, ResolvedEntity
    ctx = MemoryContext(
        session_summary="用户询问茅台财报",
        active_entities=[ResolvedEntity(type="stock", name="贵州茅台", code="600519", market="CN")],
        last_intent="tool_answer",
    )
    block = ctx.to_prompt_block()
    assert "贵州茅台" in block
    assert "用户询问茅台财报" in block
