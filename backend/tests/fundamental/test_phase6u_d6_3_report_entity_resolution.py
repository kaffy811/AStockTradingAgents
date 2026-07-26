from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.agents.chat_skills.base import SkillContext
from app.agents.chat_skills.base import SkillResult
from app.agents.chat_orchestrator import process_message
from app.agents.chat_skills.report_explanation_skill import ReportExplanationSkill
from app.services import security_entity_resolver as resolver_module
from app.services.security_entity_resolver import INDEX_VERSION, SecurityEntityResolver
from app.services.conversation_memory_service import MemoryContext, ResolvedEntity


SAMPLE_SECURITIES = [
    {"market": "CN", "symbol": "600519", "short_name": "贵州茅台", "full_name": "贵州茅台酒股份有限公司", "industry": "白酒"},
    {"market": "CN", "symbol": "000858", "short_name": "五粮液", "full_name": "宜宾五粮液股份有限公司", "industry": "白酒"},
    {"market": "CN", "symbol": "300750", "short_name": "宁德时代", "full_name": "宁德时代新能源科技股份有限公司", "industry": "电池"},
    {"market": "HK", "symbol": "00700", "short_name": "腾讯控股", "full_name": "腾讯控股有限公司", "english_name": "Tencent"},
    {"market": "US", "symbol": "MSFT", "short_name": "Microsoft", "full_name": "Microsoft Corporation", "aliases": ["微软"]},
]


@pytest.mark.asyncio
async def test_d6_3_continuous_chinese_report_query_resolves_cn_short_name():
    resolver = SecurityEntityResolver(sample_rows=SAMPLE_SECURITIES)
    result = await resolver.resolve(None, "贵州茅台最新财报表现如何？", market_hint="CN", min_confidence=0.72)
    assert result["index_version"] == INDEX_VERSION
    entity = result["entities"][0]
    assert entity.symbol == "600519"
    assert entity.ts_code == "600519.SH"
    assert entity.match_type in {"continuous_name_match", "exact_short_name"}


@pytest.mark.asyncio
async def test_d6_3_wuliangye_latest_annual_report_resolves():
    resolver = SecurityEntityResolver(sample_rows=SAMPLE_SECURITIES)
    result = await resolver.resolve(None, "五粮液最新年报", market_hint="CN", min_confidence=0.72)
    assert result["entities"][0].symbol == "000858"


@pytest.mark.asyncio
async def test_d6_3_generated_cn_short_names_embedded_in_sentence_resolve():
    rows = [
        {"market": "CN", "symbol": f"{idx:06d}", "short_name": f"样本股份{idx}", "full_name": f"样本股份{idx}有限公司"}
        for idx in range(100100, 100200)
    ]
    resolver = SecurityEntityResolver(sample_rows=rows)
    for row in rows:
        result = await resolver.resolve(None, f"请分析{row['short_name']}最新财报表现", market_hint="CN", min_confidence=0.72)
        assert result["entities"][0].symbol == row["symbol"]


@pytest.mark.asyncio
async def test_d6_3_hk_us_names_embedded_in_sentence_resolve():
    resolver = SecurityEntityResolver(sample_rows=SAMPLE_SECURITIES)
    hk = await resolver.resolve(None, "腾讯控股最新财报怎么样", market_hint="HK", min_confidence=0.72)
    us = await resolver.resolve(None, "微软最新年报如何", market_hint="US", min_confidence=0.72)
    assert hk["entities"][0].market == "HK"
    assert hk["entities"][0].symbol == "00700"
    assert us["entities"][0].market == "US"
    assert us["entities"][0].symbol == "MSFT"


@pytest.mark.asyncio
async def test_d6_3_empty_index_cache_is_rebuilt(monkeypatch):
    resolver = SecurityEntityResolver()

    async def _fake_get_swr(key, *, force_refresh=False):
        return [], "fresh", "memory"

    async def _fake_set_swr(*args, **kwargs):
        return None

    async def _fake_master_rows(db, market):
        return [resolver._normalize_row(SAMPLE_SECURITIES[0])]

    monkeypatch.setattr(resolver_module.company_v2_snapshot_cache_service, "get_swr", _fake_get_swr)
    monkeypatch.setattr(resolver_module.company_v2_snapshot_cache_service, "set_swr", _fake_set_swr)
    monkeypatch.setattr(resolver, "_load_master_rows", _fake_master_rows)
    rows = await resolver._load_index(SimpleNamespace(), "CN")
    assert rows
    assert rows[0]["symbol"] == "600519"


@pytest.mark.asyncio
async def test_d6_3_report_skill_uses_payload_primary_entity_without_report_id(monkeypatch):
    captured: dict = {}

    class _FakeAgent:
        async def chat(self, **kwargs):
            captured.update(kwargs)
            return {
                "answer": "贵州茅台财报回答",
                "status": "completed",
                "source_chunks": [{"text": "主要会计数据"}],
                "report_context": {"market": "CN", "symbol": kwargs["symbol"], "report_id": 2, "stock_name": "贵州茅台"},
                "confidence": "high",
            }

    monkeypatch.setattr("app.agents.chat_skills.report_explanation_skill.ReportChatCopilotAgent", _FakeAgent)
    context = SkillContext(
        db=None,
        user_id="u",
        session_id="s",
        metadata={
            "raw_query": "贵州茅台最新财报表现如何？",
            "effective_query": "贵州茅台最新财报表现如何？",
            "primary_entity": {
                "market": "CN",
                "symbol": "600519",
                "ts_code": "600519.SH",
                "short_name": "贵州茅台",
                "confidence": 0.99,
                "match_type": "exact_short_name",
            },
            "resolved_entities": [],
            "resolver_called": True,
            "resolver_result_count": 1,
        },
        memory_context=MemoryContext(active_entities=[ResolvedEntity(type="stock", name="损坏上下文", code="000001", market="CN")]),
    )
    result = await ReportExplanationSkill().run("贵州茅台最新财报表现如何？", context)
    assert result.data["status"] == "completed"
    assert captured["market"] == "CN"
    assert captured["symbol"] == "600519"
    assert captured["report_id"] is None


@pytest.mark.asyncio
async def test_d6_3_entity_not_resolved_has_precise_error_without_partial_prefix(monkeypatch):
    monkeypatch.setattr(resolver_module.security_entity_resolver, "_sample_rows", [])
    context = SkillContext(
        db=None,
        user_id="u",
        session_id="s",
        metadata={
            "raw_query": "不存在公司最新财报表现如何？",
            "effective_query": "不存在公司最新财报表现如何？",
            "resolver_called": True,
            "resolver_result_count": 0,
            "resolved_entities": [],
        },
    )
    result = await ReportExplanationSkill().run("不存在公司最新财报表现如何？", context)
    assert result.data["status"] == "failed"
    assert result.data["error_code"] == "ENTITY_NOT_RESOLVED"
    assert result.data["partial"] is False
    assert {event["name"] for event in result.tool_events} >= {"rag_retrieve", "rag_review"}
    assert "数据部分完整" not in result.answer


@pytest.mark.asyncio
async def test_d6_3_orchestrator_passes_primary_entity_to_skill_context(monkeypatch):
    monkeypatch.setattr(resolver_module.security_entity_resolver, "_sample_rows", SAMPLE_SECURITIES)

    async def _fake_memory_context(db, session_id, user_id, content):
        return MemoryContext(active_entities=[])

    captured: dict = {}

    async def _fake_run(message, context):
        captured["message"] = message
        captured["metadata"] = context.metadata
        return SkillResult(
            ok=True,
            skill_name="report_explanation_skill",
            answer="ok",
            data={"status": "completed", "source_chunks": [{"text": "x"}]},
        )

    monkeypatch.setattr("app.services.conversation_memory_service.build_memory_context", _fake_memory_context)
    monkeypatch.setattr("app.agents.chat_orchestrator._skill_registry.run", _fake_run)
    result = await process_message("贵州茅台最新财报表现如何？", None, "user-id")
    assert result.answer == "ok"
    assert captured["metadata"]["chat_entity_pipeline_version"] == "d6_4"
    assert captured["metadata"]["primary_entity"]["symbol"] == "600519"
    assert captured["metadata"]["resolved_entities"][0]["ts_code"] == "600519.SH"
