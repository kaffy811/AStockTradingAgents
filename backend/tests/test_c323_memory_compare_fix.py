"""
C32.3 Test Suite — Memory Runtime Final Fix + Marker Restore + Sidebar Filter

Tests:
  T1–T6   : _extract_compare_candidates memory_context fallback (C32.3.1)
  T7–T10  : build_memory_context entity fallback from recent_messages (C32.3.2)
  T11–T13 : General multi-turn Q&A memory enters LLM messages (C32.3.3)
  T14–T19 : ConversationMarkers frontend spec (static checks)
  T20–T25 : Sidebar time-chips removal spec (static checks)
"""
from __future__ import annotations

import re
import pytest

# ─────────────────────────────────────────────────────────────────────────────
# Imports from production code
# ─────────────────────────────────────────────────────────────────────────────

from app.services.conversation_memory_service import (
    MemoryContext,
    ResolvedEntity,
    _entity_from_text,
    _MEMORY_STOCK_TABLE,
    resolve_coreferences,
    build_llm_messages_with_memory,
)
from app.agents.chat_orchestrator import (
    _extract_compare_candidates,
    _match_compare,
)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _maotai_entity() -> ResolvedEntity:
    return ResolvedEntity(type="stock", name="贵州茅台", code="600519", market="CN")

def _wuliangye_entity() -> ResolvedEntity:
    return ResolvedEntity(type="stock", name="五粮液", code="000858", market="CN")

def _ctx_with_maotai() -> MemoryContext:
    return MemoryContext(
        active_entities=[_maotai_entity()],
        recent_messages=[
            {"role": "user",      "snippet": "贵州茅台最新财报表现如何？"},
            {"role": "assistant", "snippet": "贵州茅台2024年营收1459亿，净利润748亿..."},
        ],
    )


# ═════════════════════════════════════════════════════════════════════════════
# T1–T6: _extract_compare_candidates with memory_context fallback
# ═════════════════════════════════════════════════════════════════════════════

def test_t1_pronoun_query_with_memory_gives_two_candidates():
    """T1: '那它和五粮液相比呢？' + active_entities=贵州茅台 → 2 candidates."""
    ctx = _ctx_with_maotai()
    candidates = _extract_compare_candidates("那它和五粮液相比呢？", memory_context=ctx)
    # Should inject 600519 (贵州茅台) + extract 五粮液 → 2 candidates
    joined = " ".join(candidates)
    assert "600519" in joined or "贵州茅台" in joined, f"Expected 贵州茅台 in candidates, got {candidates}"
    assert "五粮液" in joined, f"Expected 五粮液 in candidates, got {candidates}"
    assert len(candidates) >= 2, f"Expected ≥2 candidates, got {candidates}"


def test_t2_resolved_content_with_parenthetical_gives_two_candidates():
    """T2: coreference-resolved '那贵州茅台（CN/600519）和五粮液相比呢？' → 2 candidates."""
    candidates = _extract_compare_candidates("那贵州茅台（CN/600519）和五粮液相比呢？")
    joined = " ".join(candidates)
    assert "贵州茅台" in joined or "600519" in joined, f"Got {candidates}"
    assert "五粮液" in joined, f"Got {candidates}"
    assert len(candidates) >= 2


def test_t3_explicit_names_no_memory_gives_two_candidates():
    """T3: '请对比五粮液和贵州茅台的股票' → 2 candidates without memory."""
    candidates = _extract_compare_candidates("请对比五粮液和贵州茅台的股票")
    assert len(candidates) >= 2, f"Got {candidates}"
    joined = " ".join(candidates)
    assert "五粮液" in joined
    assert "贵州茅台" in joined


def test_t4_pronoun_without_memory_gives_single_candidate():
    """T4: '那它和五粮液相比呢？' with NO memory → only finds 五粮液 (< 2)."""
    empty_ctx = MemoryContext()
    candidates = _extract_compare_candidates("那它和五粮液相比呢？", memory_context=empty_ctx)
    # Without memory, 它 cannot be resolved — expect only 五粮液
    assert "五粮液" in " ".join(candidates)
    # The code (600519) should NOT appear since memory is empty
    assert "600519" not in " ".join(candidates)


def test_t5_no_pronoun_memory_not_injected():
    """T5: '对比贵州茅台和五粮液' (no pronoun) → memory NOT injected spuriously."""
    ctx = _ctx_with_maotai()
    candidates = _extract_compare_candidates("对比贵州茅台和五粮液", memory_context=ctx)
    # Should find both from text alone; no duplication of 600519
    assert len(candidates) >= 2
    # Count occurrence of 600519 — should appear at most once
    assert " ".join(candidates).count("600519") <= 1


def test_t6_three_stock_compare():
    """T6: '对比宁德时代、紫金矿业、华大九天' → 3 candidates."""
    candidates = _extract_compare_candidates("对比宁德时代、紫金矿业、华大九天")
    assert len(candidates) >= 3, f"Got {candidates}"
    joined = " ".join(candidates)
    assert "宁德时代" in joined
    assert "紫金矿业" in joined
    assert "华大九天" in joined


# ═════════════════════════════════════════════════════════════════════════════
# T7–T10: build_memory_context entity fallback from recent_messages
# ═════════════════════════════════════════════════════════════════════════════

def test_t7_entity_from_text_finds_maotai():
    """T7: _entity_from_text('贵州茅台最新财报表现如何？') → 贵州茅台 CN/600519."""
    ent = _entity_from_text("贵州茅台最新财报表现如何？")
    assert ent is not None
    assert ent.code == "600519"
    assert ent.name == "贵州茅台"
    assert ent.market == "CN"
    assert ent.type == "stock"


def test_t8_entity_from_text_finds_wuliangye():
    """T8: _entity_from_text snippet with 五粮液 → 五粮液 CN/000858."""
    ent = _entity_from_text("五粮液最近走势怎么样？")
    assert ent is not None
    assert ent.code == "000858"
    assert ent.name == "五粮液"


def test_t9_entity_from_text_generic_6digit_code():
    """T9: _entity_from_text('分析688146') → ResolvedEntity(code='688146')."""
    ent = _entity_from_text("分析688146的走势")
    assert ent is not None
    assert ent.code == "688146"


def test_t10_entity_from_text_no_match_returns_none():
    """T10: _entity_from_text with no stock mention → None."""
    ent = _entity_from_text("今天天气怎么样？")
    assert ent is None


def test_t10b_memory_stock_table_has_required_stocks():
    """T10b: _MEMORY_STOCK_TABLE covers the 10 required A-share stocks."""
    codes = {row[0] for row in _MEMORY_STOCK_TABLE}
    required = {"600519", "000858", "300750", "601899", "301269",
                "688146", "002594", "601012", "002475", "688981"}
    assert required.issubset(codes), f"Missing codes: {required - codes}"


# ═════════════════════════════════════════════════════════════════════════════
# T11–T13: Multi-turn Q&A memory enters LLM messages (C32.3.3)
# ═════════════════════════════════════════════════════════════════════════════

def test_t11_llm_messages_include_prior_maotai_mention():
    """T11: Round-2 LLM messages contain 贵州茅台 from round-1 context."""
    ctx = _ctx_with_maotai()
    system_prompt = "你是一个金融研究助手。"
    current_query = "那它主要风险是什么？"

    messages = build_llm_messages_with_memory(system_prompt, ctx, current_query)
    full_text = " ".join(str(m) for m in messages)
    assert "贵州茅台" in full_text, "贵州茅台 not found in LLM messages"


def test_t12_llm_messages_contain_current_query():
    """T12: build_llm_messages_with_memory always includes the current query."""
    ctx = _ctx_with_maotai()
    query = "那它主要风险是什么？"
    messages = build_llm_messages_with_memory("sys", ctx, query)
    last_user = next((m for m in reversed(messages) if m.get("role") == "user"), None)
    assert last_user is not None
    assert query in last_user.get("content", "")


def test_t13_llm_messages_exclude_sensitive_fields():
    """T13: LLM messages must not contain traceback, SQL, Run ID, or API key."""
    ctx = MemoryContext(
        session_summary="用户询问贵州茅台财报",
        active_entities=[_maotai_entity()],
        recent_messages=[
            {"role": "user",      "snippet": "贵州茅台最新财报表现如何？"},
            {"role": "assistant", "snippet": "营收1459亿，净利润748亿"},
        ],
    )
    messages = build_llm_messages_with_memory("sys", ctx, "那它主要风险是什么？")
    full_text = " ".join(str(m) for m in messages)
    forbidden = [
        "Traceback", "SELECT ", "INSERT INTO", "sk-", "Bearer ",
        "sql_query", "raw_tool_args", "system_prompt",
    ]
    for token in forbidden:
        assert token.lower() not in full_text.lower(), f"Sensitive token '{token}' found in LLM messages"


# ═════════════════════════════════════════════════════════════════════════════
# T14–T19: ConversationMarkers frontend spec (static checks)
# ═════════════════════════════════════════════════════════════════════════════

def _read_markers_vue() -> str:
    import os
    path = os.path.join(
        os.path.dirname(__file__),
        "../../frontend/src/components/chat/ConversationMarkers.vue",
    )
    with open(path, encoding="utf-8") as f:
        return f.read()


def test_t14_markers_shows_when_3_user_messages():
    """T14: ConversationMarkers renders only when userMessages.length >= 3."""
    src = _read_markers_vue()
    assert "userMessages.length >= 3" in src, "Missing v-if threshold of 3"


def test_t15_markers_hidden_on_mobile():
    """T15: Marker rail hidden on mobile (max-width: 640px)."""
    src = _read_markers_vue()
    assert "max-width: 640px" in src, "Missing mobile hide rule"
    assert "display: none" in src, "Missing display:none for mobile"


def test_t16_markers_preview_15_chars():
    """T16: Marker preview shows at most 15 chars."""
    src = _read_markers_vue()
    assert "slice(0, 15)" in src, "Missing 15-char slice for preview"


def test_t17_markers_click_scrolls_to_message():
    """T17: Clicking marker calls scrollToMessage / scrollIntoView."""
    src = _read_markers_vue()
    assert "scrollToMessage" in src
    assert "scrollIntoView" in src


def test_t18_markers_use_getboundingclientrect():
    """T18: C32.3 fix — position calc uses getBoundingClientRect (not offsetTop alone)."""
    src = _read_markers_vue()
    assert "getBoundingClientRect" in src, "Missing getBoundingClientRect for accurate position"


def test_t19_markers_watch_flush_post():
    """T19: Messages watch uses flush:'post' so DOM is settled before recalc."""
    src = _read_markers_vue()
    assert "flush: 'post'" in src or "flush:'post'" in src, "Missing flush:'post' on messages watch"


# ═════════════════════════════════════════════════════════════════════════════
# T20–T25: Sidebar time-chips removal spec (static checks)
# ═════════════════════════════════════════════════════════════════════════════

def _read_sidebar_vue() -> str:
    import os
    path = os.path.join(
        os.path.dirname(__file__),
        "../../frontend/src/components/chat/ChatSessionSidebar.vue",
    )
    with open(path, encoding="utf-8") as f:
        return f.read()


def test_t20_sidebar_no_filter_chips_rendered():
    """T20: filter-chips v-for loop must not render TIME_RANGES buttons directly."""
    src = _read_sidebar_vue()
    # The old pattern: v-for="range in TIME_RANGES" inside a visible section
    # After C32.3.5 removal, this should be gone
    assert 'v-for="range in TIME_RANGES"' not in src, \
        "TIME_RANGES v-for chips still in template — should be removed"


def test_t21_sidebar_calendar_icon_present():
    """T21: Calendar icon (📅 or btn-calendar) remains in sidebar header."""
    src = _read_sidebar_vue()
    assert "btn-calendar" in src or "📅" in src, "Calendar button missing from sidebar"


def test_t22_sidebar_date_picker_popup_present():
    """T22: Date picker popup still exists (showDatePicker popover)."""
    src = _read_sidebar_vue()
    assert "showDatePicker" in src, "Missing showDatePicker — calendar popup should remain"
    assert "date-picker-popup" in src, "Missing date-picker-popup class"


def test_t23_sidebar_calendar_active_when_date_selected():
    """T23: Calendar icon shows active state when date is selected."""
    src = _read_sidebar_vue()
    assert ":class=\"{ active: dateStart" in src or "active: dateStart" in src, \
        "Missing active state on calendar button when dateStart is set"


def test_t24_sidebar_apply_date_filter_emits_search():
    """T24: applyDateRange function emits search event with date_from/date_to."""
    src = _read_sidebar_vue()
    assert "applyDateRange" in src, "Missing applyDateRange function"
    # Should emit a search event
    assert "emit('search'" in src or "$emit('search'" in src or "emit(\"search\"" in src, \
        "Missing emit('search') in sidebar — calendar filter should trigger search"


def test_t25_sidebar_clear_restores_full_list():
    """T25: clearSearch / clearDateRange resets filters and emits search."""
    src = _read_sidebar_vue()
    assert "clearSearch" in src or "clearDateRange" in src, \
        "Missing clear function in sidebar"


# ═════════════════════════════════════════════════════════════════════════════
# T26–T30: Fallback current-query-skip (C32.3-fix)
# Prevents self-referential entity extraction that caused "五粮液 vs 五粮液"
# ═════════════════════════════════════════════════════════════════════════════

from app.services.conversation_memory_service import _sanitize_for_summary


def _build_recent_messages_two_rounds() -> list[dict]:
    """
    Simulate the recent_messages list AFTER Round 2 user message is committed.
    Round 1 user: "贵州茅台最新财报表现如何？"
    Round 1 assistant: "贵州茅台2024年营收1459亿..."
    Round 2 user: "那它和五粮液相比呢？"  ← current query (committed by Phase 1)
    """
    return [
        {"role": "user",      "snippet": "贵州茅台最新财报表现如何？"},
        {"role": "assistant", "snippet": "贵州茅台2024年营收1459亿，净利润748亿..."},
        {"role": "user",      "snippet": "那它和五粮液相比呢？"},   # ← current query
    ]


def test_t26_fallback_skips_current_query_finds_prior_stock():
    """
    T26 [C32.3-fix]: When active_entities is empty, the fallback must skip
    the current query itself and find the stock from the PREVIOUS user message.

    Bug: fallback iterated newest-first and hit "那它和五粮液相比呢？" first,
    extracting 五粮液. Then coreference replaced "它"→"五粮液", producing
    "五粮液 vs 五粮液" → only 1 unique candidate → "需要至少2只股票" error.

    Fix: skip the snippet that matches current_query prefix.
    """
    current_query = "那它和五粮液相比呢？"
    _cur_prefix = _sanitize_for_summary(current_query)[:25].strip()

    recent_messages = _build_recent_messages_two_rounds()
    found_entity = None
    for recent in reversed(recent_messages):
        if recent.get("role") == "user":
            snippet = recent.get("snippet", "")
            if _cur_prefix and snippet[:25].strip() == _cur_prefix:
                continue   # skip current query
            from app.services.conversation_memory_service import _entity_from_text
            ent = _entity_from_text(snippet)
            if ent is not None:
                found_entity = ent
                break

    assert found_entity is not None, "Should find an entity from the PRIOR round"
    assert found_entity.code == "600519", \
        f"Should find 贵州茅台 (600519) from Round 1, got {found_entity}"
    assert found_entity.name == "贵州茅台"


def test_t27_fallback_does_not_extract_from_current_query():
    """
    T27: _entity_from_text on Round-2 query "那它和五粮液相比呢？"
    WOULD extract 五粮液 — this proves the current-query MUST be skipped.
    """
    from app.services.conversation_memory_service import _entity_from_text
    ent = _entity_from_text("那它和五粮液相比呢？")
    # This is a valid extraction — the bug is that it shouldn't be used as context
    assert ent is not None, "五粮液 is in the query and _entity_from_text finds it"
    assert ent.code == "000858"
    # The test proves WHY we must skip the current query in the fallback loop


def test_t28_with_correct_active_entity_compare_gives_two_candidates():
    """
    T28: After C32.3-fix, active_entities=[贵州茅台], coreference resolves
    "它"→"贵州茅台(CN/600519)", then _extract_compare_candidates finds 2 stocks.
    End-to-end simulation of the fixed Round-2 compare flow.
    """
    # Simulate: fallback correctly found 贵州茅台 from Round 1
    ctx = MemoryContext(
        active_entities=[ResolvedEntity(type="stock", name="贵州茅台", code="600519", market="CN")],
        recent_messages=[
            {"role": "user",      "snippet": "贵州茅台最新财报表现如何？"},
            {"role": "assistant", "snippet": "贵州茅台2024年营收1459亿..."},
            {"role": "user",      "snippet": "那它和五粮液相比呢？"},
        ],
    )
    # Step 1: coreference resolution
    resolved, _, _ = resolve_coreferences("那它和五粮液相比呢？", ctx)
    assert "贵州茅台" in resolved, f"Expected 贵州茅台 in resolved, got: {resolved!r}"
    assert "600519" in resolved

    # Step 2: candidate extraction from resolved query
    candidates = _extract_compare_candidates(resolved, memory_context=ctx)
    joined = " ".join(candidates)
    assert len(candidates) >= 2, f"Expected ≥2 candidates, got: {candidates}"
    assert "贵州茅台" in joined or "600519" in joined
    assert "五粮液" in joined or "000858" in joined


def test_t29_wrong_active_entity_causes_one_candidate_proving_bug():
    """
    T29: Proves the original bug — if active_entities=[五粮液] (from current query),
    coreference resolves "它"→"五粮液", giving only 1 unique candidate.
    This is WHY the fallback MUST skip the current query.
    """
    # BUG scenario: fallback incorrectly extracted 五粮液 from current query
    ctx_wrong = MemoryContext(
        active_entities=[ResolvedEntity(type="stock", name="五粮液", code="000858", market="CN")],
        recent_messages=[
            {"role": "user",      "snippet": "贵州茅台最新财报表现如何？"},
            {"role": "assistant", "snippet": "贵州茅台2024年营收1459亿..."},
            {"role": "user",      "snippet": "那它和五粮液相比呢？"},
        ],
    )
    resolved_wrong, _, _ = resolve_coreferences("那它和五粮液相比呢？", ctx_wrong)
    # Would become "那五粮液(CN/000858)和五粮液相比呢？"
    candidates_wrong = _extract_compare_candidates(resolved_wrong, memory_context=ctx_wrong)
    # After dedup: only ["五粮液"] or ["000858"] — length=1 → triggers error message
    assert len(candidates_wrong) < 2, \
        f"This test proves the bug: wrong entity yields {len(candidates_wrong)} candidates"


def test_t30_recent_symbols_path_bypasses_fallback():
    """
    T30: If recent_symbols correctly populated 贵州茅台, active_entities is set
    WITHOUT needing the fallback scan — no risk of current-query contamination.
    """
    # Simulate: recent_symbols has 贵州茅台 from Round 1's _write_memory_from_result
    ctx = MemoryContext(
        active_entities=[ResolvedEntity(type="stock", name="贵州茅台", code="600519", market="CN")],
        recent_messages=[
            {"role": "user",      "snippet": "贵州茅台最新财报表现如何？"},
            {"role": "assistant", "snippet": "贵州茅台2024年营收1459亿..."},
            {"role": "user",      "snippet": "那它和五粮液相比呢？"},
        ],
    )
    # Coreference should resolve correctly
    resolved, needs_clarification, _ = resolve_coreferences("那它和五粮液相比呢？", ctx)
    assert not needs_clarification, "Should resolve without clarification when entity known"
    candidates = _extract_compare_candidates(resolved, memory_context=ctx)
    assert len(candidates) >= 2


# ═════════════════════════════════════════════════════════════════════════════
# Extra: edge-case guards
# ═════════════════════════════════════════════════════════════════════════════

def test_no_injection_when_no_pronoun_and_only_one_name():
    """Only 1 stock name AND no pronoun → no injection, returns that 1 name."""
    ctx = _ctx_with_maotai()
    candidates = _extract_compare_candidates("请分析五粮液的基本面", memory_context=ctx)
    # No pronoun → should NOT inject 贵州茅台 from memory
    joined = " ".join(candidates)
    assert "600519" not in joined, "Should not inject entity without pronoun"
    assert "贵州茅台" not in joined, "Should not inject entity without pronoun"


def test_dedup_candidates():
    """Duplicate stock names/codes are deduplicated."""
    candidates = _extract_compare_candidates("对比600519和600519")
    # Should deduplicate
    assert candidates.count("600519") <= 1


def test_match_compare_xiangbi_and_separator():
    """'相比' with '和' separator → matches compare intent."""
    assert _match_compare("那它和五粮液相比呢？") is True


def test_match_compare_duibi():
    """'对比' directly → matches compare intent."""
    assert _match_compare("请对比贵州茅台和五粮液") is True
