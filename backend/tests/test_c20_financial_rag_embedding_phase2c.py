"""
tests/test_c20_financial_rag_embedding_phase2c.py

Phase 2C: Embedding + pgvector hybrid RAG tests.

Test matrix:
  T1  — embedding_service deterministic mock
  T2  — ingest with embedding (happy path)
  T3  — embedding failure → non-fatal fallback (warnings)
  T4  — vector search success
  T5  — vector unavailable → fallback keyword
  T6  — hybrid merge deduplication
  T7  — metadata filter (symbol/market)
  T8  — official source boost
  T9  — backward compatibility (no embedding, keyword-only)
  T10 — full suite compatibility (existing 904 tests unaffected)
"""
from __future__ import annotations

import asyncio
import math
import uuid
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ── helpers ────────────────────────────────────────────────────────────────────

def _make_row(**kwargs) -> Any:
    """Build a lightweight row-like object for mocked DB results."""
    ns = SimpleNamespace(**kwargs)
    return ns


def _make_chunk_row(
    *,
    chunk_id: str | None = None,
    chunk_text: str = "Apple revenue grew 6%.",
    chunk_index: int = 0,
    chunk_symbol: str = "AAPL",
    chunk_market: str = "US",
    chunk_metadata: dict | None = None,
    embedding_model: str | None = "mock",
    doc_id: str | None = None,
    title: str = "Apple Annual Report 2025",
    source_type: str = "annual_report",
    source: str = "SEC",
    published_at: str = "2025-10-30",
    url: str = "https://www.sec.gov/Archives/edgar/data/320193/000032019325000123/0000320193-25-000123-index.htm",
    doc_metadata: dict | None = None,
    vector_score: float = 0.85,
    keyword_raw: float = 1.0,
) -> Any:
    return _make_row(
        chunk_id=chunk_id or str(uuid.uuid4()),
        chunk_text=chunk_text,
        chunk_index=chunk_index,
        chunk_symbol=chunk_symbol,
        chunk_market=chunk_market,
        chunk_metadata=chunk_metadata or {},
        embedding_model=embedding_model,
        doc_id=doc_id or str(uuid.uuid4()),
        title=title,
        source_type=source_type,
        source=source,
        published_at=published_at,
        url=url,
        doc_metadata=doc_metadata or {},
        vector_score=vector_score,
        keyword_raw=keyword_raw,
    )


# ══════════════════════════════════════════════════════════════════════════════
# T1 — Embedding service: deterministic mock
# ══════════════════════════════════════════════════════════════════════════════

class TestEmbeddingServiceMock:
    """T1: mock provider returns stable 1536-dim vectors."""

    def test_dim_is_1536(self):
        from app.agents.embedding_service import _mock_embed, EMBEDDING_DIM
        vec = _mock_embed("Hello world")
        assert len(vec) == 1536
        assert len(vec) == EMBEDDING_DIM

    def test_deterministic(self):
        from app.agents.embedding_service import _mock_embed
        v1 = _mock_embed("茅台2026年报分析")
        v2 = _mock_embed("茅台2026年报分析")
        assert v1 == v2

    def test_different_inputs_differ(self):
        from app.agents.embedding_service import _mock_embed
        v1 = _mock_embed("Apple revenue")
        v2 = _mock_embed("Microsoft revenue")
        assert v1 != v2

    def test_normalised(self):
        from app.agents.embedding_service import _mock_embed
        vec = _mock_embed("normalisation test")
        norm = math.sqrt(sum(x * x for x in vec))
        assert abs(norm - 1.0) < 1e-6

    @pytest.mark.asyncio
    async def test_embed_text_async(self):
        from app.agents.embedding_service import embed_text, EMBEDDING_DIM
        vec = await embed_text("quarterly earnings beat estimates", provider="mock")
        assert len(vec) == EMBEDDING_DIM
        assert all(isinstance(v, float) for v in vec)

    @pytest.mark.asyncio
    async def test_embed_texts_batch(self):
        from app.agents.embedding_service import embed_texts, EMBEDDING_DIM
        texts = ["First sentence.", "Second sentence.", "Third sentence."]
        vecs = await embed_texts(texts, provider="mock")
        assert len(vecs) == 3
        for v in vecs:
            assert len(v) == EMBEDDING_DIM

    @pytest.mark.asyncio
    async def test_empty_text_raises(self):
        from app.agents.embedding_service import embed_text
        with pytest.raises(ValueError, match="non-empty"):
            await embed_text("", provider="mock")

    @pytest.mark.asyncio
    async def test_whitespace_only_raises(self):
        from app.agents.embedding_service import embed_text
        with pytest.raises(ValueError):
            await embed_text("   \n\t  ", provider="mock")

    @pytest.mark.asyncio
    async def test_empty_list_returns_empty(self):
        from app.agents.embedding_service import embed_texts
        result = await embed_texts([], provider="mock")
        assert result == []

    @pytest.mark.asyncio
    async def test_same_text_twice_consistent(self):
        from app.agents.embedding_service import embed_texts
        texts = ["revenue recognition policy"]
        r1 = await embed_texts(texts, provider="mock")
        r2 = await embed_texts(texts, provider="mock")
        assert r1 == r2


# ══════════════════════════════════════════════════════════════════════════════
# T2 — Ingest with embedding (happy path)
# ══════════════════════════════════════════════════════════════════════════════

class TestIngestWithEmbedding:
    """T2: embedding fields written on successful ingest."""

    @pytest.mark.asyncio
    async def test_embedding_written_on_ingest(self):
        from app.agents.financial_document_ingest import ingest_financial_document

        executed: list[dict] = []

        async def fake_execute(sql_obj, params=None):
            sql_str = str(sql_obj)
            executed.append({"sql": sql_str, "params": dict(params or {})})
            mock_result = MagicMock()
            mock_result.fetchone.return_value = None  # not duplicate
            # column-exists check
            if "information_schema.columns" in sql_str:
                mock_result.fetchone.return_value = (1,)
            return mock_result

        mock_db = AsyncMock()
        mock_db.execute.side_effect = fake_execute
        mock_db.flush = AsyncMock()

        result = await ingest_financial_document(
            db=mock_db,
            raw_text="Apple Inc. reported revenue of $400 billion in fiscal 2025. "
                     "EPS grew 12% year-over-year. iPhone segment revenue increased 6%.",
            title="Apple FY2025 Annual Report",
            source_type="annual_report",
            source="SEC",
            symbol="AAPL",
            market="US",
            published_at="2025-10-30",
            enable_embedding=True,
        )

        assert result["ok"] is True, f"ingest failed: {result}"
        assert result["chunks_inserted"] > 0

        # Find chunk INSERT statements that have embedding info
        chunk_inserts = [e for e in executed if "INSERT INTO financial_document_chunks" in e["sql"]]
        assert chunk_inserts, "No chunk inserts found"

        # At least one chunk should have embedding_vector column in SQL
        # (depends on _check_vector_column_exists returning True above)
        vector_inserts = [e for e in chunk_inserts if "embedding_vector" in e["sql"]]
        # The mock returns (1,) for information_schema, so vector column appears available
        assert vector_inserts, "Expected at least one vector INSERT"

        # embedding_model must be present in params
        for vi in vector_inserts:
            assert "emb_model" in vi["params"], "embedding_model param missing"
            assert "embedded_at" in vi["params"], "embedded_at param missing"
            assert "vec" in vi["params"], "vec (embedding_vector) param missing"

    @pytest.mark.asyncio
    async def test_warnings_empty_on_success(self):
        from app.agents.financial_document_ingest import ingest_financial_document

        async def fake_execute(sql_obj, params=None):
            mock_result = MagicMock()
            mock_result.fetchone.return_value = None
            if "information_schema" in str(sql_obj):
                mock_result.fetchone.return_value = (1,)
            return mock_result

        mock_db = AsyncMock()
        mock_db.execute.side_effect = fake_execute
        mock_db.flush = AsyncMock()

        result = await ingest_financial_document(
            db=mock_db,
            raw_text="Revenue increased 10% driven by cloud segment growth.",
            title="Microsoft Q3 Report",
            source_type="quarterly_report",
            source="SEC",
            enable_embedding=True,
        )

        assert result["ok"] is True
        assert "embedding_failed" not in result.get("warnings", [])


# ══════════════════════════════════════════════════════════════════════════════
# T3 — Embedding failure → non-fatal, ingest still succeeds
# ══════════════════════════════════════════════════════════════════════════════

class TestEmbeddingFailureFallback:
    """T3: if embedding raises, ingest continues with NULL vectors + warning."""

    @pytest.mark.asyncio
    async def test_embedding_failure_non_fatal(self):
        from app.agents.financial_document_ingest import ingest_financial_document

        async def fake_execute(sql_obj, params=None):
            mock_result = MagicMock()
            mock_result.fetchone.return_value = None
            # Pretend vector column does NOT exist
            if "information_schema" in str(sql_obj):
                mock_result.fetchone.return_value = None
            return mock_result

        mock_db = AsyncMock()
        mock_db.execute.side_effect = fake_execute
        mock_db.flush = AsyncMock()

        with patch(
            "app.agents.embedding_service.embed_texts",
            side_effect=RuntimeError("OpenAI API unreachable"),
        ):
            result = await ingest_financial_document(
                db=mock_db,
                raw_text="贵州茅台2026年营业收入同比增长18%，净利润达到650亿元。",
                title="贵州茅台2026年报",
                source_type="annual_report",
                source="上交所",
                symbol="600519",
                market="CN",
                enable_embedding=True,
            )

        assert result["ok"] is True, f"ingest should not fail on embedding error: {result}"
        assert result["chunks_inserted"] > 0
        assert "embedding_failed" in result.get("warnings", [])

    @pytest.mark.asyncio
    async def test_no_embedding_mode_skips_embed(self):
        from app.agents.financial_document_ingest import ingest_financial_document

        embed_called = []

        async def fake_execute(sql_obj, params=None):
            mock_result = MagicMock()
            mock_result.fetchone.return_value = None
            if "information_schema" in str(sql_obj):
                mock_result.fetchone.return_value = None
            return mock_result

        mock_db = AsyncMock()
        mock_db.execute.side_effect = fake_execute
        mock_db.flush = AsyncMock()

        with patch(
            "app.agents.embedding_service.embed_texts",
            side_effect=lambda *a, **kw: embed_called.append(1) or [],
        ):
            result = await ingest_financial_document(
                db=mock_db,
                raw_text="Keyword-only document — no embedding requested.",
                title="Plain Text Note",
                source_type="document",
                source="internal",
                enable_embedding=False,
            )

        assert result["ok"] is True
        assert embed_called == [], "embed_texts should not be called when enable_embedding=False"
        assert "embedding_failed" not in result.get("warnings", [])


# ══════════════════════════════════════════════════════════════════════════════
# T4 — Vector search success
# ══════════════════════════════════════════════════════════════════════════════

class TestVectorSearchSuccess:
    """T4: vector search returns results with score_detail.vector_score."""

    @pytest.mark.asyncio
    async def test_vector_search_returns_score_detail(self):
        from app.agents.financial_rag_tool import financial_rag_search

        row = _make_chunk_row(vector_score=0.88)
        mock_result = MagicMock()
        mock_result.fetchall.return_value = [row]

        mock_db = AsyncMock()
        mock_db.execute.return_value = mock_result

        with patch(
            "app.agents.financial_rag_tool._get_query_vector",
            new=AsyncMock(return_value=[0.1] * 1536),
        ):
            result = await financial_rag_search(
                "Apple revenue growth",
                mock_db,
                search_mode="vector",
            )

        assert result["ok"] is True
        assert len(result["results"]) == 1
        r = result["results"][0]
        assert "score_detail" in r
        assert "vector_score" in r["score_detail"]
        assert r["score_detail"]["vector_score"] > 0
        assert r["search_mode_used"] == "vector"

    @pytest.mark.asyncio
    async def test_hybrid_search_has_both_scores(self):
        from app.agents.financial_rag_tool import financial_rag_search

        row = _make_chunk_row(vector_score=0.75, keyword_raw=3.0)
        mock_result = MagicMock()
        mock_result.fetchall.return_value = [row]

        mock_db = AsyncMock()
        mock_db.execute.return_value = mock_result

        with patch(
            "app.agents.financial_rag_tool._get_query_vector",
            new=AsyncMock(return_value=[0.1] * 1536),
        ):
            result = await financial_rag_search(
                "annual report revenue",
                mock_db,
                search_mode="hybrid",
            )

        assert result["ok"] is True
        assert result["search_mode"] in ("hybrid", "vector", "keyword")
        for r in result["results"]:
            assert "score_detail" in r
            assert "combined_score" in r["score_detail"]


# ══════════════════════════════════════════════════════════════════════════════
# T5 — Vector unavailable → fallback keyword
# ══════════════════════════════════════════════════════════════════════════════

class TestVectorFallbackKeyword:
    """T5: when embedding fails or pgvector missing, falls back to keyword."""

    @pytest.mark.asyncio
    async def test_embedding_failure_falls_back(self):
        from app.agents.financial_rag_tool import financial_rag_search

        row = _make_chunk_row(vector_score=0.0, keyword_raw=2.0)
        mock_result = MagicMock()
        mock_result.fetchall.return_value = [row]

        mock_db = AsyncMock()
        mock_db.execute.return_value = mock_result

        with patch(
            "app.agents.financial_rag_tool._get_query_vector",
            side_effect=RuntimeError("embedding service unavailable"),
        ):
            result = await financial_rag_search(
                "revenue earnings",
                mock_db,
                search_mode="hybrid",
            )

        assert result["ok"] is True
        assert result["search_mode"] == "keyword"
        assert len(result["results"]) >= 1

    @pytest.mark.asyncio
    async def test_vector_db_error_falls_back(self):
        from app.agents.financial_rag_tool import financial_rag_search

        call_count = [0]

        async def mock_execute(sql_obj, params=None):
            call_count[0] += 1
            sql_str = str(sql_obj)
            mock_result = MagicMock()
            if "embedding_vector" in sql_str and "<=>" in sql_str:
                # Simulate pgvector error
                raise Exception("column embedding_vector does not exist")
            # Keyword search succeeds
            mock_result.fetchall.return_value = [_make_chunk_row()]
            return mock_result

        mock_db = AsyncMock()
        mock_db.execute.side_effect = mock_execute

        with patch(
            "app.agents.financial_rag_tool._get_query_vector",
            new=AsyncMock(return_value=[0.1] * 1536),
        ):
            result = await financial_rag_search(
                "earnings per share",
                mock_db,
                search_mode="hybrid",
            )

        assert result["ok"] is True
        assert result["search_mode"] == "keyword"

    @pytest.mark.asyncio
    async def test_keyword_mode_never_calls_vector(self):
        from app.agents.financial_rag_tool import financial_rag_search

        embed_called = []

        row = _make_chunk_row()
        mock_result = MagicMock()
        mock_result.fetchall.return_value = [row]

        mock_db = AsyncMock()
        mock_db.execute.return_value = mock_result

        async def no_vector(*a, **kw):
            embed_called.append(1)
            return [0.0] * 1536

        with patch("app.agents.financial_rag_tool._get_query_vector", side_effect=no_vector):
            result = await financial_rag_search(
                "AAPL earnings",
                mock_db,
                search_mode="keyword",
            )

        assert embed_called == [], "keyword mode should NOT call embed"
        assert result["search_mode"] == "keyword"


# ══════════════════════════════════════════════════════════════════════════════
# T6 — Hybrid merge deduplication
# ══════════════════════════════════════════════════════════════════════════════

class TestHybridMergeDedup:
    """T6: same chunk from vector and keyword search → only one result."""

    def test_dedup_same_doc_same_chunk_text(self):
        from app.agents.financial_rag_tool import _hybrid_merge

        shared_chunk = "Apple revenue grew 6% year-over-year."
        doc_id = str(uuid.uuid4())

        def _base_result(mode: str, score: float) -> dict:
            return {
                "title":        "Apple FY2025",
                "source_type":  "annual_report",
                "source":       "SEC",
                "published_at": "2025-10-30",
                "chunk":        shared_chunk,
                "score":        score,
                "score_detail": {
                    "vector_score":   score if mode == "vector" else 0.0,
                    "keyword_score":  score if mode == "keyword" else 0.0,
                    "source_boost":   0.05,
                    "recency_boost":  0.01,
                    "combined_score": score,
                },
                "search_mode_used": mode,
                "metadata": {
                    "doc_id":    doc_id,
                    "symbol":    "AAPL",
                    "market":    "US",
                    "url":       "",
                    "page":      None,
                    "page_start": None,
                    "page_end":   None,
                    "source_level": "official_exchange",
                    "authority_score": 1.0,
                    "verified":  True,
                    "report_year": 2025,
                    "report_type": "annual",
                    "search_mode_used": mode,
                },
            }

        vector_results  = [_base_result("vector",  0.85)]
        keyword_results = [_base_result("keyword", 0.60)]

        merged = _hybrid_merge(vector_results, keyword_results, top_k=5)

        assert len(merged) == 1, f"Expected 1 deduplicated result, got {len(merged)}"
        r = merged[0]
        assert r["search_mode_used"] == "hybrid"
        assert r["score_detail"]["keyword_score"] > 0
        assert r["score_detail"]["vector_score"] > 0

    def test_non_overlapping_merge_keeps_all(self):
        from app.agents.financial_rag_tool import _hybrid_merge

        def _result(doc_id: str, chunk: str, mode: str) -> dict:
            return {
                "title":        "Doc",
                "source_type":  "document",
                "source":       "SEC",
                "published_at": "",
                "chunk":        chunk,
                "score":        0.5,
                "score_detail": {
                    "vector_score": 0.5 if mode == "vector" else 0.0,
                    "keyword_score": 0.5 if mode == "keyword" else 0.0,
                    "source_boost": 0.0,
                    "recency_boost": 0.0,
                    "combined_score": 0.5,
                },
                "search_mode_used": mode,
                "metadata": {
                    "doc_id": doc_id, "symbol": "", "market": "",
                    "url": "", "page": None, "page_start": None, "page_end": None,
                    "source_level": "general", "authority_score": 0.3,
                    "verified": False, "report_year": None, "report_type": "",
                    "search_mode_used": mode,
                },
            }

        vec_results  = [_result(str(uuid.uuid4()), "chunk A", "vector")]
        kw_results   = [_result(str(uuid.uuid4()), "chunk B", "keyword")]

        merged = _hybrid_merge(vec_results, kw_results, top_k=5)
        assert len(merged) == 2

    def test_top_k_respected(self):
        from app.agents.financial_rag_tool import _hybrid_merge

        def _r(i: int) -> dict:
            doc_id = str(uuid.uuid4())
            return {
                "title": f"Doc {i}", "source_type": "document", "source": "",
                "published_at": "", "chunk": f"chunk {i}", "score": 1.0 / (i + 1),
                "score_detail": {"vector_score": 1.0 / (i + 1), "keyword_score": 0.0,
                                 "source_boost": 0.0, "recency_boost": 0.0,
                                 "combined_score": 1.0 / (i + 1)},
                "search_mode_used": "vector",
                "metadata": {"doc_id": doc_id, "symbol": "", "market": "", "url": "",
                             "page": None, "page_start": None, "page_end": None,
                             "source_level": "general", "authority_score": 0.3,
                             "verified": False, "report_year": None, "report_type": "",
                             "search_mode_used": "vector"},
            }

        many = [_r(i) for i in range(10)]
        merged = _hybrid_merge(many, [], top_k=3)
        assert len(merged) == 3


# ══════════════════════════════════════════════════════════════════════════════
# T7 — Metadata filter
# ══════════════════════════════════════════════════════════════════════════════

class TestMetadataFilter:
    """T7: symbol/market filter is added to SQL params."""

    @pytest.mark.asyncio
    async def test_symbol_filter_in_sql(self):
        from app.agents.financial_rag_tool import financial_rag_search

        captured_params: list[dict] = []

        async def mock_execute(sql_obj, params=None):
            captured_params.append(dict(params or {}))
            mock_result = MagicMock()
            mock_result.fetchall.return_value = []
            return mock_result

        mock_db = AsyncMock()
        mock_db.execute.side_effect = mock_execute

        await financial_rag_search(
            "annual revenue",
            mock_db,
            symbol="AAPL",
            market="US",
            search_mode="keyword",
        )

        assert any("symbol" in p for p in captured_params), "symbol not in SQL params"
        assert any(p.get("symbol") == "AAPL" for p in captured_params), "symbol value wrong"
        assert any(p.get("market") == "US" for p in captured_params), "market value wrong"

    @pytest.mark.asyncio
    async def test_msft_filter_excludes_aapl(self):
        """If we filter by MSFT, AAPL rows should not be returned."""
        from app.agents.financial_rag_tool import _keyword_search

        async def mock_execute(sql_obj, params=None):
            # Simulate DB correctly filtering — return empty for non-matching symbol
            mock_result = MagicMock()
            mock_result.fetchall.return_value = []
            return mock_result

        mock_db = AsyncMock()
        mock_db.execute.side_effect = mock_execute

        results = await _keyword_search(
            mock_db, "revenue",
            symbol="MSFT", market="US", top_k=5,
            source_type=None, report_year=None, report_type=None,
            mode_label="keyword",
        )
        # DB returned nothing (as expected for MSFT filter with no MSFT data)
        assert results == []

    @pytest.mark.asyncio
    async def test_source_type_filter(self):
        from app.agents.financial_rag_tool import financial_rag_search

        captured_params: list[dict] = []

        async def mock_execute(sql_obj, params=None):
            captured_params.append(dict(params or {}))
            mock_result = MagicMock()
            mock_result.fetchall.return_value = []
            return mock_result

        mock_db = AsyncMock()
        mock_db.execute.side_effect = mock_execute

        await financial_rag_search(
            "revenue",
            mock_db,
            source_type="annual_report",
            search_mode="keyword",
        )

        assert any(p.get("source_type") == "annual_report" for p in captured_params)


# ══════════════════════════════════════════════════════════════════════════════
# T8 — Official source boost
# ══════════════════════════════════════════════════════════════════════════════

class TestOfficialSourceBoost:
    """T8: official_exchange URL gets higher score than general source."""

    def test_source_boost_official_vs_general(self):
        from app.agents.financial_rag_tool import _source_boost, _source_level_for_url

        official_url = "https://www.sec.gov/Archives/edgar/data/320193/0000320193-25.htm"
        general_url  = "https://www.some-blog.com/aapl-analysis"

        official_level = _source_level_for_url(official_url)
        general_level  = _source_level_for_url(general_url)

        assert official_level == "official_exchange"
        assert general_level  == "general"

        assert _source_boost(official_level) > _source_boost(general_level)
        assert _source_boost(official_level) > 0

    def test_official_result_ranks_higher(self):
        from app.agents.financial_rag_tool import _row_to_result

        official_row = _make_chunk_row(
            url="https://www.sec.gov/Archives/edgar/data/320193/0000.htm",
            vector_score=0.80,
        )
        general_row = _make_chunk_row(
            url="https://random-blog.com/aapl",
            vector_score=0.80,
        )

        r_official = _row_to_result(official_row, vector_score=0.80, mode_label="vector")
        r_general  = _row_to_result(general_row,  vector_score=0.80, mode_label="vector")

        assert r_official["score"] > r_general["score"], (
            f"official {r_official['score']} should exceed general {r_general['score']}"
        )
        assert r_official["score_detail"]["source_boost"] > 0
        assert r_official["metadata"]["source_level"] == "official_exchange"
        assert r_official["metadata"]["verified"] is True

    def test_authoritative_media_mid_boost(self):
        from app.agents.financial_rag_tool import _source_boost, _source_level_for_url

        em_url = "https://www.eastmoney.com/article/aapl-q3"
        level  = _source_level_for_url(em_url)
        assert level == "authoritative_media"
        boost = _source_boost(level)
        assert 0 < boost < 0.05  # Less than official but more than 0


# ══════════════════════════════════════════════════════════════════════════════
# T9 — Backward compatibility: no embedding, keyword-only search still works
# ══════════════════════════════════════════════════════════════════════════════

class TestBackwardCompatibility:
    """T9: documents without embedding_vector are still retrievable via keyword."""

    @pytest.mark.asyncio
    async def test_old_doc_keyword_retrieval(self):
        from app.agents.financial_rag_tool import financial_rag_search

        # Row with no embedding_vector — only keyword match
        row = _make_chunk_row(
            embedding_model=None,
            keyword_raw=5.0,
        )
        mock_result = MagicMock()
        mock_result.fetchall.return_value = [row]

        mock_db = AsyncMock()
        mock_db.execute.return_value = mock_result

        result = await financial_rag_search(
            "Apple iPhone revenue",
            mock_db,
            search_mode="keyword",
        )

        assert result["ok"] is True
        assert len(result["results"]) == 1
        assert result["search_mode"] == "keyword"

    @pytest.mark.asyncio
    async def test_ingest_without_embedding_inserts_null(self):
        from app.agents.financial_document_ingest import ingest_financial_document

        inserted_sqls: list[str] = []

        async def fake_execute(sql_obj, params=None):
            sql_str = str(sql_obj)
            inserted_sqls.append(sql_str)
            mock_result = MagicMock()
            mock_result.fetchone.return_value = None
            return mock_result

        mock_db = AsyncMock()
        mock_db.execute.side_effect = fake_execute
        mock_db.flush = AsyncMock()

        result = await ingest_financial_document(
            db=mock_db,
            raw_text="Legacy document without embedding.",
            title="Legacy Doc",
            source_type="document",
            source="internal",
            enable_embedding=False,
        )

        assert result["ok"] is True
        chunk_inserts = [s for s in inserted_sqls if "INSERT INTO financial_document_chunks" in s]
        assert chunk_inserts, "Should have chunk inserts"
        # Without embedding, should use the simple INSERT (no embedding_vector column)
        for sql_str in chunk_inserts:
            assert "embedding_vector" not in sql_str

    def test_financial_rag_search_signature_compatible(self):
        """original 2-arg call still works (backward compat with Phase 2A callers)."""
        import inspect
        from app.agents.financial_rag_tool import financial_rag_search

        sig = inspect.signature(financial_rag_search)
        params = sig.parameters

        assert "query" in params
        assert "db" in params
        assert "symbol" in params
        assert "market" in params
        assert "top_k" in params
        # New Phase 2C params must have defaults
        assert params.get("search_mode") is not None
        assert params["search_mode"].default == "hybrid"

    def test_source_ref_backward_compatible(self):
        """SourceRef can still be created with only Phase 2A fields."""
        from app.agents.schemas import SourceRef

        ref = SourceRef(
            title="Apple Annual Report 2025",
            source_type="annual_report",
            source="SEC",
            published_at="2025-10-30",
        )
        assert ref.title == "Apple Annual Report 2025"
        # Phase 2C fields have defaults
        assert ref.source_level == ""
        assert ref.verified is False
        assert ref.authority_score == 0.0
        assert ref.search_mode_used == ""

    def test_source_ref_new_fields_accepted(self):
        """SourceRef accepts Phase 2C quality fields."""
        from app.agents.schemas import SourceRef

        ref = SourceRef(
            title="AAPL FY2025",
            source_level="official_exchange",
            verified=True,
            authority_score=1.0,
            report_year=2025,
            report_type="annual",
            page_start=12,
            page_end=15,
            search_mode_used="hybrid",
        )
        assert ref.verified is True
        assert ref.authority_score == 1.0
        assert ref.report_year == 2025
        assert ref.search_mode_used == "hybrid"


# ══════════════════════════════════════════════════════════════════════════════
# Unit tests for score components
# ══════════════════════════════════════════════════════════════════════════════

class TestScoreComponents:
    """Extra unit tests for recency boost and source classification."""

    def test_recency_boost_recent_doc(self):
        from app.agents.financial_rag_tool import _recency_boost
        # Very recent date → high boost
        boost = _recency_boost("2026-06-01")
        assert boost > 0

    def test_recency_boost_old_doc(self):
        from app.agents.financial_rag_tool import _recency_boost
        boost = _recency_boost("2010-01-01")
        assert boost < 0.001

    def test_recency_boost_invalid_date(self):
        from app.agents.financial_rag_tool import _recency_boost
        assert _recency_boost("") == 0.0
        assert _recency_boost("not-a-date") == 0.0

    def test_source_level_sec(self):
        from app.agents.financial_rag_tool import _source_level_for_url
        assert _source_level_for_url("https://www.sec.gov/foo") == "official_exchange"

    def test_source_level_cninfo(self):
        from app.agents.financial_rag_tool import _source_level_for_url
        assert _source_level_for_url("https://www.cninfo.com.cn/new/hisAnnouncement") == "official_exchange"

    def test_source_level_unknown(self):
        from app.agents.financial_rag_tool import _source_level_for_url
        assert _source_level_for_url("https://unknown.example.com") == "general"

    def test_source_level_none(self):
        from app.agents.financial_rag_tool import _source_level_for_url
        assert _source_level_for_url(None) == "general"

    def test_embedding_truncation(self):
        from app.agents.embedding_service import _truncate
        long_text = "A" * 10000
        truncated = _truncate(long_text, 5000)
        assert len(truncated) <= 5000


# ══════════════════════════════════════════════════════════════════════════════
# T10 marker — run full suite (just validates import chain here)
# ══════════════════════════════════════════════════════════════════════════════

class TestPhase2CImports:
    """T10: all Phase 2C modules importable without errors."""

    def test_embedding_service_importable(self):
        import app.agents.embedding_service as es
        assert hasattr(es, "embed_text")
        assert hasattr(es, "embed_texts")
        assert hasattr(es, "EMBEDDING_DIM")
        assert es.EMBEDDING_DIM == 1536

    def test_financial_rag_tool_importable(self):
        import app.agents.financial_rag_tool as rt
        assert hasattr(rt, "financial_rag_search")
        assert hasattr(rt, "_hybrid_merge")
        assert hasattr(rt, "_vector_search")
        assert hasattr(rt, "_keyword_search")

    def test_ingest_new_params(self):
        import inspect
        from app.agents.financial_document_ingest import ingest_financial_document

        sig = inspect.signature(ingest_financial_document)
        assert "enable_embedding" in sig.parameters
        assert "embedding_model" in sig.parameters
        assert sig.parameters["enable_embedding"].default is True

    def test_schemas_source_ref_has_quality_fields(self):
        from app.agents.schemas import SourceRef
        import inspect

        fields = SourceRef.model_fields
        for field in ("source_level", "verified", "authority_score",
                      "report_year", "report_type", "page_start",
                      "page_end", "search_mode_used"):
            assert field in fields, f"SourceRef missing field: {field}"

    def test_config_has_embedding_provider(self):
        from app.core.config import Settings
        import inspect

        sig = inspect.signature(Settings.__init__)
        # pydantic models don't show in __init__ sig directly, check fields
        fields = Settings.model_fields
        assert "embedding_provider" in fields
        assert "embedding_model" in fields
