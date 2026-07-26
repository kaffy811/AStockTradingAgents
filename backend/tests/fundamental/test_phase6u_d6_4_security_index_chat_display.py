from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from app.agents.chat_skills.base import SkillContext
from app.agents.chat_skills.report_comparison_skill import _build_comparison_entities
from app.agents.chat_skills.report_explanation_skill import _sanitize_public_report_answer
from app.agents.financial_safety_postprocessor import sanitize_certainty_claims
from app.services import security_entity_resolver as resolver_module
from app.services.conversation_memory_service import MemoryContext, ResolvedEntity
from app.services.security_entity_resolver import (
    INDEX_VERSION,
    SecurityEntityResolver,
    get_security_index_metrics,
    reset_security_index_runtime_state,
)


SAMPLE_SECURITIES = [
    {"market": "CN", "symbol": "600519", "short_name": "贵州茅台", "full_name": "贵州茅台酒股份有限公司", "industry": "白酒", "source": "test_master"},
    {"market": "CN", "symbol": "000858", "short_name": "五粮液", "full_name": "宜宾五粮液股份有限公司", "industry": "白酒", "source": "test_master"},
    {"market": "CN", "symbol": "300750", "short_name": "宁德时代", "full_name": "宁德时代新能源科技股份有限公司", "industry": "电池", "source": "test_master"},
]


def _large_cn_rows(total: int = 1200) -> list[dict]:
    rows = [
        {"market": "CN", "symbol": f"{idx:06d}", "short_name": f"样本证券{idx}", "full_name": f"样本证券{idx}股份有限公司", "source": "test_master"}
        for idx in range(100000, 100000 + total)
    ]
    rows[0] = SAMPLE_SECURITIES[1]
    return rows


@pytest.mark.asyncio
async def test_d6_4_wuliangye_continuous_report_query_contract():
    resolver = SecurityEntityResolver(sample_rows=SAMPLE_SECURITIES)
    result = await resolver.resolve(None, "五粮液最新财报表现如何", market_hint="CN", min_confidence=0.72)
    entity = result["entities"][0]
    assert result["index_version"] == "v3_d6_4"
    assert entity.market == "CN"
    assert entity.symbol == "000858"
    assert entity.ts_code == "000858.SZ"
    assert entity.short_name == "五粮液"
    assert entity.confidence == 1.0
    assert entity.match_type == "continuous_name_match"
    assert entity.source == "test_master"


@pytest.mark.asyncio
async def test_d6_4_wuliangye_code_query_contract():
    resolver = SecurityEntityResolver(sample_rows=SAMPLE_SECURITIES)
    result = await resolver.resolve(None, "000858最新财报", market_hint="CN", min_confidence=0.72)
    assert result["entities"][0].symbol == "000858"
    assert result["entities"][0].match_type == "exact_code"


@pytest.mark.asyncio
async def test_d6_4_pronoun_and_explicit_entity_merge_for_comparison(monkeypatch):
    monkeypatch.setattr(resolver_module.security_entity_resolver, "_sample_rows", SAMPLE_SECURITIES)
    context = SkillContext(
        db=None,
        user_id="u",
        session_id="s",
        metadata={"raw_query": "那它和五粮液比呢", "effective_query": "那它和五粮液比呢"},
        memory_context=MemoryContext(active_entities=[ResolvedEntity(type="stock", name="贵州茅台", code="600519", market="CN")]),
    )
    entities, diagnostics = await _build_comparison_entities("那它和五粮液比呢", context)
    assert [(e["market"], e["symbol"], e["source"]) for e in entities[:2]] == [
        ("CN", "600519", "pronoun_context"),
        ("CN", "000858", "current_query_explicit"),
    ]
    assert diagnostics["comparison_parser_output"]["entities"][1]["symbol"] == "000858"


@pytest.mark.asyncio
async def test_d6_4_incomplete_current_version_cache_rebuilds(monkeypatch):
    resolver = SecurityEntityResolver()
    stale_rows = [
        resolver._normalize_row({"market": "CN", "symbol": f"{idx:06d}", "short_name": f"旧缓存{idx}"})
        for idx in range(20)
    ]
    fresh_rows = [resolver._normalize_row(row) for row in _large_cn_rows()]
    writes: list[dict] = []

    async def _fake_get_swr(key):
        return {
            "version": INDEX_VERSION,
            "market": "CN",
            "rows": stale_rows,
            "metadata": {
                "version": INDEX_VERSION,
                "market": "CN",
                "indexed_count": len(stale_rows),
                "checksum": resolver._index_checksum(stale_rows),
            },
        }, "fresh", "redis"

    async def _fake_set_swr(key, value, **kwargs):
        writes.append(value)

    async def _fake_master_rows(db, market):
        return fresh_rows

    monkeypatch.setattr(resolver_module.company_v2_snapshot_cache_service, "get_swr", _fake_get_swr)
    monkeypatch.setattr(resolver_module.company_v2_snapshot_cache_service, "set_swr", _fake_set_swr)
    monkeypatch.setattr(resolver, "_load_master_rows", _fake_master_rows)

    rows = await resolver._load_index(SimpleNamespace(), "CN")
    assert len(rows) == len(fresh_rows)
    assert any(row["symbol"] == "000858" for row in rows)
    assert writes and writes[0]["metadata"]["indexed_count"] == len(fresh_rows)


@pytest.mark.asyncio
async def test_d6_4_old_list_cache_is_ignored(monkeypatch):
    resolver = SecurityEntityResolver()
    fresh_rows = [resolver._normalize_row(row) for row in _large_cn_rows()]

    async def _fake_get_swr(key):
        return [{"market": "CN", "symbol": "000001", "short_name": "旧列表缓存"}], "fresh", "redis"

    async def _fake_set_swr(*args, **kwargs):
        return None

    async def _fake_master_rows(db, market):
        return fresh_rows

    monkeypatch.setattr(resolver_module.company_v2_snapshot_cache_service, "get_swr", _fake_get_swr)
    monkeypatch.setattr(resolver_module.company_v2_snapshot_cache_service, "set_swr", _fake_set_swr)
    monkeypatch.setattr(resolver, "_load_master_rows", _fake_master_rows)
    rows = await resolver._load_index(SimpleNamespace(), "CN")
    assert len(rows) == len(fresh_rows)


@pytest.mark.asyncio
async def test_e1_3_1_warm_resolver_snapshot_has_zero_full_db_scans(monkeypatch):
    reset_security_index_runtime_state()
    resolver = SecurityEntityResolver()
    fresh_rows = [resolver._normalize_row(row) for row in _large_cn_rows()]
    calls = {"load": 0}

    async def _fake_get_swr(key):
        return None, "miss", None

    async def _fake_set_swr(*args, **kwargs):
        return None

    async def _fake_master_rows(db, market):
        calls["load"] += 1
        return fresh_rows

    monkeypatch.setattr(resolver_module.company_v2_snapshot_cache_service, "get_swr", _fake_get_swr)
    monkeypatch.setattr(resolver_module.company_v2_snapshot_cache_service, "set_swr", _fake_set_swr)
    monkeypatch.setattr(resolver, "_load_master_rows", _fake_master_rows)

    db = SimpleNamespace(info={})
    await resolver._load_index(db, "CN")
    metrics_after_cold = get_security_index_metrics()
    await resolver._load_index(db, "CN")
    await SecurityEntityResolver()._load_index(SimpleNamespace(info={}), "CN")
    metrics_after_warm = get_security_index_metrics()

    assert calls["load"] == 1
    assert metrics_after_cold["security_index_db_full_scan"] == 0
    assert metrics_after_warm["security_index_db_full_scan"] == 0
    assert metrics_after_warm["security_index_cache_hit"] >= 2


@pytest.mark.asyncio
async def test_e1_3_1_concurrent_rebuild_uses_singleflight(monkeypatch):
    reset_security_index_runtime_state()
    resolver = SecurityEntityResolver()
    fresh_rows = [resolver._normalize_row(row) for row in _large_cn_rows()]
    calls = {"load": 0}

    async def _fake_get_swr(key):
        return None, "miss", None

    async def _fake_set_swr(*args, **kwargs):
        return None

    async def _fake_master_rows(db, market):
        calls["load"] += 1
        return fresh_rows

    monkeypatch.setattr(resolver_module.company_v2_snapshot_cache_service, "get_swr", _fake_get_swr)
    monkeypatch.setattr(resolver_module.company_v2_snapshot_cache_service, "set_swr", _fake_set_swr)
    monkeypatch.setattr(resolver, "_load_master_rows", _fake_master_rows)

    await asyncio.gather(
        resolver._load_index(SimpleNamespace(info={}), "CN"),
        resolver._load_index(SimpleNamespace(info={}), "CN"),
        resolver._load_index(SimpleNamespace(info={}), "CN"),
    )
    assert calls["load"] == 1


def test_d6_4_report_answer_hides_internal_sources_and_softens_causal_claim():
    answer = (
        "source_chunks[4] chunk 1 review_audit\n"
        "现金流大幅下降并非主营业务恶化。\n"
        "_仅供研究参考，不构成投资建议。_"
    )
    clean = _sanitize_public_report_answer(
        answer,
        stock_name="测试公司",
        result={"source_chunks": [{"chunk_id": "x"}], "report_context": {"report_year": 2025}},
    )
    assert "source_chunks" not in clean
    assert "chunk 1" not in clean
    assert "review_audit" not in clean
    assert "不构成投资建议" not in clean
    assert "仅凭当前资料不能直接判断主营业务收款能力是否恶化" in clean
    assert "数据来源：测试公司2025年年度报告" in clean


def test_d6_4_safety_postprocessor_does_not_corrupt_business_pressure():
    text = "表明2025年面临一定业绩压力。"
    assert sanitize_certainty_claims(text) == text
    assert "（走势存在不确定性）业绩压力" not in sanitize_certainty_claims(text)
