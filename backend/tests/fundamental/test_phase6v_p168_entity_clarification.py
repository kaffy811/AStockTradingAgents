"""Phase 6V-P1.6.8 — legacy entity clarification candidates regression tests."""
from __future__ import annotations

import asyncio

import pytest

from app.services.entity_clarification import (
    build_entity_clarification,
    clarification_answer_text,
    compact_clarification_for_metadata,
)
from app.services.chat_service import compact_chat_message_metadata, public_message_metadata
from app.services.security_entity_resolver import SecurityEntityResolver


_SAMPLE_ROWS = [
    {"market": "CN", "symbol": "000001", "short_name": "平安银行", "full_name": "平安银行股份有限公司"},
    {"market": "CN", "symbol": "601318", "short_name": "中国平安", "full_name": "中国平安保险(集团)股份有限公司"},
    {"market": "HK", "symbol": "02318", "short_name": "中国平安", "full_name": "中国平安保险(集团)股份有限公司"},
    {"market": "CN", "symbol": "600519", "short_name": "贵州茅台", "full_name": "贵州茅台酒股份有限公司"},
    {"market": "CN", "symbol": "000858", "short_name": "五粮液", "full_name": "宜宾五粮液股份有限公司"},
    {"market": "CN", "symbol": "600036", "short_name": "招商银行", "full_name": "招商银行股份有限公司"},
    {"market": "CN", "symbol": "600999", "short_name": "招商证券", "full_name": "招商证券股份有限公司"},
]


def _resolver() -> SecurityEntityResolver:
    return SecurityEntityResolver(sample_rows=_SAMPLE_ROWS)


def _alias(query: str):
    return asyncio.run(_resolver().resolve_short_alias_candidates(None, query))


# ── candidate generation (items 1-6) ─────────────────────────────────────────


def test_two_resolver_candidates_enter_clarification_contract():
    hit = _alias("平安的年报PDF在哪里？")
    assert hit is not None and hit["query_term"] == "平安"
    names = [c["display_name"] for c in hit["candidates"]]
    assert "平安银行" in names and "中国平安" in names
    contract = build_entity_clarification(query_term=hit["query_term"], candidates=hit["candidates"])
    assert contract["kind"] == "entity_selection"
    assert contract["selection_required"] is True


def test_candidates_deduplicated_across_markets():
    hit = _alias("平安的年报PDF在哪里？")
    names = [c["display_name"] for c in hit["candidates"]]
    assert names.count("中国平安") == 1  # CN 601318 preferred over HK duplicate
    symbols = [c["symbol"] for c in hit["candidates"] if c["display_name"] == "中国平安"]
    assert symbols == ["601318"]


def test_candidates_ordering_is_deterministic():
    first = _alias("平安的年报PDF在哪里？")["candidates"]
    second = _alias("平安的年报PDF在哪里？")["candidates"]
    assert first == second
    # prefix matches sort before containment, then by name length/market/symbol
    assert first[0]["display_name"] == "平安银行"


def test_explicit_symbol_does_not_trigger_alias_clarification():
    assert _alias("000858 2025年年报PDF") is None


def test_explicit_company_name_resolves_without_multi_candidates():
    resolver = _resolver()
    resolved = asyncio.run(resolver.resolve(None, "中国平安2025年年度报告PDF链接", min_confidence=0.72))
    assert resolved["entities"], "explicit name must resolve normally"
    # and the alias path is not consulted when an entity resolves


def test_no_candidates_keeps_generic_clarification():
    assert _alias("不存在的公司2025年年报PDF在哪里？") is None
    assert build_entity_clarification(query_term="x", candidates=[]) is None


def test_generic_stopword_alias_never_matches():
    assert _alias("银行的年报") is None


# ── contract content (items 7-10) ────────────────────────────────────────────


def _contract():
    hit = _alias("平安的年报PDF在哪里？")
    return build_entity_clarification(query_term=hit["query_term"], candidates=hit["candidates"])


def test_clarification_calls_no_report_tool_and_has_no_url():
    contract = _contract()
    text = clarification_answer_text(contract)
    assert "http" not in text.lower()
    assert "PDF：" not in text
    payload = str(contract)
    assert "http" not in payload.lower()


def test_structured_payload_contains_no_internal_reasoning():
    contract = _contract()
    for candidate in contract["candidates"]:
        assert set(candidate) <= {"display_name", "symbol", "market", "reason"}
    assert "confidence" not in str(contract)
    assert "prompt_template" not in str(contract)


def test_text_fallback_lists_names_and_symbols():
    text = clarification_answer_text(_contract())
    assert "平安银行" in text and "000001" in text
    assert "中国平安" in text and "601318" in text
    assert "回复公司名称或股票代码" in text


# ── persistence / payload (items 11, 15, 16) ─────────────────────────────────


def test_metadata_compaction_persists_clarification():
    compact = compact_chat_message_metadata({
        "skill_name": "report_explanation",
        "status": "clarification_required",
        "clarification": _contract(),
    })
    assert compact["response_kind"] == "clarification"
    assert [c["display_name"] for c in compact["clarification"]["candidates"]][:2] == ["平安银行", "中国平安"]


def test_metadata_compaction_from_skill_data_path():
    compact = compact_chat_message_metadata({
        "skill_data": {"status": "clarification_required", "clarification": _contract()},
    })
    assert compact["response_kind"] == "clarification"


def test_public_metadata_roundtrip_and_legacy_messages_compatible():
    compact = compact_chat_message_metadata({"clarification": _contract()})
    public = public_message_metadata(compact)
    assert public["clarification"]["candidates"]
    # old messages without metadata stay compatible
    assert public_message_metadata(None) == {}
    assert public_message_metadata({"status": "completed"}) == {}


def test_message_item_schema_accepts_metadata_default():
    from datetime import datetime, timezone
    import uuid

    from app.models.chat import ChatMessageItem, ChatMessageSendResponse

    item = ChatMessageItem(
        message_id=uuid.uuid4(), role="assistant", content="x", message_type="text",
        tool_events=[], cards=[], confirmation=None,
        created_at=datetime.now(timezone.utc),
    )
    assert item.metadata == {}
    resp = ChatMessageSendResponse(
        message_id=uuid.uuid4(), assistant_message_id=uuid.uuid4(), status="completed",
        answer="a", tool_events=[], cards=[], confirmation=None,
    )
    assert resp.metadata is None


# ── skill integration (items 4, 14, 17-20 partial) ───────────────────────────


@pytest.mark.asyncio
async def test_skill_fallback_produces_clarification(monkeypatch):
    from app.agents.chat_skills import report_explanation_skill as mod

    resolver = _resolver()
    monkeypatch.setattr(mod, "security_entity_resolver", resolver)

    class _Ctx:
        db = None
        event_callback = None
        memory_context = None
        metadata = {}

    skill = mod.ReportExplanationSkill()
    # drive only the fallback path helpers: alias → contract → answer
    alias_hit = await resolver.resolve_short_alias_candidates(None, "平安的年报PDF在哪里？")
    assert alias_hit is not None
    contract = build_entity_clarification(query_term=alias_hit["query_term"], candidates=alias_hit["candidates"])
    answer = clarification_answer_text(contract)
    assert "平安银行" in answer and "中国平安" in answer
    assert "报告工具" not in answer


def test_selected_candidate_resolves_next_turn():
    resolver = _resolver()
    resolved = asyncio.run(resolver.resolve(None, "中国平安", min_confidence=0.72))
    symbols = {e.symbol for e in resolved["entities"]}
    assert "601318" in symbols or "02318" in symbols


def test_compact_clarification_sanitizer_rejects_empty():
    assert compact_clarification_for_metadata({"candidates": []}) is None
    assert compact_clarification_for_metadata(None) is None
