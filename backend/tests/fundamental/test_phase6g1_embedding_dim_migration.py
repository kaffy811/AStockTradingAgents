"""
tests/fundamental/test_phase6g1_embedding_dim_migration.py

Phase 6G-1: Embedding dimension migration vector(1536) → vector(384)
9 tests covering:
  1. MockReportEmbeddingProvider defaults to 384-dim
  2. Mock outputs exactly 384 floats
  3. LocalSentenceTransformerProvider: dim match → available
  4. LocalSentenceTransformerProvider: dim mismatch → unavailable with reason
  5. LocalSentenceTransformerProvider: dim mismatch → embed_texts raises (no silent pad)
  6. No _adjust_dim method exists on LocalSentenceTransformerProvider
  7. DisabledReportEmbeddingProvider: keyword-only (dim 384 default)
  8. get_report_embedding_provider factory uses dim from settings
  9. Migration revision IDs chain correctly (g5h6i7j8k9l0 → f4a5b6c7d8e9)
"""
from __future__ import annotations

import asyncio
import importlib
import math
import sys
import types
from unittest.mock import MagicMock, patch

import pytest


# ── Helpers ────────────────────────────────────────────────────────────────────

def _run(coro):
    return asyncio.run(coro)


def _make_mock_model(dim: int):
    """Stub SentenceTransformer that returns dim-sized embeddings."""
    import numpy as np

    model = MagicMock()
    model.get_sentence_embedding_dimension.return_value = dim
    model.encode.return_value = [
        [0.1 / math.sqrt(dim)] * dim
    ]
    return model


# ── Test 1: Mock default dim = 384 ────────────────────────────────────────────

def test_mock_provider_default_dim_is_384():
    from app.services.report_embedding_provider import MockReportEmbeddingProvider
    p = MockReportEmbeddingProvider()
    assert p.embedding_dim == 384


# ── Test 2: Mock outputs exactly 384 floats ───────────────────────────────────

def test_mock_provider_outputs_384_floats():
    from app.services.report_embedding_provider import MockReportEmbeddingProvider
    p = MockReportEmbeddingProvider()
    vecs = _run(p.embed_texts(["hello", "world"]))
    assert len(vecs) == 2
    for vec in vecs:
        assert len(vec) == 384, f"expected 384, got {len(vec)}"


# ── Test 3: Local provider dim match → available ──────────────────────────────

def test_local_provider_dim_match_is_available():
    from app.services.report_embedding_provider import LocalSentenceTransformerProvider

    mock_model = _make_mock_model(384)
    fake_st = types.ModuleType("sentence_transformers")
    fake_st.SentenceTransformer = MagicMock(return_value=mock_model)

    with patch.dict(sys.modules, {"sentence_transformers": fake_st}):
        p = LocalSentenceTransformerProvider("BAAI/bge-small-zh-v1.5", target_dim=384)

    assert p.is_available(), f"should be available; reason: {p.unavailability_reason()}"
    assert p.embedding_dim == 384


# ── Test 4: Local provider dim mismatch → unavailable with reason ─────────────

def test_local_provider_dim_mismatch_unavailable():
    from app.services.report_embedding_provider import LocalSentenceTransformerProvider

    mock_model = _make_mock_model(768)  # wrong dim
    fake_st = types.ModuleType("sentence_transformers")
    fake_st.SentenceTransformer = MagicMock(return_value=mock_model)

    with patch.dict(sys.modules, {"sentence_transformers": fake_st}):
        p = LocalSentenceTransformerProvider("BAAI/bge-base-zh-v1.5", target_dim=384)

    assert not p.is_available()
    reason = p.unavailability_reason()
    assert reason is not None
    assert "768" in reason, f"reason should mention model dim 768: {reason}"
    assert "384" in reason, f"reason should mention target_dim 384: {reason}"


# ── Test 5: Dim mismatch → embed_texts raises (no silent pad/truncate) ────────

def test_local_provider_dim_mismatch_embed_raises():
    from app.services.report_embedding_provider import LocalSentenceTransformerProvider

    mock_model = _make_mock_model(768)
    fake_st = types.ModuleType("sentence_transformers")
    fake_st.SentenceTransformer = MagicMock(return_value=mock_model)

    with patch.dict(sys.modules, {"sentence_transformers": fake_st}):
        p = LocalSentenceTransformerProvider("BAAI/bge-base-zh-v1.5", target_dim=384)

    # embed_texts must raise (provider is unavailable due to dim mismatch)
    with pytest.raises(RuntimeError):
        _run(p.embed_texts(["test text"]))


# ── Test 6: _adjust_dim method must not exist ─────────────────────────────────

def test_local_provider_no_adjust_dim_method():
    from app.services.report_embedding_provider import LocalSentenceTransformerProvider
    assert not hasattr(LocalSentenceTransformerProvider, "_adjust_dim"), (
        "_adjust_dim should have been removed in Phase 6G-1 (no silent pad/truncate)"
    )


# ── Test 7: Disabled provider defaults to 384-dim ─────────────────────────────

def test_disabled_provider_keyword_only():
    from app.services.report_embedding_provider import DisabledReportEmbeddingProvider
    p = DisabledReportEmbeddingProvider()
    assert not p.is_available()
    assert p.embedding_dim == 384
    reason = p.unavailability_reason()
    assert reason is not None
    with pytest.raises(RuntimeError):
        _run(p.embed_texts(["test"]))


# ── Test 8: Factory uses REPORT_EMBEDDING_DIM from settings ───────────────────

def test_factory_uses_dim_from_settings():
    from app.services import report_embedding_provider as mod

    mock_settings = MagicMock()
    mock_settings.report_embedding_provider = "mock"
    mock_settings.report_embedding_dim = 384
    mock_settings.report_embedding_model = None

    with patch.object(mod, "get_settings", return_value=mock_settings):
        p = mod.get_report_embedding_provider()

    assert p.provider_name == "mock"
    assert p.embedding_dim == 384


# ── Test 9: Migration revision chain ──────────────────────────────────────────

def test_migration_revision_chain():
    """Migration g5h6i7j8k9l0 must chain from f4a5b6c7d8e9 (Phase 6F head)."""
    import importlib.util, pathlib

    migration_path = (
        pathlib.Path(__file__).parent.parent.parent
        / "alembic" / "versions"
        / "2026_07_06_0005-g5h6i7j8k9l0_migrate_embedding_to_384.py"
    )
    assert migration_path.exists(), f"Migration file not found: {migration_path}"

    spec = importlib.util.spec_from_file_location("mig_6g1", migration_path)
    mig = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mig)

    assert mig.revision == "g5h6i7j8k9l0"
    assert mig.down_revision == "f4a5b6c7d8e9"
