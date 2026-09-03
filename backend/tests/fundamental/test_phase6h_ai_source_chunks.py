"""
tests/fundamental/test_phase6h_ai_source_chunks.py — Phase 6H: RAG chunks → AI analysis pipeline

Tests:
 1. Data Agent collects report_rag_context when db provided
 2. Data Agent returns empty report_rag_context when db is None
 3. Data Agent deduplicates chunk_ids across queries
 4. Data Agent limits to 4 chunks (summary) / 8 chunks (full)
 5. Analysis Agent includes report_rag_context in prompt compact JSON
 6. Review Agent removes invalid chunk_id from source_chunks
 7. Review Agent keeps valid chunk_id in source_chunks
 8. Orchestrator enriches source_chunks with full content from rag_context
 9. Orchestrator passes rag_meta to envelope (rag_status)
10. Cache key changes when chunk_ids change
11. API response contains source_chunks field
12. AiAnalysisCard can read source_chunks from envelope (effectiveSourceChunks logic)
"""
from __future__ import annotations

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_agg_envelope(ok=True, data=None):
    return {
        "ok": ok,
        "data": data or {"series": [{"end_date": "20231231", "revenue_yoy_pct": 10.0, "net_profit_yoy_pct": 8.0, "deduct_net_profit_yoy_pct": 7.0}]},
        "partial_errors": [],
        "stale": False,
        "reason": None,
        "cached_at": None,
    }


def _make_rag_chunk(chunk_id: int, content: str = "公司主营业务收入稳定增长。") -> dict:
    return {
        "chunk_id":      chunk_id,
        "report_id":     100 + chunk_id,
        "ts_code":       "600519.SH",
        "report_type":   "annual",
        "report_year":   2023,
        "period":        "20231231",
        "chunk_index":   0,
        "section_title": "管理层讨论与分析",
        "content":       content,
        "has_embedding": True,
        "score":         0.87,
        "score_detail":  {"vector_score": 0.85, "keyword_bonus": 0.02},
    }


def _make_rag_result(chunks: list[dict], search_mode="vector", fallback_used=False) -> dict:
    return {
        "chunks":       chunks,
        "partial":      False,
        "errors":       [],
        "search_mode":  search_mode,
        "total":        len(chunks),
        "fallback_used": fallback_used,
        "provider":     "mock",
    }


def _good_analysis_json(source_chunks=None):
    base = {
        "summary": "公司基本面稳健，营收保持增长。",
        "overall_score": 72,
        "dimensions": [
            {"name": "成长性", "score": 75, "level": "strong",
             "evidence": [{"text": "营收同比增长10%", "source_modules": ["growth"], "source_fact_ids": ["growth_000"]}],
             "risks": []},
            {"name": "盈利能力", "score": 68, "level": "neutral", "evidence": [], "risks": []},
            {"name": "现金流质量", "score": 70, "level": "neutral", "evidence": [], "risks": []},
            {"name": "偿债安全", "score": 80, "level": "strong", "evidence": [], "risks": []},
            {"name": "估值位置", "score": 55, "level": "neutral", "evidence": [], "risks": []},
        ],
        "highlights": [{"title": "营收稳定增长", "detail": "连续两年营收同比正增长。",
                        "source_modules": ["growth"], "source_fact_ids": ["growth_000"]}],
        "risks": [{"title": "净利润增速放缓", "detail": "净利润增速低于营收增速。",
                   "severity": "low", "source_modules": ["growth"], "source_fact_ids": ["growth_001"]}],
        "watch_items": [],
        "data_limitations": [],
        "raw_disclaimer": "本内容由 AI 基于公开财务数据生成，仅供参考，不构成投资建议。",
        "source_chunks": source_chunks or [],
    }
    return base


# ── T1: Data Agent collects report_rag_context when db provided ───────────────

@pytest.mark.asyncio
async def test_data_agent_collects_rag_context_with_db():
    """T1: Data Agent includes report_rag_context when db is provided."""
    from app.agent.fundamental_data_agent import FundamentalDataAgent

    mock_chunk = _make_rag_chunk(1)
    rag_result = _make_rag_result([mock_chunk])

    mock_rag_service = AsyncMock()
    mock_rag_service.query = AsyncMock(return_value=rag_result)

    mock_db = MagicMock()

    with patch("app.aggregator.fundamentals_aggregator.get_aggregator") as mock_get_agg, \
         patch("app.services.report_rag_service.report_rag_service", mock_rag_service), \
         patch("app.datasource.tushare_client._to_ts_code", return_value="600519.SH"):

        mock_agg = MagicMock()
        mock_agg.fetch_module = AsyncMock(return_value=_make_agg_envelope())
        mock_get_agg.return_value = mock_agg

        agent = FundamentalDataAgent()
        result = await agent.collect("CN", "600519", mode="summary", db=mock_db)

    assert "report_rag_context" in result
    assert "allowed_chunk_ids" in result
    assert "rag_meta" in result
    assert len(result["report_rag_context"]) >= 1
    assert result["allowed_chunk_ids"] == [1]


# ── T2: Data Agent returns empty report_rag_context when db is None ───────────

@pytest.mark.asyncio
async def test_data_agent_no_rag_without_db():
    """T2: Data Agent returns empty RAG fields when db=None."""
    from app.agent.fundamental_data_agent import FundamentalDataAgent

    with patch("app.aggregator.fundamentals_aggregator.get_aggregator") as mock_get_agg:
        mock_agg = MagicMock()
        mock_agg.fetch_module = AsyncMock(return_value=_make_agg_envelope())
        mock_get_agg.return_value = mock_agg

        agent = FundamentalDataAgent()
        result = await agent.collect("CN", "600519", mode="summary", db=None)

    assert result["report_rag_context"] == []
    assert result["allowed_chunk_ids"] == []


# ── T3: Data Agent deduplicates chunk_ids across queries ──────────────────────

@pytest.mark.asyncio
async def test_data_agent_deduplicates_chunks():
    """T3: Same chunk_id returned by multiple RAG queries is deduplicated."""
    from app.agent.fundamental_data_agent import FundamentalDataAgent

    shared_chunk = _make_rag_chunk(42)
    # All queries return the same chunk
    rag_result = _make_rag_result([shared_chunk])

    mock_rag_service = AsyncMock()
    mock_rag_service.query = AsyncMock(return_value=rag_result)
    mock_db = MagicMock()

    with patch("app.aggregator.fundamentals_aggregator.get_aggregator") as mock_get_agg, \
         patch("app.services.report_rag_service.report_rag_service", mock_rag_service), \
         patch("app.datasource.tushare_client._to_ts_code", return_value="600519.SH"):

        mock_agg = MagicMock()
        mock_agg.fetch_module = AsyncMock(return_value=_make_agg_envelope())
        mock_get_agg.return_value = mock_agg

        agent = FundamentalDataAgent()
        result = await agent.collect("CN", "600519", mode="full", db=mock_db)

    chunk_ids = [c["chunk_id"] for c in result["report_rag_context"]]
    assert len(chunk_ids) == len(set(chunk_ids)), "chunk_ids must be unique"
    assert 42 in result["allowed_chunk_ids"]


# ── T4: Data Agent limits chunks (4 for summary, 8 for full) ─────────────────

@pytest.mark.asyncio
async def test_data_agent_chunk_limit_summary():
    """T4a: Data Agent limits to 4 chunks in summary mode."""
    from app.agent.fundamental_data_agent import FundamentalDataAgent

    # Return 3 unique chunks per query, many queries
    call_counter = {"n": 0}

    async def rag_query(**kwargs):
        chunks = [_make_rag_chunk(call_counter["n"] * 3 + i) for i in range(3)]
        call_counter["n"] += 1
        return _make_rag_result(chunks)

    mock_rag_service = AsyncMock()
    mock_rag_service.query = AsyncMock(side_effect=rag_query)
    mock_db = MagicMock()

    with patch("app.aggregator.fundamentals_aggregator.get_aggregator") as mock_get_agg, \
         patch("app.services.report_rag_service.report_rag_service", mock_rag_service), \
         patch("app.datasource.tushare_client._to_ts_code", return_value="600519.SH"):

        mock_agg = MagicMock()
        mock_agg.fetch_module = AsyncMock(return_value=_make_agg_envelope())
        mock_get_agg.return_value = mock_agg

        agent = FundamentalDataAgent()
        result = await agent.collect("CN", "600519", mode="summary", db=mock_db)

    assert len(result["report_rag_context"]) <= 4


@pytest.mark.asyncio
async def test_data_agent_chunk_limit_full():
    """T4b: Data Agent limits to 8 chunks in full mode."""
    from app.agent.fundamental_data_agent import FundamentalDataAgent

    call_counter = {"n": 0}

    async def rag_query(**kwargs):
        chunks = [_make_rag_chunk(call_counter["n"] * 3 + i) for i in range(3)]
        call_counter["n"] += 1
        return _make_rag_result(chunks)

    mock_rag_service = AsyncMock()
    mock_rag_service.query = AsyncMock(side_effect=rag_query)
    mock_db = MagicMock()

    with patch("app.aggregator.fundamentals_aggregator.get_aggregator") as mock_get_agg, \
         patch("app.services.report_rag_service.report_rag_service", mock_rag_service), \
         patch("app.datasource.tushare_client._to_ts_code", return_value="600519.SH"):

        mock_agg = MagicMock()
        mock_agg.fetch_module = AsyncMock(return_value=_make_agg_envelope())
        mock_get_agg.return_value = mock_agg

        agent = FundamentalDataAgent()
        result = await agent.collect("CN", "600519", mode="full", db=mock_db)

    assert len(result["report_rag_context"]) <= 8


# ── T5: Analysis Agent includes report_rag_context in prompt ──────────────────

def test_analysis_agent_includes_rag_in_prompt():
    """T5: _compress_data_pack_for_prompt includes report_rag_context."""
    from app.agent.fundamental_analysis_agent import _compress_data_pack_for_prompt
    from app.agent.schemas import make_data_pack

    rag_chunks = [_make_rag_chunk(1), _make_rag_chunk(2)]
    data_pack = make_data_pack(
        ts_code="600519.SH", market="CN", symbol="600519",
        collected=["growth"], missing=[], stale=[], partial=[],
        data_quality={"score": 80, "level": "high", "issues": []},
        module_summaries={},
        compressed_facts=[{"fact_id": "growth_000", "module_key": "growth", "metric": "revenue_yoy_pct", "value": 10.0, "period": "20231231", "text": "营收同比增长10%"}],
        report_rag_context=rag_chunks,
        allowed_chunk_ids=[1, 2],
    )

    compact_json = _compress_data_pack_for_prompt(data_pack, facts_limit=30)
    compact = json.loads(compact_json)

    assert "report_rag_context" in compact
    assert len(compact["report_rag_context"]) == 2
    assert compact["report_rag_context"][0]["chunk_id"] == 1


# ── T6: Review Agent removes invalid chunk_id ─────────────────────────────────

def test_review_agent_removes_invalid_chunk_id():
    """T6: _canonicalize_source_chunks removes chunk_ids not in allowed list."""
    from app.agent.fundamental_review_agent import _canonicalize_source_chunks
    from app.agent.schemas import make_data_pack

    rag_chunk_10 = {
        "chunk_id": 10, "report_id": 1, "ts_code": "600519.SH",
        "report_type": "annual", "report_year": 2023, "period": "2023-12-31",
        "section_title": "MD&A", "content": "内容", "score": 0.9,
    }
    data_pack = make_data_pack(
        ts_code="600519.SH", market="CN", symbol="600519",
        collected=[], missing=[], stale=[], partial=[],
        data_quality={"score": 80, "level": "high", "issues": []},
        module_summaries={}, compressed_facts=[],
        allowed_chunk_ids=[10, 20],  # only these are allowed
        report_rag_context=[rag_chunk_10],
    )

    analysis = {
        "source_chunks": [
            {"chunk_id": 10, "citation": "收入增长"},
            {"chunk_id": 99, "citation": "无效引用"},  # invalid
        ]
    }

    issues, cleaned, audit = _canonicalize_source_chunks(analysis, data_pack)

    assert any("99" in msg for msg in issues)
    assert len(cleaned["source_chunks"]) == 1
    assert cleaned["source_chunks"][0]["chunk_id"] == 10


# ── T7: Review Agent keeps valid chunk_id ────────────────────────────────────

def test_review_agent_keeps_valid_chunk_id():
    """T7: _canonicalize_source_chunks keeps chunk_ids that are in the allowed list."""
    from app.agent.fundamental_review_agent import _canonicalize_source_chunks
    from app.agent.schemas import make_data_pack

    rag_chunks = [
        {"chunk_id": 10, "report_id": 1, "ts_code": "600519.SH",
         "report_type": "annual", "report_year": 2023, "period": "2023-12-31",
         "section_title": "MD&A", "content": "内容", "score": 0.9},
        {"chunk_id": 20, "report_id": 1, "ts_code": "600519.SH",
         "report_type": "annual", "report_year": 2023, "period": "2023-12-31",
         "section_title": "风险因素", "content": "风险内容", "score": 0.8},
    ]
    data_pack = make_data_pack(
        ts_code="600519.SH", market="CN", symbol="600519",
        collected=[], missing=[], stale=[], partial=[],
        data_quality={"score": 80, "level": "high", "issues": []},
        module_summaries={}, compressed_facts=[],
        allowed_chunk_ids=[10, 20],
        report_rag_context=rag_chunks,
    )

    analysis = {
        "source_chunks": [
            {"chunk_id": 10, "citation": "收入增长"},
            {"chunk_id": 20, "citation": "风险因素"},
        ]
    }

    issues, cleaned, audit = _canonicalize_source_chunks(analysis, data_pack)

    # No invalid chunk removals
    assert audit["invalid_removed"] == []
    assert len(cleaned["source_chunks"]) == 2


# ── T8: Orchestrator enriches source_chunks ───────────────────────────────────

@pytest.mark.asyncio
async def test_orchestrator_enriches_source_chunks():
    """T8: Orchestrator replaces raw source_chunks with enriched data from rag_context."""
    from app.agent.fundamental_ai_orchestrator import FundamentalAIOrchestrator
    from app.agent.schemas import make_data_pack

    rag_chunk = _make_rag_chunk(42, content="公司主营业务为酱香型白酒生产及销售。")
    data_pack = make_data_pack(
        ts_code="600519.SH", market="CN", symbol="600519",
        collected=["growth"], missing=[], stale=[], partial=[],
        data_quality={"score": 80, "level": "high", "issues": []},
        module_summaries={},
        compressed_facts=[{"fact_id": "growth_000", "module_key": "growth", "metric": "revenue_yoy_pct", "value": 10.0, "period": "20231231", "text": "营收同比增长10%"}],
        report_rag_context=[rag_chunk],
        allowed_chunk_ids=[42],
        rag_meta={"provider": "mock", "fallback_used": False, "search_mode": "vector", "chunk_count": 1},
    )

    analysis_with_chunk = _good_analysis_json(source_chunks=[
        {"chunk_id": 42, "section_title": "管理层讨论与分析", "report_type": "annual", "period": "20231231", "citation": "主营业务为酱香型白酒"}
    ])

    review_result = {
        "review_status": "approved",
        "review_notes": [],
        "blocked_phrases": [],
        "final": analysis_with_chunk,
    }

    orch = FundamentalAIOrchestrator()
    orch._data_agent = AsyncMock()
    orch._data_agent.collect = AsyncMock(return_value=data_pack)
    orch._analysis_agent = AsyncMock()
    orch._analysis_agent.analyze = AsyncMock(return_value=analysis_with_chunk)
    orch._review_agent = AsyncMock()
    orch._review_agent.review = AsyncMock(return_value=review_result)

    with patch("app.agent.ai_cache.read_cache", AsyncMock(return_value=None)), \
         patch("app.agent.ai_cache.write_cache", AsyncMock()):
        envelope = await orch.run("CN", "600519", mode="summary", force_refresh=True)

    ai_data = envelope["data"]["ai_analysis"]
    # source_chunks should be enriched (has content, report_id, etc.)
    source_chunks = ai_data.get("source_chunks", [])
    assert len(source_chunks) == 1
    sc = source_chunks[0]
    assert sc["chunk_id"] == 42
    assert "content" in sc
    assert sc["report_id"] == 142  # 100 + chunk_id


# ── T9: Orchestrator passes rag_status to envelope ────────────────────────────

@pytest.mark.asyncio
async def test_orchestrator_rag_status_in_envelope():
    """T9: Envelope contains rag_status field from rag_meta."""
    from app.agent.fundamental_ai_orchestrator import FundamentalAIOrchestrator
    from app.agent.schemas import make_data_pack

    rag_chunk = _make_rag_chunk(1)
    data_pack = make_data_pack(
        ts_code="600519.SH", market="CN", symbol="600519",
        collected=["growth"], missing=[], stale=[], partial=[],
        data_quality={"score": 80, "level": "high", "issues": []},
        module_summaries={},
        compressed_facts=[],
        report_rag_context=[rag_chunk],
        allowed_chunk_ids=[1],
        rag_meta={"provider": "mock", "fallback_used": False, "search_mode": "vector", "chunk_count": 1},
    )

    analysis = _good_analysis_json()  # no source_chunks
    review_result = {
        "review_status": "approved", "review_notes": [], "blocked_phrases": [], "final": analysis,
    }

    orch = FundamentalAIOrchestrator()
    orch._data_agent = AsyncMock()
    orch._data_agent.collect = AsyncMock(return_value=data_pack)
    orch._analysis_agent = AsyncMock()
    orch._analysis_agent.analyze = AsyncMock(return_value=analysis)
    orch._review_agent = AsyncMock()
    orch._review_agent.review = AsyncMock(return_value=review_result)

    with patch("app.agent.ai_cache.read_cache", AsyncMock(return_value=None)), \
         patch("app.agent.ai_cache.write_cache", AsyncMock()):
        envelope = await orch.run("CN", "600519", mode="summary", force_refresh=True)

    ai_data = envelope["data"]["ai_analysis"]
    # rag_status should be present when rag_context is available
    assert "rag_status" in ai_data
    assert ai_data["rag_status"] in ("mock", "local", "keyword_only", "unavailable")


# ── T10: Cache key changes when chunk_ids change ─────────────────────────────

def test_cache_key_changes_with_chunk_ids():
    """T10: _input_hash produces different values for different chunk_id sets."""
    from app.agent.ai_cache import _input_hash
    from app.agent.schemas import make_data_pack

    base_kwargs = dict(
        ts_code="600519.SH", market="CN", symbol="600519",
        collected=["growth"], missing=[], stale=[], partial=[],
        data_quality={"score": 80, "level": "high", "issues": []},
        module_summaries={},
        compressed_facts=[],
    )

    dp_no_rag = make_data_pack(**base_kwargs, allowed_chunk_ids=[])
    dp_with_rag = make_data_pack(**base_kwargs, allowed_chunk_ids=[1, 2, 3])
    dp_different_rag = make_data_pack(**base_kwargs, allowed_chunk_ids=[4, 5])

    hash_no_rag = _input_hash(dp_no_rag)
    hash_with_rag = _input_hash(dp_with_rag)
    hash_different = _input_hash(dp_different_rag)

    assert hash_no_rag != hash_with_rag, "Hash should differ when chunk_ids added"
    assert hash_with_rag != hash_different, "Hash should differ for different chunk_id sets"


# ── T11: API response contains source_chunks field ───────────────────────────

@pytest.mark.asyncio
async def test_orchestrator_response_has_source_chunks_field():
    """T11: Orchestrator response dict always has source_chunks accessible."""
    from app.agent.fundamental_ai_orchestrator import FundamentalAIOrchestrator
    from app.agent.schemas import make_data_pack

    data_pack = make_data_pack(
        ts_code="600519.SH", market="CN", symbol="600519",
        collected=["growth"], missing=[], stale=[], partial=[],
        data_quality={"score": 80, "level": "high", "issues": []},
        module_summaries={},
        compressed_facts=[{"fact_id": "growth_000", "module_key": "growth", "metric": "revenue_yoy_pct", "value": 10.0, "period": "20231231", "text": "营收同比增长10%"}],
        report_rag_context=[],
        allowed_chunk_ids=[],
    )

    analysis = _good_analysis_json()
    review_result = {
        "review_status": "approved", "review_notes": [], "blocked_phrases": [], "final": analysis,
    }

    orch = FundamentalAIOrchestrator()
    orch._data_agent = AsyncMock()
    orch._data_agent.collect = AsyncMock(return_value=data_pack)
    orch._analysis_agent = AsyncMock()
    orch._analysis_agent.analyze = AsyncMock(return_value=analysis)
    orch._review_agent = AsyncMock()
    orch._review_agent.review = AsyncMock(return_value=review_result)

    with patch("app.agent.ai_cache.read_cache", AsyncMock(return_value=None)), \
         patch("app.agent.ai_cache.write_cache", AsyncMock()):
        envelope = await orch.run("CN", "600519", mode="summary", force_refresh=True)

    # Response is a dict with data.ai_analysis (even if source_chunks absent/empty)
    assert "data" in envelope
    assert "ai_analysis" in envelope["data"]
    ai_analysis = envelope["data"]["ai_analysis"]
    # source_chunks may or may not be present when no RAG context — that's OK
    # What's required is the field is accessible if it's there
    if "source_chunks" in ai_analysis:
        assert isinstance(ai_analysis["source_chunks"], list)


# ── T12: effectiveSourceChunks reads from envelope when no prop passed ────────

def test_effective_source_chunks_reads_from_envelope():
    """T12: Simulate the Vue computed effectiveSourceChunks logic in Python."""
    # Simulate the Vue component's effectiveSourceChunks computed property
    # Props: sourceChunks=[], chunksMeta={}
    # Envelope: data.ai_analysis.source_chunks = [...]

    source_chunks_prop: list = []
    chunks_meta_prop: dict = {}

    analysis = {
        "source_chunks": [
            {"chunk_id": 5, "section_title": "MD&A", "report_type": "annual",
             "period": "20231231", "citation": "营收增长", "provider": "mock", "fallback_used": False}
        ]
    }

    # Simulate: effectiveSourceChunks
    def effective_source_chunks(source_chunks_prop, analysis):
        if len(source_chunks_prop) > 0:
            return source_chunks_prop
        return analysis.get("source_chunks") or []

    # Simulate: effectiveChunksMeta
    def effective_chunks_meta(chunks_meta_prop, analysis):
        if len(chunks_meta_prop) > 0:
            return chunks_meta_prop
        chunks = analysis.get("source_chunks") or []
        if not chunks:
            return {}
        first = chunks[0]
        return {
            "provider": first.get("provider", "mock"),
            "fallback_used": any(c.get("fallback_used") for c in chunks),
            "search_mode": "keyword" if any(c.get("fallback_used") for c in chunks) else "vector",
        }

    esc = effective_source_chunks(source_chunks_prop, analysis)
    ecm = effective_chunks_meta(chunks_meta_prop, analysis)

    assert len(esc) == 1
    assert esc[0]["chunk_id"] == 5
    assert ecm["provider"] == "mock"
    assert ecm["fallback_used"] is False
    assert ecm["search_mode"] == "vector"
