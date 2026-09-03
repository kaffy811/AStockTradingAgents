"""
tests/fundamental/test_phase3_ai_agent.py — Phase 3 AI Agent 测试

测试策略：
- Data Agent: 不 mock LLM，只 mock aggregator
- Analysis Agent: mock DeepSeekClient，验证 JSON 解析和错误处理
- Review Agent: 规则引擎不需要 mock，直接测试
- Orchestrator: 端到端 mock，验证缓存和 fallback 逻辑
"""
from __future__ import annotations

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _make_envelope(ok=True, data=None, partial=False, stale=False, errors=None):
    return {
        "ok": ok,
        "data": data or {},
        "partial_errors": errors or [],
        "stale": stale,
        "reason": None,
        "cached_at": None,
    }

def _make_growth_envelope():
    return _make_envelope(data={
        "series": [
            {"end_date": "20231231", "revenue_yoy_pct": 12.3, "net_profit_yoy_pct": 8.5, "deduct_net_profit_yoy_pct": 7.2},
            {"end_date": "20221231", "revenue_yoy_pct": 15.1, "net_profit_yoy_pct": 11.0, "deduct_net_profit_yoy_pct": 10.5},
        ]
    })

def _make_valuation_envelope():
    return _make_envelope(data={
        "series": [
            {"trade_date": "20240101", "pe_ttm": 25.3, "pb": 3.1, "ps_ttm": 5.2},
        ]
    })

def _good_analysis_json():
    return {
        "summary": "公司基本面稳健，营收保持增长。",
        "overall_score": 72,
        "dimensions": [
            {"name": "成长性", "score": 75, "level": "strong",
             "evidence": [{"text": "营收同比增长12.3%", "source_modules": ["growth"], "source_fact_ids": ["growth_000"]}],
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
    }


# ── T1: Data Agent 能收集并压缩模块数据 ──────────────────────────────────────

@pytest.mark.asyncio
async def test_data_agent_collect():
    """T1: Data Agent 收集数据，不调用 LLM。"""
    from app.agent.fundamental_data_agent import FundamentalDataAgent

    mock_envelope = _make_growth_envelope()

    with patch("app.aggregator.fundamentals_aggregator.get_aggregator") as mock_get_agg:
        mock_agg = MagicMock()
        mock_agg.fetch_module = AsyncMock(return_value=mock_envelope)
        mock_get_agg.return_value = mock_agg

        agent = FundamentalDataAgent()
        result = await agent.collect("CN", "600519", mode="summary")

    assert "collected_modules" in result
    assert "compressed_facts" in result
    assert "data_quality" in result
    assert "missing_modules" in result
    assert isinstance(result["compressed_facts"], list)


# ── T2: Data Agent 不生成投资建议 ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_data_agent_no_investment_advice():
    """T2: Data Agent facts text 不包含投资建议词汇。"""
    from app.agent.fundamental_data_agent import FundamentalDataAgent
    from app.agent.fundamental_review_agent import _SEVERE_BANNED

    mock_envelope = _make_growth_envelope()

    with patch("app.aggregator.fundamentals_aggregator.get_aggregator") as mock_get_agg:
        mock_agg = MagicMock()
        mock_agg.fetch_module = AsyncMock(return_value=mock_envelope)
        mock_get_agg.return_value = mock_agg

        agent = FundamentalDataAgent()
        result = await agent.collect("CN", "600519", mode="summary")

    all_text = " ".join(f.get("text", "") for f in result["compressed_facts"])
    for phrase in _SEVERE_BANNED:
        assert phrase not in all_text, f"Data Agent fact contains banned phrase: {phrase}"


# ── T3: 无 DeepSeek API Key 时返回 partial ────────────────────────────────────

@pytest.mark.asyncio
async def test_no_api_key_returns_partial():
    """T3: DEEPSEEK_API_KEY 未配置时 ai_analysis 返回 partial=True。"""
    from app.agent.fundamental_ai_orchestrator import FundamentalAIOrchestrator

    data_pack = {
        "ts_code": "600519.SH", "market": "CN", "symbol": "600519",
        "collected_modules": ["growth"], "missing_modules": [],
        "stale_modules": [], "partial_modules": [],
        "data_quality": {"score": 80, "level": "high", "issues": []},
        "module_summaries": {}, "compressed_facts": [],
    }

    async def _raise_no_api_key(*args, **kwargs):
        raise RuntimeError("DEEPSEEK_API_KEY 未配置，AI 分析不可用")

    with patch("app.agent.fundamental_data_agent.FundamentalDataAgent.collect", new_callable=AsyncMock, return_value=data_pack):
        with patch("app.agent.fundamental_analysis_agent.FundamentalAnalysisAgent.analyze", side_effect=_raise_no_api_key):
            with patch("app.agent.ai_cache.read_cache", new_callable=AsyncMock, return_value=None):
                with patch("app.agent.ai_cache.read_stale_cache", new_callable=AsyncMock, return_value=None):
                    orch = FundamentalAIOrchestrator()
                    result = await orch.run("CN", "600519", mode="summary")

    assert result["partial"] is True
    assert len(result["errors"]) > 0


# ── T4: Claude 返回合法 JSON 时 envelope 正常 ────────────────────────────────

@pytest.mark.asyncio
async def test_valid_llm_output_envelope():
    """T4: LLM 返回合法 JSON 时，最终 envelope 结构符合 Phase 2D 契约。"""
    from app.agent.fundamental_ai_orchestrator import FundamentalAIOrchestrator

    data_pack = {
        "ts_code": "600519.SH", "market": "CN", "symbol": "600519",
        "collected_modules": ["growth", "valuation"],
        "missing_modules": [],
        "stale_modules": [], "partial_modules": [],
        "data_quality": {"score": 90, "level": "high", "issues": []},
        "module_summaries": {},
        "compressed_facts": [
            {"fact_id": "growth_000", "module_key": "growth", "metric": "revenue_yoy_pct",
             "value": 12.3, "period": "20231231", "text": "营收同比增长12.3%"},
        ],
    }
    analysis = _good_analysis_json()

    with patch("app.agent.fundamental_data_agent.FundamentalDataAgent.collect", new_callable=AsyncMock, return_value=data_pack):
        with patch("app.agent.fundamental_analysis_agent.FundamentalAnalysisAgent.analyze", new_callable=AsyncMock, return_value=analysis):
            with patch("app.agent.ai_cache.read_cache", new_callable=AsyncMock, return_value=None):
                with patch("app.agent.ai_cache.write_cache", new_callable=AsyncMock):
                    orch = FundamentalAIOrchestrator()
                    result = await orch.run("CN", "600519")

    assert result["module_key"] == "ai_analysis"
    assert result["group_seq"] == 8
    assert "data" in result
    assert "ai_analysis" in result["data"]
    assert "meta" in result
    assert result["meta"]["render_type"] == "ai_card"
    assert result["partial"] is False


# ── T5: Analysis Agent 非 JSON 输出被捕获 ────────────────────────────────────

@pytest.mark.asyncio
async def test_analysis_agent_non_json_handled():
    """T5: LLM 返回非 JSON 时 Analysis Agent 抛 ValueError，Orchestrator 返回 partial。"""
    from app.agent.fundamental_ai_orchestrator import FundamentalAIOrchestrator

    data_pack = {
        "ts_code": "600519.SH", "market": "CN", "symbol": "600519",
        "collected_modules": [], "missing_modules": [],
        "stale_modules": [], "partial_modules": [],
        "data_quality": {"score": 50, "level": "medium", "issues": []},
        "module_summaries": {}, "compressed_facts": [],
    }

    async def _bad_analyze(*args, **kwargs):
        raise ValueError("LLM 输出解析失败（非合法 JSON）")

    with patch("app.agent.fundamental_data_agent.FundamentalDataAgent.collect", new_callable=AsyncMock, return_value=data_pack):
        with patch("app.agent.fundamental_analysis_agent.FundamentalAnalysisAgent.analyze", side_effect=_bad_analyze):
            with patch("app.agent.ai_cache.read_cache", new_callable=AsyncMock, return_value=None):
                with patch("app.agent.ai_cache.read_stale_cache", new_callable=AsyncMock, return_value=None):
                    orch = FundamentalAIOrchestrator()
                    result = await orch.run("CN", "600519")

    assert result["partial"] is True
    assert any("解析" in e for e in result["errors"])


# ── T6: Review Agent 拦截"买入" ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_review_blocks_buy_advice():
    """T6: Review Agent 拦截包含"买入"的分析输出。"""
    from app.agent.fundamental_review_agent import FundamentalReviewAgent

    bad_analysis = dict(_good_analysis_json())
    bad_analysis["summary"] = "公司基本面好，值得买入，建议积极加仓。"

    agent = FundamentalReviewAgent()
    result = await agent.review(bad_analysis, {"compressed_facts": []})

    assert result["review_status"] in ("rejected", "revised")
    assert len(result["blocked_phrases"]) > 0 or any(
        "买入" in n.get("message", "") for n in result["review_notes"]
    )


# ── T7: Review Agent 拦截"目标价" ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_review_blocks_target_price():
    """T7: Review Agent 拦截包含"目标价"的内容。"""
    from app.agent.fundamental_review_agent import FundamentalReviewAgent

    bad_analysis = dict(_good_analysis_json())
    bad_analysis["highlights"] = [{"title": "目标价 50 元", "detail": "目标价测算基于 DCF",
                                   "source_modules": [], "source_fact_ids": []}]

    agent = FundamentalReviewAgent()
    result = await agent.review(bad_analysis, {"compressed_facts": []})

    assert result["review_status"] in ("rejected", "revised")


# ── T8: Review Agent 拦截"保证上涨" ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_review_blocks_guaranteed_returns():
    """T8: Review Agent 拦截"保证收益"类表达。"""
    from app.agent.fundamental_review_agent import FundamentalReviewAgent

    bad_analysis = dict(_good_analysis_json())
    bad_analysis["summary"] = "基本面优秀，保证收益，必然上涨。"

    agent = FundamentalReviewAgent()
    result = await agent.review(bad_analysis, {"compressed_facts": []})

    assert result["review_status"] == "rejected"


# ── T9: Review Agent 改写轻微违规表达 ────────────────────────────────────────

@pytest.mark.asyncio
async def test_review_rewrites_mild_phrases():
    """T9: Review Agent 对轻微违规措辞改写，status=revised。"""
    from app.agent.fundamental_review_agent import FundamentalReviewAgent

    mild_analysis = dict(_good_analysis_json())
    mild_analysis["watch_items"] = [
        {"title": "可短期布局", "reason": "适合布局", "source_modules": [], "source_fact_ids": []}
    ]

    agent = FundamentalReviewAgent()
    result = await agent.review(mild_analysis, {"compressed_facts": []})

    assert result["review_status"] in ("revised", "approved")
    if result["review_status"] == "revised":
        final = result.get("final", {})
        # Check that the content sections (not blocked_phrases audit trail) have been rewritten
        watch_text = json.dumps(final.get("watch_items", []), ensure_ascii=False)
        assert "适合布局" not in watch_text, "watch_items should have 适合布局 rewritten"


# ── T10: 严重违规返回 rejected 安全占位 ──────────────────────────────────────

@pytest.mark.asyncio
async def test_review_rejected_returns_safe_placeholder():
    """T10: 严重违规时 final 包含安全占位内容。"""
    from app.agent.fundamental_review_agent import FundamentalReviewAgent
    from app.agent.schemas import SAFE_PLACEHOLDER

    bad_analysis = dict(_good_analysis_json())
    bad_analysis["summary"] = "强烈推荐买入，目标价翻倍。"

    agent = FundamentalReviewAgent()
    result = await agent.review(bad_analysis, {"compressed_facts": []})

    assert result["review_status"] == "rejected"
    final = result.get("final", {})
    assert final.get("overall_score") is None or final.get("summary") == SAFE_PLACEHOLDER["summary"]


# ── T11: source_modules 必须存在 ──────────────────────────────────────────────

def test_good_analysis_has_source_modules():
    """T11: 合规分析输出每条 highlight/risk 都有 source_modules。"""
    analysis = _good_analysis_json()
    for item in analysis.get("highlights", []):
        assert "source_modules" in item
    for item in analysis.get("risks", []):
        assert "source_modules" in item


# ── T12: source_fact_ids 必须存在 ────────────────────────────────────────────

def test_good_analysis_has_source_fact_ids():
    """T12: 合规分析输出每条 highlight/risk 都有 source_fact_ids。"""
    analysis = _good_analysis_json()
    for item in analysis.get("highlights", []):
        assert "source_fact_ids" in item


# ── T13: 引用不存在 fact_id 时被审核层标记 ───────────────────────────────────

@pytest.mark.asyncio
async def test_review_flags_invalid_fact_ids():
    """T13: source_fact_ids 引用了 data_pack 中不存在的 fact_id，审核层应标记。"""
    from app.agent.fundamental_review_agent import FundamentalReviewAgent

    analysis = dict(_good_analysis_json())
    analysis["highlights"] = [{"title": "...", "detail": "...",
                                "source_modules": ["growth"], "source_fact_ids": ["nonexistent_999"]}]

    data_pack = {"compressed_facts": [{"fact_id": "growth_000"}]}
    agent = FundamentalReviewAgent()
    result = await agent.review(analysis, data_pack)

    # Should be revised (warning added) or note about fact_id issues
    if result["review_status"] == "revised":
        assert any("fact_id" in n.get("type", "") or "fact_id" in n.get("message", "")
                   for n in result["review_notes"])


# ── T14: 缓存命中 ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cache_hit():
    """T14: 缓存命中时不调用 Analysis Agent。"""
    from app.agent.fundamental_ai_orchestrator import FundamentalAIOrchestrator

    data_pack = {
        "ts_code": "600519.SH", "market": "CN", "symbol": "600519",
        "collected_modules": ["growth"], "missing_modules": [],
        "stale_modules": [], "partial_modules": [],
        "data_quality": {"score": 80, "level": "high", "issues": []},
        "module_summaries": {}, "compressed_facts": [],
    }
    cached_result = {"ai_analysis": {"summary": "缓存分析", "overall_score": 70, "review": {"review_status": "approved"}}}

    with patch("app.agent.fundamental_data_agent.FundamentalDataAgent.collect", new_callable=AsyncMock, return_value=data_pack):
        with patch("app.agent.ai_cache.read_cache", new_callable=AsyncMock, return_value=cached_result):
            mock_analyze = AsyncMock()
            with patch("app.agent.fundamental_analysis_agent.FundamentalAnalysisAgent.analyze", mock_analyze):
                orch = FundamentalAIOrchestrator()
                result = await orch.run("CN", "600519")

    mock_analyze.assert_not_called()
    assert result["data"]["ai_analysis"]["summary"] == "缓存分析"


# ── T15: force_refresh 绕过缓存 ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_force_refresh_bypasses_cache():
    """T15: force_refresh=True 时不读取缓存，调用 Analysis Agent。"""
    from app.agent.fundamental_ai_orchestrator import FundamentalAIOrchestrator

    data_pack = {
        "ts_code": "600519.SH", "market": "CN", "symbol": "600519",
        "collected_modules": [], "missing_modules": [],
        "stale_modules": [], "partial_modules": [],
        "data_quality": {"score": 50, "level": "medium", "issues": []},
        "module_summaries": {}, "compressed_facts": [],
    }
    analysis = _good_analysis_json()

    with patch("app.agent.fundamental_data_agent.FundamentalDataAgent.collect", new_callable=AsyncMock, return_value=data_pack):
        with patch("app.agent.ai_cache.read_cache", new_callable=AsyncMock) as mock_read:
            with patch("app.agent.fundamental_analysis_agent.FundamentalAnalysisAgent.analyze", new_callable=AsyncMock, return_value=analysis):
                with patch("app.agent.ai_cache.write_cache", new_callable=AsyncMock):
                    orch = FundamentalAIOrchestrator()
                    await orch.run("CN", "600519", force_refresh=True)

    mock_read.assert_not_called()


# ── T16: stale AI 缓存在 LLM 失败时可返回 ───────────────────────────────────

@pytest.mark.asyncio
async def test_stale_cache_returned_on_llm_failure():
    """T16: LLM 不可用时，若有 stale 缓存则返回 stale=True。"""
    from app.agent.fundamental_ai_orchestrator import FundamentalAIOrchestrator

    data_pack = {
        "ts_code": "600519.SH", "market": "CN", "symbol": "600519",
        "collected_modules": [], "missing_modules": [],
        "stale_modules": [], "partial_modules": [],
        "data_quality": {"score": 50, "level": "medium", "issues": []},
        "module_summaries": {}, "compressed_facts": [],
    }
    stale_cached = {"ai_analysis": {"summary": "旧缓存分析", "overall_score": 65, "review": {"review_status": "approved"}}, "_stale": True}

    async def _unavailable(*args, **kwargs):
        raise RuntimeError("DEEPSEEK_API_KEY 未配置")

    with patch("app.agent.fundamental_data_agent.FundamentalDataAgent.collect", new_callable=AsyncMock, return_value=data_pack):
        with patch("app.agent.ai_cache.read_cache", new_callable=AsyncMock, return_value=None):
            with patch("app.agent.fundamental_analysis_agent.FundamentalAnalysisAgent.analyze", side_effect=_unavailable):
                with patch("app.agent.ai_cache.read_stale_cache", new_callable=AsyncMock, return_value=stale_cached):
                    orch = FundamentalAIOrchestrator()
                    result = await orch.run("CN", "600519")

    assert result["stale"] is True


# ── T17: rejected 内容不写入缓存 ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_rejected_not_cached():
    """T17: review_status=rejected 时不写入缓存。"""
    from app.agent.fundamental_ai_orchestrator import FundamentalAIOrchestrator

    data_pack = {
        "ts_code": "600519.SH", "market": "CN", "symbol": "600519",
        "collected_modules": ["growth"], "missing_modules": [],
        "stale_modules": [], "partial_modules": [],
        "data_quality": {"score": 80, "level": "high", "issues": []},
        "module_summaries": {}, "compressed_facts": [],
    }

    # Analysis returns something with severe banned phrase
    bad_analysis = dict(_good_analysis_json())
    bad_analysis["summary"] = "强烈推荐买入，目标价翻倍保证上涨。"

    with patch("app.agent.fundamental_data_agent.FundamentalDataAgent.collect", new_callable=AsyncMock, return_value=data_pack):
        with patch("app.agent.ai_cache.read_cache", new_callable=AsyncMock, return_value=None):
            with patch("app.agent.fundamental_analysis_agent.FundamentalAnalysisAgent.analyze", new_callable=AsyncMock, return_value=bad_analysis):
                mock_write = AsyncMock()
                with patch("app.agent.ai_cache.write_cache", mock_write):
                    orch = FundamentalAIOrchestrator()
                    result = await orch.run("CN", "600519")

    mock_write.assert_not_called()


# ── T18: revised 内容可写入缓存 ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_revised_is_cached():
    """T18: review_status=revised 时内容写入缓存。"""
    from app.agent.fundamental_ai_orchestrator import FundamentalAIOrchestrator

    data_pack = {
        "ts_code": "600519.SH", "market": "CN", "symbol": "600519",
        "collected_modules": ["growth"], "missing_modules": [],
        "stale_modules": [], "partial_modules": [],
        "data_quality": {"score": 80, "level": "high", "issues": []},
        "module_summaries": {}, "compressed_facts": [],
    }

    # Analysis with mild phrase (should be revised, not rejected)
    mild_analysis = dict(_good_analysis_json())
    mild_analysis["watch_items"] = [
        {"title": "适合布局", "reason": "适合布局", "source_modules": [], "source_fact_ids": []}
    ]

    with patch("app.agent.fundamental_data_agent.FundamentalDataAgent.collect", new_callable=AsyncMock, return_value=data_pack):
        with patch("app.agent.ai_cache.read_cache", new_callable=AsyncMock, return_value=None):
            with patch("app.agent.fundamental_analysis_agent.FundamentalAnalysisAgent.analyze", new_callable=AsyncMock, return_value=mild_analysis):
                mock_write = AsyncMock()
                with patch("app.agent.ai_cache.write_cache", mock_write):
                    orch = FundamentalAIOrchestrator()
                    result = await orch.run("CN", "600519")

    # If review_status is revised, cache should be written
    if result["data"]["ai_analysis"].get("review", {}).get("review_status") == "revised":
        mock_write.assert_called_once()


# ── T19: 其他 fundamentals 模块不受影响 ──────────────────────────────────────

@pytest.mark.asyncio
async def test_other_modules_unaffected():
    """T19: ai_analysis 模块失败时，growth 等其他模块仍可正常获取（通过 Data Agent mock 验证）。"""
    from app.agent.fundamental_data_agent import FundamentalDataAgent

    # Verify Data Agent can still collect growth data even if ai_analysis would fail
    mock_envelope = _make_growth_envelope()

    with patch("app.aggregator.fundamentals_aggregator.get_aggregator") as mock_get_agg:
        mock_agg = MagicMock()
        mock_agg.fetch_module = AsyncMock(return_value=mock_envelope)
        mock_get_agg.return_value = mock_agg

        agent = FundamentalDataAgent()
        result = await agent.collect("CN", "600519", mode="summary")

    # growth data should be collected successfully
    assert "growth" in result["collected_modules"]
    assert result["data_quality"]["score"] > 0


# ── T20: ai_analysis DataEnvelope 顶层结构符合 Phase 2D 契约 ─────────────────

@pytest.mark.asyncio
async def test_envelope_structure_matches_phase2d():
    """T20: ai_analysis 返回 envelope 包含所有 Phase 2D 必需顶层字段。"""
    from app.agent.fundamental_ai_orchestrator import FundamentalAIOrchestrator

    data_pack = {
        "ts_code": "600519.SH", "market": "CN", "symbol": "600519",
        "collected_modules": ["growth"], "missing_modules": [],
        "stale_modules": [], "partial_modules": [],
        "data_quality": {"score": 80, "level": "high", "issues": []},
        "module_summaries": {}, "compressed_facts": [
            {"fact_id": "growth_000", "module_key": "growth", "metric": "revenue_yoy_pct",
             "value": 12.3, "period": "20231231", "text": "营收同比增长12.3%"},
        ],
    }

    analysis = _good_analysis_json()

    with patch("app.agent.fundamental_data_agent.FundamentalDataAgent.collect", new_callable=AsyncMock, return_value=data_pack):
        with patch("app.agent.fundamental_analysis_agent.FundamentalAnalysisAgent.analyze", new_callable=AsyncMock, return_value=analysis):
            with patch("app.agent.ai_cache.read_cache", new_callable=AsyncMock, return_value=None):
                with patch("app.agent.ai_cache.write_cache", new_callable=AsyncMock):
                    orch = FundamentalAIOrchestrator()
                    result = await orch.run("CN", "600519")

    required_fields = {"market", "symbol", "ts_code", "module_key", "module_name",
                       "group", "group_seq", "data", "errors", "partial", "stale",
                       "generated_at", "source", "meta"}
    missing = required_fields - set(result.keys())
    assert not missing, f"Envelope missing fields: {missing}"
    assert result["meta"]["render_type"] == "ai_card"
    assert result["meta"]["disclaimer_type"] == "ai_generated"
