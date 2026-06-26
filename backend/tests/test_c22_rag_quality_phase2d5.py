"""
tests/test_c22_rag_quality_phase2d5.py

Phase 2D.5: RAG Quality Hardening — 11 tests covering:
  T1  Batch-level retry config fields in Settings
  T2  _get_batch_retry_config returns correct tuple
  T3  _openai_embed_batch_with_retry retries on failure then succeeds
  T4  _openai_embed_batch_with_retry raises after exhausting retries
  T5  _parse_vec_text handles well-formed and malformed inputs
  T6  _cosine_sim correct values (orthogonal, same, opposite)
  T7  _cosine_mmr selects top-k with diversity
  T8  _mmr_filter_with_strategy returns "cosine" strategy when _chunk_vec present
  T9  _mmr_filter_with_strategy returns "per_doc_cap" when no _chunk_vec
  T10 financial_rag_search diagnostics include mmr_strategy + score_weights
  T11 run_rag_eval returns Recall@k == 1.0 on all 25 eval cases (mock DB)
"""
from __future__ import annotations

import asyncio
import math
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ══════════════════════════════════════════════════════════════════════════════
# T1 — Batch retry config fields in Settings
# ══════════════════════════════════════════════════════════════════════════════

class TestBatchRetryConfigFields:

    def test_fields_have_correct_defaults(self):
        from app.core.config import settings

        # Fields exist and have correct types / default values
        assert isinstance(settings.embedding_batch_retry_count, int)
        assert settings.embedding_batch_retry_count >= 0

        assert isinstance(settings.embedding_batch_retry_backoff_seconds, float)
        assert settings.embedding_batch_retry_backoff_seconds > 0

        assert isinstance(settings.embedding_batch_timeout_seconds, float)
        assert settings.embedding_batch_timeout_seconds > 0

    def test_default_values(self):
        from app.core.config import settings

        assert settings.embedding_batch_retry_count == 2
        assert settings.embedding_batch_retry_backoff_seconds == 1.5
        assert settings.embedding_batch_timeout_seconds == 30.0


# ══════════════════════════════════════════════════════════════════════════════
# T2 — _get_batch_retry_config returns correct tuple
# ══════════════════════════════════════════════════════════════════════════════

class TestGetBatchRetryConfig:

    def test_returns_three_tuple(self):
        from app.agents.embedding_service import _get_batch_retry_config

        result = _get_batch_retry_config()
        assert isinstance(result, tuple)
        assert len(result) == 3

    def test_values_are_positive(self):
        from app.agents.embedding_service import _get_batch_retry_config

        retry_count, backoff, timeout = _get_batch_retry_config()
        assert retry_count >= 0
        assert backoff > 0
        assert timeout > 0

    def test_matches_settings(self):
        from app.agents.embedding_service import _get_batch_retry_config
        from app.core.config import settings

        retry_count, backoff, timeout = _get_batch_retry_config()
        assert retry_count == settings.embedding_batch_retry_count
        assert backoff     == settings.embedding_batch_retry_backoff_seconds
        assert timeout     == settings.embedding_batch_timeout_seconds


# ══════════════════════════════════════════════════════════════════════════════
# T3 — _openai_embed_batch_with_retry retries on failure then succeeds
# ══════════════════════════════════════════════════════════════════════════════

class TestBatchRetrySucceeds:

    @pytest.mark.asyncio
    async def test_retries_once_and_succeeds(self):
        from app.agents.embedding_service import _openai_embed_batch_with_retry

        call_count = 0
        good_vec   = [[0.1] * 1536]

        async def _mock_inner(texts, *, model, api_key, timeout_seconds):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("transient error")
            return good_vec

        with patch(
            "app.agents.embedding_service._openai_embed_texts_with_timeout",
            side_effect=_mock_inner,
        ):
            result = await _openai_embed_batch_with_retry(
                ["test text"],
                model="text-embedding-3-small",
                api_key="sk-fake",
                retry_count=2,
                backoff_seconds=0.001,
                timeout_seconds=10.0,
            )

        assert call_count == 2
        assert len(result) == 1
        assert len(result[0]) == 1536


# ══════════════════════════════════════════════════════════════════════════════
# T4 — _openai_embed_batch_with_retry raises after exhausting retries
# ══════════════════════════════════════════════════════════════════════════════

class TestBatchRetryExhausted:

    @pytest.mark.asyncio
    async def test_raises_after_all_attempts(self):
        from app.agents.embedding_service import _openai_embed_batch_with_retry

        attempts = 0

        async def _always_fail(texts, *, model, api_key, timeout_seconds):
            nonlocal attempts
            attempts += 1
            raise ConnectionError("network down")

        with patch(
            "app.agents.embedding_service._openai_embed_texts_with_timeout",
            side_effect=_always_fail,
        ):
            with pytest.raises(RuntimeError, match="failed after"):
                await _openai_embed_batch_with_retry(
                    ["hello"],
                    model="text-embedding-3-small",
                    api_key="sk-fake",
                    retry_count=2,
                    backoff_seconds=0.001,
                    timeout_seconds=5.0,
                )

        # 1 initial + 2 retries = 3 attempts
        assert attempts == 3


# ══════════════════════════════════════════════════════════════════════════════
# T5 — _parse_vec_text handles various inputs
# ══════════════════════════════════════════════════════════════════════════════

class TestParseVecText:

    def test_valid_vector(self):
        from app.agents.financial_rag_tool import _parse_vec_text

        result = _parse_vec_text("[0.1,0.2,0.3]")
        assert result == pytest.approx([0.1, 0.2, 0.3])

    def test_none_returns_none(self):
        from app.agents.financial_rag_tool import _parse_vec_text

        assert _parse_vec_text(None) is None

    def test_empty_string_returns_none(self):
        from app.agents.financial_rag_tool import _parse_vec_text

        assert _parse_vec_text("") is None

    def test_malformed_returns_none(self):
        from app.agents.financial_rag_tool import _parse_vec_text

        assert _parse_vec_text("[abc,def]") is None

    def test_large_vector(self):
        from app.agents.financial_rag_tool import _parse_vec_text

        vec_str = "[" + ",".join(f"{i/1000:.4f}" for i in range(1536)) + "]"
        result = _parse_vec_text(vec_str)
        assert result is not None
        assert len(result) == 1536


# ══════════════════════════════════════════════════════════════════════════════
# T6 — _cosine_sim correct values
# ══════════════════════════════════════════════════════════════════════════════

class TestCosineSim:

    def test_identical_vectors(self):
        from app.agents.financial_rag_tool import _cosine_sim

        v = [1.0, 0.0, 0.0]
        assert _cosine_sim(v, v) == pytest.approx(1.0, abs=1e-6)

    def test_orthogonal_vectors(self):
        from app.agents.financial_rag_tool import _cosine_sim

        a = [1.0, 0.0, 0.0]
        b = [0.0, 1.0, 0.0]
        assert _cosine_sim(a, b) == pytest.approx(0.0, abs=1e-6)

    def test_opposite_vectors(self):
        from app.agents.financial_rag_tool import _cosine_sim

        a = [1.0, 0.0]
        b = [-1.0, 0.0]
        assert _cosine_sim(a, b) == pytest.approx(-1.0, abs=1e-6)

    def test_empty_returns_zero(self):
        from app.agents.financial_rag_tool import _cosine_sim

        assert _cosine_sim([], []) == 0.0

    def test_length_mismatch_returns_zero(self):
        from app.agents.financial_rag_tool import _cosine_sim

        assert _cosine_sim([1.0, 2.0], [1.0]) == 0.0


# ══════════════════════════════════════════════════════════════════════════════
# T7 — _cosine_mmr selects top-k with diversity
# ══════════════════════════════════════════════════════════════════════════════

class TestCosineMMR:

    def _make_result(self, doc_id: str, score: float, vec: list[float]) -> dict:
        return {
            "title":           f"Doc {doc_id}",
            "source_type":     "annual_report",
            "source":          "SEC",
            "published_at":    "2025-01-01",
            "chunk":           f"chunk text for {doc_id}",
            "score":           score,
            "score_detail":    {"combined_score": score, "vector_score": score,
                                "keyword_score": 0.0, "source_boost": 0.0, "recency_boost": 0.0},
            "search_mode_used": "vector",
            "_chunk_vec":      vec,
            "metadata": {
                "doc_id":       doc_id,
                "source_level": "general",
                "symbol":       "AAPL",
                "market":       "US",
                "url":          "",
                "page":         None,
                "page_start":   None,
                "page_end":     None,
                "authority_score": 0.3,
                "verified":     False,
                "report_year":  None,
                "report_type":  "",
                "search_mode_used": "vector",
            },
        }

    def test_selects_diverse_results(self):
        from app.agents.financial_rag_tool import _cosine_mmr

        # Two very similar (nearly identical) vectors and one orthogonal
        a = [1.0, 0.0, 0.0]
        b = [0.99, 0.14, 0.0]   # very similar to a
        c = [0.0, 1.0, 0.0]     # orthogonal to a

        results = [
            self._make_result("doc_a", 0.95, a),
            self._make_result("doc_b", 0.90, b),
            self._make_result("doc_c", 0.80, c),
        ]

        # With lambda=0.5 MMR should prefer diversity; doc_c should be chosen over doc_b
        selected = _cosine_mmr(results, top_k=2, lambda_val=0.5)
        assert len(selected) == 2
        ids = {r["metadata"]["doc_id"] for r in selected}
        # doc_a is always first (highest score); doc_c should beat doc_b due to diversity
        assert "doc_a" in ids
        assert "doc_c" in ids

    def test_top_k_respected(self):
        from app.agents.financial_rag_tool import _cosine_mmr

        results = [
            self._make_result(str(i), 1.0 - i * 0.1, [float(i), 0.0, 0.0])
            for i in range(10)
        ]
        selected = _cosine_mmr(results, top_k=3, lambda_val=0.7)
        assert len(selected) == 3


# ══════════════════════════════════════════════════════════════════════════════
# T8 — _mmr_filter_with_strategy returns "cosine" when _chunk_vec present
# ══════════════════════════════════════════════════════════════════════════════

class TestMMRFilterStrategy:

    def _base_result(self, doc_id: str, score: float, vec: list[float] | None = None) -> dict:
        r = {
            "title": f"T{doc_id}", "source_type": "doc", "source": "x",
            "published_at": "2025-01-01", "chunk": f"chunk {doc_id}",
            "score": score,
            "score_detail": {"combined_score": score, "vector_score": 0.0,
                             "keyword_score": score, "source_boost": 0.0, "recency_boost": 0.0},
            "search_mode_used": "keyword",
            "metadata": {
                "doc_id": doc_id, "source_level": "general",
                "symbol": "", "market": "", "url": "",
                "page": None, "page_start": None, "page_end": None,
                "authority_score": 0.3, "verified": False,
                "report_year": None, "report_type": "", "search_mode_used": "keyword",
            },
        }
        if vec is not None:
            r["_chunk_vec"] = vec
        return r

    def test_cosine_strategy_when_all_have_vecs(self):
        from app.agents.financial_rag_tool import _mmr_filter_with_strategy

        # 6 results, each with distinct chunk_vec, top_k=3 → triggers cosine MMR
        results = [
            self._base_result(str(i), 1.0 - i * 0.05, [float(i + 1), 0.0, 0.0])
            for i in range(6)
        ]
        filtered, strategy = _mmr_filter_with_strategy(results, top_k=3)
        assert strategy == "cosine"
        assert len(filtered) == 3
        # _chunk_vec should be stripped from output
        for r in filtered:
            assert "_chunk_vec" not in r

    def test_per_doc_cap_strategy_when_no_vecs(self):
        from app.agents.financial_rag_tool import _mmr_filter_with_strategy

        results = [
            self._base_result(str(i % 2), 1.0 - i * 0.05)   # 2 docs, no _chunk_vec
            for i in range(8)
        ]
        filtered, strategy = _mmr_filter_with_strategy(results, top_k=5)
        assert strategy == "per_doc_cap"
        # Each doc should appear at most rag_mmr_max_per_doc=2 times
        from collections import Counter
        counts = Counter(r["metadata"]["doc_id"] for r in filtered)
        for cnt in counts.values():
            assert cnt <= 2

    def test_disabled_when_mmr_not_enabled(self):
        from app.agents.financial_rag_tool import _mmr_filter_with_strategy

        results = [self._base_result(str(i), 1.0 - i * 0.1) for i in range(4)]
        with patch("app.agents.financial_rag_tool._cfg_bool", return_value=False):
            filtered, strategy = _mmr_filter_with_strategy(results, top_k=3)
        assert strategy == "disabled"
        assert len(filtered) == 3


# ══════════════════════════════════════════════════════════════════════════════
# T9 — backward-compat: _mmr_filter still works as wrapper
# ══════════════════════════════════════════════════════════════════════════════

class TestMMRFilterBackwardCompat:

    def test_mmr_filter_returns_list(self):
        from app.agents.financial_rag_tool import _mmr_filter

        results = [
            {
                "title": f"T{i}", "source_type": "doc", "source": "x",
                "published_at": "2025-01-01", "chunk": f"chunk {i}",
                "score": 1.0 - i * 0.1,
                "score_detail": {
                    "combined_score": 1.0 - i * 0.1,
                    "vector_score": 0.0, "keyword_score": 1.0 - i * 0.1,
                    "source_boost": 0.0, "recency_boost": 0.0,
                },
                "search_mode_used": "keyword",
                "metadata": {
                    "doc_id": str(i % 3), "source_level": "general",
                    "symbol": "", "market": "", "url": "",
                    "page": None, "page_start": None, "page_end": None,
                    "authority_score": 0.3, "verified": False,
                    "report_year": None, "report_type": "", "search_mode_used": "keyword",
                },
            }
            for i in range(8)
        ]
        filtered = _mmr_filter(results, 5)
        assert isinstance(filtered, list)
        assert len(filtered) <= 5


# ══════════════════════════════════════════════════════════════════════════════
# T10 — financial_rag_search diagnostics include Phase 2D.5 fields
# ══════════════════════════════════════════════════════════════════════════════

class TestEnhancedDiagnostics:

    @pytest.mark.asyncio
    async def test_diagnostics_have_phase2d5_fields(self):
        from app.agents.financial_rag_tool import financial_rag_search

        row = SimpleNamespace(
            chunk_id=str(uuid.uuid4()),
            chunk_text="Apple services revenue grew 14 percent year-over-year.",
            chunk_index=0,
            chunk_symbol="AAPL",
            chunk_market="US",
            chunk_metadata={},
            embedding_model=None,
            doc_id=str(uuid.uuid4()),
            title="Apple Annual Report",
            source_type="annual_report",
            source="SEC",
            published_at="2025-10-30",
            url="https://www.sec.gov/Archives/edgar/data/320193/0000320193-25.htm",
            doc_metadata={},
            vector_score=0.85,
            keyword_raw=5.0,
        )
        mr = MagicMock()
        mr.fetchall.return_value = [row]

        mock_db = AsyncMock()
        mock_db.execute.return_value = mr

        result = await financial_rag_search(
            "Apple services revenue", mock_db, search_mode="keyword"
        )

        assert result["ok"] is True
        diag = result["diagnostics"]

        # Phase 2D.5 required fields
        assert "mmr_strategy"                   in diag
        assert "score_weights"                  in diag
        assert "embedding_coverage_in_candidates" in diag
        assert "official_source_ratio"          in diag

        # score_weights should have all four components
        sw = diag["score_weights"]
        assert "vector"   in sw
        assert "keyword"  in sw
        assert "source"   in sw
        assert "recency"  in sw

        # mmr_strategy should be a string
        assert isinstance(diag["mmr_strategy"], str)

        # coverage / ratio should be floats in [0, 1]
        assert 0.0 <= diag["embedding_coverage_in_candidates"] <= 1.0
        assert 0.0 <= diag["official_source_ratio"] <= 1.0

    @pytest.mark.asyncio
    async def test_official_source_ratio_nonzero_for_sec_docs(self):
        from app.agents.financial_rag_tool import financial_rag_search

        row = SimpleNamespace(
            chunk_id=str(uuid.uuid4()),
            chunk_text="Apple quarterly earnings report.",
            chunk_index=0,
            chunk_symbol="AAPL",
            chunk_market="US",
            chunk_metadata={},
            embedding_model=None,
            doc_id=str(uuid.uuid4()),
            title="Apple 10-K",
            source_type="annual_report",
            source="SEC",
            published_at="2025-10-30",
            url="https://www.sec.gov/Archives/data/aapl/10k.htm",
            doc_metadata={},
            vector_score=0.9,
            keyword_raw=8.0,
        )
        mr = MagicMock()
        mr.fetchall.return_value = [row]

        mock_db = AsyncMock()
        mock_db.execute.return_value = mr

        result = await financial_rag_search(
            "Apple earnings", mock_db, search_mode="keyword"
        )

        assert result["ok"] is True
        # SEC URL → official_exchange → official_source_ratio > 0
        assert result["diagnostics"]["official_source_ratio"] > 0.0


# ══════════════════════════════════════════════════════════════════════════════
# T11 — run_rag_eval Recall@k == 1.0 on all 25 eval cases (mock DB)
# ══════════════════════════════════════════════════════════════════════════════

class TestRunRagEval:

    @pytest.mark.asyncio
    async def test_recall_at_k_all_cases(self):
        from app.agents.rag_eval_runner import run_rag_eval

        result = await run_rag_eval(top_k=5, search_mode="keyword")

        assert result["ok"] is True, f"eval errors: {result['errors']}"
        assert result["cases_total"] >= 25, (
            f"Expected ≥25 eval cases, got {result['cases_total']}"
        )
        assert result["cases_failed"] == 0, (
            f"Failed cases: {[c for c in result['per_case'] if not c['ok']]}"
        )
        assert result["recall_at_k"] == 1.0, (
            f"recall_at_k={result['recall_at_k']} < 1.0; "
            f"failed cases: {[c['id'] for c in result['per_case'] if c['recall_at_k'] < 1.0]}"
        )

    @pytest.mark.asyncio
    async def test_mrr_above_threshold(self):
        from app.agents.rag_eval_runner import run_rag_eval

        result = await run_rag_eval(top_k=5, search_mode="keyword")

        # With mock DB returning the exact eval doc, MRR should be 1.0
        assert result["mrr"] >= 0.9, f"MRR too low: {result['mrr']}"

    @pytest.mark.asyncio
    async def test_per_case_breakdown_present(self):
        from app.agents.rag_eval_runner import run_rag_eval

        result = await run_rag_eval(top_k=3, search_mode="keyword")

        assert "per_case" in result
        for c in result["per_case"]:
            assert "id"          in c
            assert "recall_at_k" in c
            assert "rr"          in c
            assert "ndcg_at_k"   in c

    @pytest.mark.asyncio
    async def test_ndcg_at_k_is_float(self):
        from app.agents.rag_eval_runner import run_rag_eval

        result = await run_rag_eval(top_k=5, search_mode="keyword")

        assert isinstance(result["ndcg_at_k"], float)
        assert 0.0 <= result["ndcg_at_k"] <= 1.0
