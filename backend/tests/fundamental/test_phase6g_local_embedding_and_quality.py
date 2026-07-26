"""
test_phase6g_local_embedding_and_quality.py — Phase 6G: Local Embedding + RAG Quality

Tests:
  1.  mock provider is default when REPORT_EMBEDDING_PROVIDER not set
  2.  mock provider embeds texts and returns correct dim vectors
  3.  disabled provider is_available=False and returns reason
  4.  disabled provider raises on embed_texts()
  5.  local provider init failure (no sentence-transformers) returns clear reason
  6.  local provider without REPORT_EMBEDDING_MODEL falls back to mock
  7.  dim mismatch: model_dim=384, target_dim=1536 → vector padded to 1536
  8.  dim mismatch: model_dim=2048, target_dim=1536 → vector truncated to 1536
  9.  embed_report uses provider — disabled returns skipped
  10. embed_report uses provider — mock embeds successfully
  11. rag_query returns fallback_used=True when vector search fails
  12. rag_query returns fallback_used=False when vector search succeeds
  13. quality evaluation keyword check helper works correctly
"""
from __future__ import annotations

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ── 1. mock provider is default ───────────────────────────────────────────────

def test_mock_provider_is_default():
    from app.services.report_embedding_provider import get_report_embedding_provider

    with patch("app.services.report_embedding_provider.get_settings") as mock_settings:
        settings = MagicMock()
        settings.report_embedding_provider = "mock"
        settings.report_embedding_dim = 1536
        settings.report_embedding_model = None
        mock_settings.return_value = settings

        provider = get_report_embedding_provider()

    assert provider.provider_name == "mock"
    assert provider.is_available() is True


# ── 2. mock provider embeds correctly ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_mock_provider_embed_correct_dim():
    from app.services.report_embedding_provider import MockReportEmbeddingProvider

    provider = MockReportEmbeddingProvider(target_dim=1536)
    texts = ["贵州茅台年度报告", "现金流量分析"]
    vectors = await provider.embed_texts(texts)

    assert len(vectors) == 2
    assert all(len(v) == 1536 for v in vectors), "Each vector must be 1536-dim"
    # Same input → same output (deterministic)
    vectors2 = await provider.embed_texts(texts)
    assert vectors[0] == vectors2[0], "Mock provider must be deterministic"


# ── 3. disabled provider is_available=False ───────────────────────────────────

def test_disabled_provider_not_available():
    from app.services.report_embedding_provider import DisabledReportEmbeddingProvider

    provider = DisabledReportEmbeddingProvider()
    assert provider.is_available() is False
    assert provider.unavailability_reason() is not None
    assert "disabled" in provider.unavailability_reason().lower()


# ── 4. disabled provider raises on embed_texts ───────────────────────────────

@pytest.mark.asyncio
async def test_disabled_provider_raises_on_embed():
    from app.services.report_embedding_provider import DisabledReportEmbeddingProvider

    provider = DisabledReportEmbeddingProvider()
    with pytest.raises(RuntimeError, match="disabled"):
        await provider.embed_texts(["test"])


# ── 5. local provider init failure → clear reason ─────────────────────────────

def test_local_provider_no_sentence_transformers():
    from app.services.report_embedding_provider import LocalSentenceTransformerProvider

    with patch.dict("sys.modules", {"sentence_transformers": None}):
        # Force ImportError
        import sys
        original = sys.modules.get("sentence_transformers")
        sys.modules["sentence_transformers"] = None  # Simulate not installed

        try:
            provider = LocalSentenceTransformerProvider(
                model_name_or_path="BAAI/bge-small-zh-v1.5",
                target_dim=1536,
            )
            # Should not crash; should set init_error
            assert not provider.is_available()
            assert provider.unavailability_reason() is not None
        finally:
            if original is None:
                del sys.modules["sentence_transformers"]
            else:
                sys.modules["sentence_transformers"] = original


# ── 6. local provider without model → fallback to mock ───────────────────────

def test_local_provider_no_model_fallback():
    from app.services.report_embedding_provider import get_report_embedding_provider

    with patch("app.services.report_embedding_provider.get_settings") as mock_settings:
        settings = MagicMock()
        settings.report_embedding_provider = "local"
        settings.report_embedding_dim = 1536
        settings.report_embedding_model = None  # No model specified
        mock_settings.return_value = settings

        provider = get_report_embedding_provider()

    assert provider.provider_name == "mock", "Should fallback to mock when no model specified"


# ── 7. dim mismatch: 384-dim model vs 1536 target → unavailable (Phase 6G-1) ──
# NOTE: Silent pad/truncate removed in Phase 6G-1. Dim mismatch now marks the
# provider as unavailable with an explicit error reason.

def test_dim_mismatch_padding():
    """Phase 6G-1: mismatch (smaller dim) → unavailable, no silent padding."""
    import sys, types
    from unittest.mock import MagicMock
    from app.services.report_embedding_provider import LocalSentenceTransformerProvider

    mock_model = MagicMock()
    mock_model.get_sentence_embedding_dimension.return_value = 384  # model is 384-dim
    fake_st = types.ModuleType("sentence_transformers")
    fake_st.SentenceTransformer = MagicMock(return_value=mock_model)

    with patch.dict(sys.modules, {"sentence_transformers": fake_st}):
        provider = LocalSentenceTransformerProvider("some-model", target_dim=1536)

    # Must be unavailable (dim mismatch, not silent padding)
    assert not provider.is_available()
    reason = provider.unavailability_reason()
    assert "384" in reason
    assert "1536" in reason
    assert not hasattr(provider, "_adjust_dim"), "_adjust_dim must not exist in Phase 6G-1"


# ── 8. dim mismatch: 2048-dim model vs 384 target → unavailable (Phase 6G-1) ─
# NOTE: Silent pad/truncate removed in Phase 6G-1. Dim mismatch now marks the
# provider as unavailable with an explicit error reason.

def test_dim_mismatch_truncation():
    """Phase 6G-1: mismatch (larger dim) → unavailable, no silent truncation."""
    import sys, types
    from unittest.mock import MagicMock
    from app.services.report_embedding_provider import LocalSentenceTransformerProvider

    mock_model = MagicMock()
    mock_model.get_sentence_embedding_dimension.return_value = 2048  # model is 2048-dim
    fake_st = types.ModuleType("sentence_transformers")
    fake_st.SentenceTransformer = MagicMock(return_value=mock_model)

    with patch.dict(sys.modules, {"sentence_transformers": fake_st}):
        provider = LocalSentenceTransformerProvider("some-model", target_dim=384)

    # Must be unavailable (dim mismatch, not silent truncation)
    assert not provider.is_available()
    reason = provider.unavailability_reason()
    assert "2048" in reason
    assert "384" in reason
    assert not hasattr(provider, "_adjust_dim"), "_adjust_dim must not exist in Phase 6G-1"


# ── 9. embed_report with disabled provider → skipped ─────────────────────────

@pytest.mark.asyncio
async def test_embed_report_disabled_provider():
    from app.services.report_embedding_service import ReportEmbeddingService
    from app.services.report_embedding_provider import DisabledReportEmbeddingProvider

    svc = ReportEmbeddingService()

    # Mock doc with chunked status
    doc = MagicMock()
    doc.id = 1
    doc.rag_status = "chunked"
    doc.rag_error = None

    mock_db = AsyncMock()
    call_count = [0]
    async def _exec(stmt, *args, **kwargs):
        r = MagicMock()
        r.scalars.return_value.first.return_value = doc
        r.scalars.return_value.all.return_value = []
        call_count[0] += 1
        return r
    mock_db.execute = _exec
    mock_db.commit = AsyncMock()

    with patch(
        "app.services.report_embedding_service.get_report_embedding_provider",
        return_value=DisabledReportEmbeddingProvider(),
    ):
        result = await svc.embed_report(1, mock_db)

    assert result["status"] == "skipped"
    assert result["provider"] == "disabled"


# ── 10. embed_report with mock provider → embedded ───────────────────────────

@pytest.mark.asyncio
async def test_embed_report_mock_provider():
    from app.services.report_embedding_service import ReportEmbeddingService
    from app.services.report_embedding_provider import MockReportEmbeddingProvider

    svc = ReportEmbeddingService()

    doc = MagicMock()
    doc.id = 1
    doc.rag_status = "chunked"
    doc.rag_error = None

    chunk = MagicMock()
    chunk.id = 10
    chunk.content = "贵州茅台年度报告正文内容" * 50
    chunk.embedding = None
    chunk.embed_error = None

    mock_db = AsyncMock()
    call_count = [0]
    async def _exec(stmt, *args, **kwargs):
        r = MagicMock()
        if call_count[0] == 0:
            r.scalars.return_value.first.return_value = doc
        else:
            r.scalars.return_value.all.return_value = [chunk]
        call_count[0] += 1
        return r
    mock_db.execute = _exec
    mock_db.commit = AsyncMock()

    with patch(
        "app.services.report_embedding_service.get_report_embedding_provider",
        return_value=MockReportEmbeddingProvider(target_dim=1536),
    ):
        with patch("app.services.report_embedding_service.get_settings") as ms:
            ms.return_value.report_embedding_model = None
            ms.return_value.report_embedding_provider = "mock"
            result = await svc.embed_report(1, mock_db)

    assert result["status"] in ("embedded", "partial"), f"Got: {result}"
    assert result["provider"] == "mock"


# ── 11. rag_query fallback_used=True when vector fails ────────────────────────

@pytest.mark.asyncio
async def test_rag_query_fallback_used_true():
    from app.services.report_rag_service import ReportRagService

    svc = ReportRagService()
    chunk = MagicMock()
    chunk.id = 1
    chunk.report_id = 1
    chunk.ts_code = "600519.SH"
    chunk.content = "现金流量分析"
    chunk.chunk_index = 0
    chunk.section_title = "现金流"
    chunk.embedding = None
    chunk.report_type = "annual"
    chunk.report_year = 2024
    chunk.period = "2024-12-31"

    mock_db = AsyncMock()
    empty_r = MagicMock()
    empty_r.fetchall.return_value = []
    kw_r = MagicMock()
    kw_r.scalars.return_value.all.return_value = [chunk]

    call_count = [0]
    async def _exec(stmt, *a, **kw):
        if call_count[0] == 0:
            call_count[0] += 1
            return empty_r
        return kw_r
    mock_db.execute = _exec

    with patch.object(svc, '_vector_search', side_effect=Exception("no embedding")):
        result = await svc.query("600519.SH", "现金流", mock_db)

    assert result["fallback_used"] is True


# ── 12. rag_query fallback_used=False when vector succeeds ───────────────────

@pytest.mark.asyncio
async def test_rag_query_fallback_used_false():
    from app.services.report_rag_service import ReportRagService

    svc = ReportRagService()
    chunk = MagicMock()
    chunk.id = 1
    chunk.report_id = 1
    chunk.ts_code = "600519.SH"
    chunk.content = "经营活动现金流净额"
    chunk.chunk_index = 0
    chunk.section_title = "现金流量分析"
    chunk.embedding = [0.1] * 1536
    chunk.report_type = "annual"
    chunk.report_year = 2024
    chunk.period = "2024-12-31"

    mock_db = AsyncMock()

    with patch.object(svc, '_vector_search', return_value=[chunk]):
        result = await svc.query("600519.SH", "现金流情况如何", mock_db)

    assert result["fallback_used"] is False
    assert result["search_mode"] == "vector"


# ── 13. quality evaluation keyword check works ────────────────────────────────

def test_keyword_check_helper():
    # Import the function from the evaluation script
    import importlib.util
    from pathlib import Path

    script = Path("scripts/evaluate_report_rag_quality.py")
    if not script.exists():
        pytest.skip("evaluation script not found")

    spec = importlib.util.spec_from_file_location("eval_script", script)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    content = "本报告期经营活动现金流净额为 269 亿元，同比增长 15%"
    has, matched = mod._check_keywords(content, ["经营活动现金流", "现金流量", "收现"])
    assert has is True
    assert "经营活动现金流" in matched

    has2, matched2 = mod._check_keywords("无关内容", ["经营活动现金流"])
    assert has2 is False
