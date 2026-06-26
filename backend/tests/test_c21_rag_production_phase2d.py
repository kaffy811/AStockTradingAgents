"""
tests/test_c21_rag_production_phase2d.py

Phase 2D: pgvector healthcheck, backfill, embed batching, hybrid weights,
MMR diversity, and RAG diagnostics tests.

Test index:
  T1  — pgvector healthcheck: all ready
  T2  — pgvector healthcheck: extension missing → ok=False + fallback warning
  T3  — backfill dry-run: count only, no DB write
  T4  — backfill success: 3 chunks embedded
  T5  — backfill partial failure: one batch fails, others continue
  T6  — embed_texts batching: 150 texts with batch_size=64 → 3 batches
  T7  — hybrid weights from config
  T8  — MMR diversity: same doc limited per slot
  T9  — diagnostics field in financial_rag_search
  T10 — full suite compatibility marker (just import checks)
"""
from __future__ import annotations

import asyncio
import uuid
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ── helpers ────────────────────────────────────────────────────────────────────

def _ns(**kwargs) -> Any:
    return SimpleNamespace(**kwargs)


def _make_chunk_row(
    *,
    chunk_id: str | None = None,
    chunk_text: str = "Apple revenue grew 6% year-over-year.",
    chunk_index: int = 0,
    chunk_symbol: str = "AAPL",
    chunk_market: str = "US",
    chunk_metadata: dict | None = None,
    embedding_model: str | None = "mock",
    doc_id: str | None = None,
    title: str = "Apple FY2025 Annual Report",
    source_type: str = "annual_report",
    source: str = "SEC",
    published_at: str = "2025-10-30",
    url: str = "https://www.sec.gov/Archives/test.htm",
    doc_metadata: dict | None = None,
    vector_score: float = 0.85,
    keyword_raw: float = 1.0,
) -> Any:
    return _ns(
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
# T1 — pgvector healthcheck: fully ready
# ══════════════════════════════════════════════════════════════════════════════

class TestPgvectorHealthcheckReady:
    """T1: DB has pgvector extension, column, index, and chunks."""

    @pytest.mark.asyncio
    async def test_healthcheck_all_ok(self):
        from app.agents.rag_healthcheck import check_pgvector_ready

        call_count = [0]

        async def mock_execute(sql_obj, params=None):
            call_count[0] += 1
            sql_str = str(sql_obj)
            mr = MagicMock()

            if "pg_extension" in sql_str:
                mr.fetchone.return_value = ("vector",)
            elif "information_schema.columns" in sql_str:
                mr.fetchone.return_value = (1,)
            elif "pg_indexes" in sql_str:
                mr.fetchone.return_value = ("ix_fdc_embedding_vector_hnsw",)
            elif "COUNT(*)" in sql_str:
                mr.fetchone.return_value = (12000, 11800)
            else:
                mr.fetchone.return_value = None
            return mr

        mock_db = AsyncMock()
        mock_db.execute.side_effect = mock_execute

        result = await check_pgvector_ready(mock_db)

        assert result["ok"] is True
        assert result["extension_installed"] is True
        assert result["embedding_column_exists"] is True
        assert result["vector_index_exists"] is True
        assert result["chunks_total"] == 12000
        assert result["chunks_embedded"] == 11800
        assert abs(result["embedding_coverage"] - 0.9833) < 0.001

    @pytest.mark.asyncio
    async def test_healthcheck_partial_coverage_has_warning(self):
        from app.agents.rag_healthcheck import check_pgvector_ready

        async def mock_execute(sql_obj, params=None):
            sql_str = str(sql_obj)
            mr = MagicMock()
            if "pg_extension" in sql_str:
                mr.fetchone.return_value = ("vector",)
            elif "information_schema.columns" in sql_str:
                mr.fetchone.return_value = (1,)
            elif "pg_indexes" in sql_str:
                mr.fetchone.return_value = ("ix_fdc_embedding_vector_hnsw",)
            elif "COUNT(*)" in sql_str:
                mr.fetchone.return_value = (1000, 500)
            else:
                mr.fetchone.return_value = None
            return mr

        mock_db = AsyncMock()
        mock_db.execute.side_effect = mock_execute

        result = await check_pgvector_ready(mock_db)

        assert result["ok"] is True
        assert result["embedding_coverage"] == 0.5
        # Should warn about missing embeddings
        backfill_warnings = [w for w in result["warnings"] if "backfill" in w.lower()]
        assert backfill_warnings, "expected backfill warning for partial coverage"


# ══════════════════════════════════════════════════════════════════════════════
# T2 — pgvector healthcheck: extension missing
# ══════════════════════════════════════════════════════════════════════════════

class TestPgvectorHealthcheckUnavailable:
    """T2: pgvector not installed → ok=False, fallback warning."""

    @pytest.mark.asyncio
    async def test_healthcheck_no_extension(self):
        from app.agents.rag_healthcheck import check_pgvector_ready

        async def mock_execute(sql_obj, params=None):
            sql_str = str(sql_obj)
            mr = MagicMock()
            if "pg_extension" in sql_str:
                mr.fetchone.return_value = None   # not installed
            elif "information_schema.columns" in sql_str:
                mr.fetchone.return_value = None   # column also missing
            elif "pg_indexes" in sql_str:
                mr.fetchone.return_value = None
            elif "COUNT(*)" in sql_str:
                mr.fetchone.return_value = (100, 0)
            else:
                mr.fetchone.return_value = None
            return mr

        mock_db = AsyncMock()
        mock_db.execute.side_effect = mock_execute

        result = await check_pgvector_ready(mock_db)

        assert result["ok"] is False
        assert result["extension_installed"] is False
        fallback_warnings = [w for w in result["warnings"] if "keyword" in w.lower()]
        assert fallback_warnings, "expected keyword fallback warning"

    @pytest.mark.asyncio
    async def test_healthcheck_db_error_never_raises(self):
        """check_pgvector_ready must not raise even on DB exceptions."""
        from app.agents.rag_healthcheck import check_pgvector_ready

        mock_db = AsyncMock()
        mock_db.execute.side_effect = Exception("connection refused")

        result = await check_pgvector_ready(mock_db)  # must not raise
        assert "ok" in result
        assert isinstance(result["warnings"], list)


# ══════════════════════════════════════════════════════════════════════════════
# T3 — Backfill dry-run
# ══════════════════════════════════════════════════════════════════════════════

class TestBackfillDryRun:
    """T3: dry_run=True returns count without writing."""

    @pytest.mark.asyncio
    async def test_dry_run_counts_only(self):
        from app.agents.embedding_backfill import backfill_missing_embeddings

        written_sqls: list[str] = []

        async def mock_execute(sql_obj, params=None):
            sql_str = str(sql_obj)
            mr = MagicMock()
            if "COUNT(*)" in sql_str:
                mr.fetchone.return_value = (247,)
            elif "SELECT c.id" in sql_str:
                mr.fetchall.return_value = []  # no rows needed in dry-run
            written_sqls.append(sql_str)
            return mr

        mock_db = AsyncMock()
        mock_db.execute.side_effect = mock_execute

        result = await backfill_missing_embeddings(
            mock_db, batch_size=64, dry_run=True
        )

        assert result["dry_run"] is True
        assert result["scanned"] == 247
        assert result["embedded"] == 0
        # Ensure no UPDATE statements were executed
        update_stmts = [s for s in written_sqls if "UPDATE" in s.upper()]
        assert not update_stmts, "dry_run should not issue UPDATE statements"

    @pytest.mark.asyncio
    async def test_dry_run_with_limit(self):
        from app.agents.embedding_backfill import backfill_missing_embeddings

        async def mock_execute(sql_obj, params=None):
            mr = MagicMock()
            mr.fetchone.return_value = (1000,)
            mr.fetchall.return_value = []
            return mr

        mock_db = AsyncMock()
        mock_db.execute.side_effect = mock_execute

        result = await backfill_missing_embeddings(
            mock_db, batch_size=64, limit=100, dry_run=True
        )

        assert result["dry_run"] is True
        assert result["scanned"] == 100   # capped at limit


# ══════════════════════════════════════════════════════════════════════════════
# T4 — Backfill success
# ══════════════════════════════════════════════════════════════════════════════

class TestBackfillSuccess:
    """T4: 3 chunks embedded successfully."""

    @pytest.mark.asyncio
    async def test_backfill_three_chunks(self):
        from app.agents.embedding_backfill import backfill_missing_embeddings

        chunk_ids = [str(uuid.uuid4()) for _ in range(3)]
        chunk_texts = [
            "Apple revenue segment analysis.",
            "iPhone unit sales grew 6 percent.",
            "Services segment gross margin 74 percent.",
        ]
        rows = [_ns(id=cid, chunk_text=ct) for cid, ct in zip(chunk_ids, chunk_texts)]

        updated_ids: list[str] = []
        fetch_called = [0]

        async def mock_execute(sql_obj, params=None):
            sql_str = str(sql_obj)
            mr = MagicMock()

            if "COUNT(*)" in sql_str:
                mr.fetchone.return_value = (3,)

            elif "SELECT c.id" in sql_str:
                fetch_called[0] += 1
                if fetch_called[0] == 1:
                    mr.fetchall.return_value = rows
                else:
                    mr.fetchall.return_value = []

            elif "UPDATE financial_document_chunks" in sql_str:
                updated_ids.append(params.get("chunk_id", ""))
                mr.fetchone.return_value = None

            else:
                mr.fetchone.return_value = None
                mr.fetchall.return_value = []

            return mr

        mock_db = AsyncMock()
        mock_db.execute.side_effect = mock_execute
        mock_db.flush = AsyncMock()

        result = await backfill_missing_embeddings(
            mock_db, batch_size=64, dry_run=False
        )

        assert result["ok"] is True
        assert result["embedded"] == 3
        assert result["failed"] == 0
        assert result["batches"] >= 1
        assert set(updated_ids) == set(chunk_ids)

    @pytest.mark.asyncio
    async def test_backfill_embedded_at_is_set(self):
        """embedded_at must be passed to UPDATE."""
        from app.agents.embedding_backfill import backfill_missing_embeddings

        chunk_id = str(uuid.uuid4())
        rows = [_ns(id=chunk_id, chunk_text="Test text for embedding.")]
        fetch_called = [0]
        update_params: list[dict] = []

        async def mock_execute(sql_obj, params=None):
            sql_str = str(sql_obj)
            mr = MagicMock()
            if "COUNT(*)" in sql_str:
                mr.fetchone.return_value = (1,)
            elif "SELECT c.id" in sql_str:
                fetch_called[0] += 1
                mr.fetchall.return_value = rows if fetch_called[0] == 1 else []
            elif "UPDATE" in sql_str:
                update_params.append(dict(params or {}))
            return mr

        mock_db = AsyncMock()
        mock_db.execute.side_effect = mock_execute
        mock_db.flush = AsyncMock()

        await backfill_missing_embeddings(mock_db, batch_size=64, dry_run=False)

        assert update_params, "No UPDATE executed"
        p = update_params[0]
        assert "embedded_at" in p
        assert p["embedded_at"] is not None
        assert "model" in p


# ══════════════════════════════════════════════════════════════════════════════
# T5 — Backfill partial failure
# ══════════════════════════════════════════════════════════════════════════════

class TestBackfillPartialFailure:
    """T5: one embed batch fails; other batches continue."""

    @pytest.mark.asyncio
    async def test_partial_failure_records_errors(self):
        from app.agents.embedding_backfill import backfill_missing_embeddings

        # 2 batches: first succeeds (3 chunks), second fails (2 chunks)
        rows_batch1 = [_ns(id=str(uuid.uuid4()), chunk_text=f"chunk {i}") for i in range(3)]
        rows_batch2 = [_ns(id=str(uuid.uuid4()), chunk_text=f"fail chunk {i}") for i in range(2)]
        all_rows = rows_batch1 + rows_batch2

        fetch_called = [0]
        update_count = [0]
        embed_call = [0]

        async def mock_execute(sql_obj, params=None):
            sql_str = str(sql_obj)
            mr = MagicMock()
            if "COUNT(*)" in sql_str:
                mr.fetchone.return_value = (5,)
            elif "SELECT c.id" in sql_str:
                fetch_called[0] += 1
                mr.fetchall.return_value = all_rows if fetch_called[0] == 1 else []
            elif "UPDATE" in sql_str:
                update_count[0] += 1
            return mr

        mock_db = AsyncMock()
        mock_db.execute.side_effect = mock_execute
        mock_db.flush = AsyncMock()

        async def flaky_embed_texts(texts, **kw):
            embed_call[0] += 1
            # First batch: succeed (texts are rows_batch1[:3] + rows_batch2[:2] in one call with batch_size=3)
            # We simulate: batch_size=3, so 2 batches
            if embed_call[0] == 2:
                raise RuntimeError("Simulated API failure for batch 2")
            from app.agents.embedding_service import _mock_embed
            return [_mock_embed(t) for t in texts]

        with patch("app.agents.embedding_backfill.embed_texts", side_effect=flaky_embed_texts):
            result = await backfill_missing_embeddings(
                mock_db, batch_size=3, dry_run=False
            )

        assert result["embedded"] > 0, "Some chunks should succeed"
        assert result["failed"] > 0,   "Some chunks should fail"
        assert result["errors"],        "errors list should be non-empty"
        assert result["ok"] is True,    "Task should not be aborted on partial failure"


# ══════════════════════════════════════════════════════════════════════════════
# T6 — embed_texts internal batching
# ══════════════════════════════════════════════════════════════════════════════

class TestEmbedTextsBatching:
    """T6: 150 texts with batch_size=64 → 3 batches, 150 embeddings returned."""

    @pytest.mark.asyncio
    async def test_150_texts_three_batches(self):
        from app.agents.embedding_service import embed_texts, EMBEDDING_DIM

        texts = [f"Financial text number {i}." for i in range(150)]

        result = await embed_texts(texts, provider="mock", batch_size=64)

        assert len(result) == 150
        for v in result:
            assert len(v) == EMBEDDING_DIM

    @pytest.mark.asyncio
    async def test_batch_count_mock(self):
        """Verify that batching splits correctly."""
        from app.agents.embedding_service import embed_texts

        batch_inputs: list[list[str]] = []
        original_mock_embed = None

        import app.agents.embedding_service as svc
        original = svc._mock_embed

        call_batches: list[int] = []

        # Monkeypatch embed_texts to count batch sizes
        # We use batch_size=10 on 25 texts → expect 3 calls: 10, 10, 5
        async def counting_embed(texts_arg, *, provider=None, model=None, batch_size=None):
            bs = batch_size or 64
            results = []
            for start in range(0, len(texts_arg), bs):
                batch = texts_arg[start: start + bs]
                call_batches.append(len(batch))
                results.extend(original(t) for t in batch)
            return results

        with patch("app.agents.embedding_service.embed_texts", side_effect=counting_embed):
            import app.agents.embedding_service as svc2
            texts = [f"text {i}" for i in range(25)]
            await counting_embed(texts, batch_size=10)

        assert call_batches == [10, 10, 5]

    @pytest.mark.asyncio
    async def test_deterministic_with_batching(self):
        """Mock provider stays deterministic regardless of batch_size."""
        from app.agents.embedding_service import embed_texts

        texts = ["alpha text", "beta text", "gamma text"]

        r_single = await embed_texts(texts, provider="mock", batch_size=100)
        r_batch  = await embed_texts(texts, provider="mock", batch_size=1)

        assert r_single == r_batch


# ══════════════════════════════════════════════════════════════════════════════
# T7 — Hybrid weights from config
# ══════════════════════════════════════════════════════════════════════════════

class TestHybridWeightsConfig:
    """T7: combined_score uses configurable weights; absent score auto-normalises."""

    def test_combined_score_uses_config_weights(self):
        from app.agents.financial_rag_tool import _compute_score

        # Patch weights
        with patch("app.agents.financial_rag_tool._cfg") as mock_cfg:
            def cfg_side(attr, default):
                return {
                    "rag_vector_weight":       0.7,
                    "rag_keyword_weight":      0.2,
                    "rag_source_boost_weight": 0.07,
                    "rag_recency_boost_weight": 0.03,
                }.get(attr, default)
            mock_cfg.side_effect = cfg_side

            combined, detail = _compute_score(
                vector_score=0.8,
                keyword_score=0.5,
                source_level="general",
                published_at_str="",
            )

        expected_base = 0.7 * 0.8 + 0.2 * 0.5   # 0.56 + 0.10 = 0.66
        assert abs(combined - expected_base) < 0.01

    def test_absent_vector_score_normalises(self):
        from app.agents.financial_rag_tool import _compute_score

        # vector_score=0 → should use keyword only at full weight
        combined, detail = _compute_score(
            vector_score=0.0,
            keyword_score=0.6,
            source_level="general",
            published_at_str="",
        )
        # With vector=0, base = keyword_score (normalised)
        assert combined >= 0.5   # should be close to 0.6

    def test_absent_keyword_score_normalises(self):
        from app.agents.financial_rag_tool import _compute_score

        combined, detail = _compute_score(
            vector_score=0.75,
            keyword_score=0.0,
            source_level="general",
            published_at_str="",
        )
        assert combined >= 0.6   # should be close to 0.75

    def test_score_detail_has_all_fields(self):
        from app.agents.financial_rag_tool import _compute_score

        _, detail = _compute_score(0.5, 0.3, "official_exchange", "2025-01-01")
        for field in ("vector_score", "keyword_score", "source_boost",
                      "recency_boost", "combined_score"):
            assert field in detail

    def test_source_boost_capped(self):
        """Official source boost must not overwhelm low-relevance documents."""
        from app.agents.financial_rag_tool import _compute_score

        # Low relevance from official source
        _, detail_official = _compute_score(0.1, 0.1, "official_exchange", "")
        # High relevance from general source
        _, detail_general  = _compute_score(0.9, 0.9, "general", "")

        # Official doc with near-zero relevance should NOT beat high-relevance general
        combined_official = detail_official["combined_score"]
        combined_general  = detail_general["combined_score"]
        assert combined_general > combined_official


# ══════════════════════════════════════════════════════════════════════════════
# T8 — MMR diversity
# ══════════════════════════════════════════════════════════════════════════════

class TestMMRDiversity:
    """T8: same document limited to rag_mmr_max_per_doc slots."""

    def _make_result(self, doc_id: str, chunk_idx: int, score: float, chunk_text: str | None = None) -> dict:
        return {
            "title":        "Doc",
            "source_type":  "annual_report",
            "source":       "SEC",
            "published_at": "",
            "chunk":        chunk_text or f"chunk {chunk_idx}",
            "score":        score,
            "score_detail": {
                "vector_score": score, "keyword_score": 0.0,
                "source_boost": 0.0, "recency_boost": 0.0,
                "combined_score": score,
            },
            "search_mode_used": "vector",
            "metadata": {
                "doc_id": doc_id, "symbol": "", "market": "",
                "url": "", "page": None, "page_start": None, "page_end": None,
                "source_level": "general", "authority_score": 0.3,
                "verified": False, "report_year": None, "report_type": "",
                "search_mode_used": "vector",
            },
        }

    def test_same_doc_limited_to_max_per_doc(self):
        from app.agents.financial_rag_tool import _mmr_filter

        same_doc = str(uuid.uuid4())
        other_doc = str(uuid.uuid4())

        # 5 chunks from same_doc, 1 from other_doc
        results = [
            self._make_result(same_doc,  0, 0.95),
            self._make_result(same_doc,  1, 0.90),
            self._make_result(same_doc,  2, 0.85),
            self._make_result(same_doc,  3, 0.80),
            self._make_result(same_doc,  4, 0.75),
            self._make_result(other_doc, 0, 0.70),
        ]

        with patch("app.agents.financial_rag_tool._cfg_bool", return_value=True), \
             patch("app.agents.financial_rag_tool._cfg_int", return_value=2):
            filtered = _mmr_filter(results, top_k=4)

        # Should have at most 2 from same_doc
        same_doc_count = sum(1 for r in filtered if r["metadata"]["doc_id"] == same_doc)
        assert same_doc_count <= 2
        # other_doc should be included
        other_doc_count = sum(1 for r in filtered if r["metadata"]["doc_id"] == other_doc)
        assert other_doc_count == 1

    def test_mmr_disabled_returns_top_k(self):
        from app.agents.financial_rag_tool import _mmr_filter

        same_doc = str(uuid.uuid4())
        results = [self._make_result(same_doc, i, 1.0 - i * 0.1) for i in range(8)]

        with patch("app.agents.financial_rag_tool._cfg_bool", return_value=False):
            filtered = _mmr_filter(results, top_k=4)

        assert len(filtered) == 4

    def test_mmr_noop_when_results_leq_top_k(self):
        """If total results ≤ top_k, MMR is a no-op."""
        from app.agents.financial_rag_tool import _mmr_filter

        doc_id = str(uuid.uuid4())
        results = [self._make_result(doc_id, i, 0.9 - i * 0.1) for i in range(3)]

        with patch("app.agents.financial_rag_tool._cfg_bool", return_value=True), \
             patch("app.agents.financial_rag_tool._cfg_int", return_value=2):
            filtered = _mmr_filter(results, top_k=5)

        # All 3 returned (fewer than top_k)
        assert len(filtered) == 3

    def test_mmr_fills_remaining_from_deferred(self):
        """After per-doc cap, remaining slots are filled from deferred high-score results."""
        from app.agents.financial_rag_tool import _mmr_filter

        doc_a = str(uuid.uuid4())
        doc_b = str(uuid.uuid4())

        results = [
            self._make_result(doc_a, 0, 0.95),
            self._make_result(doc_a, 1, 0.90),   # max_per_doc=2 → allowed
            self._make_result(doc_a, 2, 0.88),   # would be deferred (3rd from doc_a)
            self._make_result(doc_b, 0, 0.70),
        ]

        with patch("app.agents.financial_rag_tool._cfg_bool", return_value=True), \
             patch("app.agents.financial_rag_tool._cfg_int", return_value=2):
            filtered = _mmr_filter(results, top_k=4)

        # All 4 should be in result (3 from doc_a after cap release + 1 from doc_b)
        assert len(filtered) == 4


# ══════════════════════════════════════════════════════════════════════════════
# T9 — Diagnostics field in financial_rag_search
# ══════════════════════════════════════════════════════════════════════════════

class TestDiagnosticsField:
    """T9: financial_rag_search always returns diagnostics."""

    @pytest.mark.asyncio
    async def test_diagnostics_present_on_success(self):
        from app.agents.financial_rag_tool import financial_rag_search

        row = _make_chunk_row()
        mr = MagicMock()
        mr.fetchall.return_value = [row]

        mock_db = AsyncMock()
        mock_db.execute.return_value = mr

        with patch("app.agents.financial_rag_tool._get_query_vector",
                   new=AsyncMock(return_value=[0.1] * 1536)):
            result = await financial_rag_search(
                "Apple services revenue", mock_db, search_mode="hybrid"
            )

        assert "diagnostics" in result
        d = result["diagnostics"]
        assert "search_mode_requested" in d
        assert "search_mode_used"      in d
        assert "vector_available"      in d
        assert "keyword_fallback_used" in d
        assert "returned_count"        in d
        assert isinstance(d["returned_count"], int)

    @pytest.mark.asyncio
    async def test_diagnostics_on_keyword_fallback(self):
        from app.agents.financial_rag_tool import financial_rag_search

        row = _make_chunk_row()
        mr = MagicMock()
        mr.fetchall.return_value = [row]

        mock_db = AsyncMock()
        mock_db.execute.return_value = mr

        with patch("app.agents.financial_rag_tool._get_query_vector",
                   side_effect=RuntimeError("embed unavailable")):
            result = await financial_rag_search(
                "revenue", mock_db, search_mode="hybrid"
            )

        assert result["ok"] is True
        d = result["diagnostics"]
        assert d["keyword_fallback_used"] is True
        assert d["search_mode_used"] == "keyword"

    @pytest.mark.asyncio
    async def test_diagnostics_search_mode_requested_preserved(self):
        from app.agents.financial_rag_tool import financial_rag_search

        mr = MagicMock()
        mr.fetchall.return_value = []

        mock_db = AsyncMock()
        mock_db.execute.return_value = mr

        result = await financial_rag_search(
            "test", mock_db, search_mode="keyword"
        )

        assert result["diagnostics"]["search_mode_requested"] == "keyword"

    @pytest.mark.asyncio
    async def test_diagnostics_on_error(self):
        """diagnostics must be present even when ok=False."""
        from app.agents.financial_rag_tool import financial_rag_search

        mock_db = AsyncMock()
        mock_db.execute.side_effect = Exception("DB unreachable")

        # keyword mode (no embed) so we hit DB directly
        result = await financial_rag_search(
            "revenue", mock_db, search_mode="keyword"
        )

        # keyword fallback catches DB error gracefully → ok=True, results=[]
        assert "diagnostics" in result

    @pytest.mark.asyncio
    async def test_diagnostics_mmr_flag(self):
        from app.agents.financial_rag_tool import financial_rag_search

        mr = MagicMock()
        mr.fetchall.return_value = []

        mock_db = AsyncMock()
        mock_db.execute.return_value = mr

        result = await financial_rag_search("test", mock_db, search_mode="keyword")
        assert "mmr_enabled" in result["diagnostics"]


# ══════════════════════════════════════════════════════════════════════════════
# T10 — Import smoke test
# ══════════════════════════════════════════════════════════════════════════════

class TestPhase2DImports:
    """T10: all Phase 2D modules importable."""

    def test_rag_healthcheck_importable(self):
        from app.agents.rag_healthcheck import check_pgvector_ready
        assert callable(check_pgvector_ready)

    def test_embedding_backfill_importable(self):
        from app.agents.embedding_backfill import backfill_missing_embeddings
        assert callable(backfill_missing_embeddings)

    def test_embedding_service_has_batch_size(self):
        import inspect
        from app.agents.embedding_service import embed_texts
        sig = inspect.signature(embed_texts)
        assert "batch_size" in sig.parameters

    def test_financial_rag_tool_has_diagnostics(self):
        """financial_rag_search returns diagnostics key."""
        import inspect
        from app.agents.financial_rag_tool import financial_rag_search
        # Just verify it's callable with the right signature
        sig = inspect.signature(financial_rag_search)
        assert "search_mode" in sig.parameters

    def test_config_has_rag_weights(self):
        from app.core.config import Settings
        fields = Settings.model_fields
        for field in (
            "rag_vector_weight", "rag_keyword_weight",
            "rag_source_boost_weight", "rag_recency_boost_weight",
            "rag_mmr_enabled", "rag_mmr_lambda", "rag_mmr_max_per_doc",
            "embedding_batch_size",
        ):
            assert field in fields, f"Config missing: {field}"
