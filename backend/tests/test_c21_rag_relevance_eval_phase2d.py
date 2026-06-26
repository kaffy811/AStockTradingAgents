"""
tests/test_c21_rag_relevance_eval_phase2d.py

Phase 2D: RAG relevance evaluation using the eval cases in
tests/fixtures/rag_eval_cases.json.

Strategy:
  1. Build an in-memory mock "database" from the eval case documents.
  2. Mock DB.execute so that _keyword_search returns rows whose chunk_text
     contains the expected_keywords for the matching case.
  3. Run financial_rag_search and assert recall / precision criteria.
  4. No external API calls; uses mock embedding provider.
"""
from __future__ import annotations

import json
import os
import uuid
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ── Load eval cases ────────────────────────────────────────────────────────────

_FIXTURE_PATH = os.path.join(
    os.path.dirname(__file__),
    "fixtures",
    "rag_eval_cases.json",
)

with open(_FIXTURE_PATH, encoding="utf-8") as _f:
    EVAL_CASES = json.load(_f)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_row_for_case(case: dict) -> Any:
    """Create a mock DB row that matches the eval case's document."""
    doc = case["doc"]
    return SimpleNamespace(
        chunk_id=str(uuid.uuid4()),
        chunk_text=doc["text"],
        chunk_index=0,
        chunk_symbol=doc["symbol"],
        chunk_market=doc["market"],
        chunk_metadata={},
        embedding_model=None,
        doc_id=str(uuid.uuid4()),
        title=doc["title"],
        source_type=doc["source_type"],
        source=doc["source"],
        published_at=doc.get("published_at", ""),
        url=doc.get("url", ""),
        doc_metadata={
            "symbol": doc["symbol"],
            "market": doc["market"],
        },
        vector_score=0.88,
        keyword_raw=5.0,
    )


# ══════════════════════════════════════════════════════════════════════════════
# Eval case fixtures
# ══════════════════════════════════════════════════════════════════════════════

class TestRAGEvalCasesLoaded:
    """Verify the eval fixture is well-formed."""

    def test_fixture_exists_and_non_empty(self):
        assert os.path.exists(_FIXTURE_PATH)
        assert len(EVAL_CASES) >= 2

    def test_each_case_has_required_fields(self):
        for case in EVAL_CASES:
            assert "id"                   in case, f"{case} missing id"
            assert "query"                in case, f"{case} missing query"
            assert "expected_keywords"    in case, f"{case} missing expected_keywords"
            assert "expected_source_type" in case, f"{case} missing expected_source_type"
            assert "doc"                  in case, f"{case} missing doc"

    def test_doc_has_text(self):
        for case in EVAL_CASES:
            doc = case["doc"]
            assert doc.get("text"), f"case {case['id']} doc.text is empty"
            assert doc.get("source_type"), f"case {case['id']} doc.source_type missing"


# ══════════════════════════════════════════════════════════════════════════════
# Eval: keyword search recall
# ══════════════════════════════════════════════════════════════════════════════

class TestEvalKeywordRecall:
    """keyword search should find eval-case documents by expected_keywords."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("case", EVAL_CASES, ids=[c["id"] for c in EVAL_CASES])
    async def test_keyword_recall(self, case: dict):
        from app.agents.financial_rag_tool import financial_rag_search

        row = _make_row_for_case(case)
        mr = MagicMock()
        mr.fetchall.return_value = [row]

        mock_db = AsyncMock()
        mock_db.execute.return_value = mr

        # Use keyword mode (no vector needed)
        result = await financial_rag_search(
            case["query"],
            mock_db,
            symbol=case.get("symbol"),
            market=case.get("market"),
            search_mode="keyword",
        )

        assert result["ok"] is True, f"RAG failed: {result.get('error')}"
        assert len(result["results"]) > 0, f"No results for case {case['id']}"

        # Check expected_keywords appear in at least one returned chunk
        chunks_combined = " ".join(r["chunk"].lower() for r in result["results"])
        for kw in case["expected_keywords"]:
            assert kw.lower() in chunks_combined, (
                f"Case {case['id']}: keyword '{kw}' not found in results"
            )

    @pytest.mark.asyncio
    @pytest.mark.parametrize("case", EVAL_CASES, ids=[c["id"] for c in EVAL_CASES])
    async def test_source_type_match(self, case: dict):
        from app.agents.financial_rag_tool import financial_rag_search

        row = _make_row_for_case(case)
        mr = MagicMock()
        mr.fetchall.return_value = [row]

        mock_db = AsyncMock()
        mock_db.execute.return_value = mr

        result = await financial_rag_search(
            case["query"], mock_db, search_mode="keyword"
        )

        assert result["ok"] is True
        found_types = {r["source_type"] for r in result["results"]}
        assert case["expected_source_type"] in found_types, (
            f"Case {case['id']}: expected source_type={case['expected_source_type']}, "
            f"got {found_types}"
        )


# ══════════════════════════════════════════════════════════════════════════════
# Eval: vector / hybrid search
# ══════════════════════════════════════════════════════════════════════════════

class TestEvalVectorRecall:
    """vector/hybrid mode should also recall eval-case documents."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("case", EVAL_CASES, ids=[c["id"] for c in EVAL_CASES])
    async def test_hybrid_recall(self, case: dict):
        from app.agents.financial_rag_tool import financial_rag_search

        row = _make_row_for_case(case)
        mr = MagicMock()
        mr.fetchall.return_value = [row]

        mock_db = AsyncMock()
        mock_db.execute.return_value = mr

        with patch(
            "app.agents.financial_rag_tool._get_query_vector",
            new=AsyncMock(return_value=[0.1] * 1536),
        ):
            result = await financial_rag_search(
                case["query"],
                mock_db,
                symbol=case.get("symbol"),
                market=case.get("market"),
                search_mode="hybrid",
            )

        assert result["ok"] is True
        assert len(result["results"]) > 0

        chunks_combined = " ".join(r["chunk"].lower() for r in result["results"])
        for kw in case["expected_keywords"]:
            assert kw.lower() in chunks_combined, (
                f"Case {case['id']}: keyword '{kw}' not found in hybrid results"
            )


# ══════════════════════════════════════════════════════════════════════════════
# Eval: search_mode_used correctness
# ══════════════════════════════════════════════════════════════════════════════

class TestEvalSearchModeUsed:

    @pytest.mark.asyncio
    async def test_keyword_mode_label(self):
        from app.agents.financial_rag_tool import financial_rag_search

        case = EVAL_CASES[0]
        row = _make_row_for_case(case)
        mr = MagicMock()
        mr.fetchall.return_value = [row]

        mock_db = AsyncMock()
        mock_db.execute.return_value = mr

        result = await financial_rag_search(
            case["query"], mock_db, search_mode="keyword"
        )

        assert result["search_mode"] == "keyword"
        for r in result["results"]:
            assert r["search_mode_used"] == "keyword"
            assert r["metadata"]["search_mode_used"] == "keyword"

    @pytest.mark.asyncio
    async def test_vector_mode_label(self):
        from app.agents.financial_rag_tool import financial_rag_search

        case = EVAL_CASES[0]
        row = _make_row_for_case(case)
        mr = MagicMock()
        mr.fetchall.return_value = [row]

        mock_db = AsyncMock()
        mock_db.execute.return_value = mr

        with patch(
            "app.agents.financial_rag_tool._get_query_vector",
            new=AsyncMock(return_value=[0.1] * 1536),
        ):
            result = await financial_rag_search(
                case["query"], mock_db, search_mode="vector"
            )

        assert result["search_mode"] == "vector"


# ══════════════════════════════════════════════════════════════════════════════
# Eval: official source boost for exchange-sourced documents
# ══════════════════════════════════════════════════════════════════════════════

class TestEvalOfficialSourceBoost:

    def test_sec_url_gets_boost(self):
        from app.agents.financial_rag_tool import _compute_score, _source_level_for_url

        # AAPL eval case uses SEC URL
        aapl_case = next(c for c in EVAL_CASES if c["id"] == "aapl_services_revenue")
        url = aapl_case["doc"]["url"]
        level = _source_level_for_url(url)
        assert level == "official_exchange"

        _, detail = _compute_score(0.5, 0.5, level, "2025-10-30")
        assert detail["source_boost"] > 0

    def test_sse_url_gets_boost(self):
        from app.agents.financial_rag_tool import _source_level_for_url

        moutai_case = next(c for c in EVAL_CASES if c["id"] == "moutai_gross_margin")
        url = moutai_case["doc"]["url"]
        level = _source_level_for_url(url)
        assert level == "official_exchange"

    @pytest.mark.asyncio
    async def test_official_doc_scores_higher_than_general(self):
        from app.agents.financial_rag_tool import financial_rag_search
        import uuid as _uuid

        # Two identical chunks, one from SEC (official), one from blog (general)
        doc_id_sec  = str(_uuid.uuid4())
        doc_id_blog = str(_uuid.uuid4())

        def _row(doc_id, url, title):
            return SimpleNamespace(
                chunk_id=str(_uuid.uuid4()),
                chunk_text="Apple services revenue grew 14 percent.",
                chunk_index=0,
                chunk_symbol="AAPL",
                chunk_market="US",
                chunk_metadata={},
                embedding_model=None,
                doc_id=doc_id,
                title=title,
                source_type="annual_report",
                source="SEC" if "sec.gov" in url else "blog",
                published_at="2025-10-30",
                url=url,
                doc_metadata={},
                vector_score=0.85,
                keyword_raw=5.0,
            )

        rows = [
            _row(doc_id_sec,  "https://www.sec.gov/Archives/0000320193-25.htm", "Apple 10-K"),
            _row(doc_id_blog, "https://random-blog.com/aapl-analysis", "AAPL Blog"),
        ]

        mr = MagicMock()
        mr.fetchall.return_value = rows

        mock_db = AsyncMock()
        mock_db.execute.return_value = mr

        result = await financial_rag_search(
            "services revenue", mock_db, search_mode="keyword"
        )

        assert result["ok"] is True
        assert len(result["results"]) == 2

        # SEC result should rank first
        top_result = result["results"][0]
        assert "sec.gov" in top_result["metadata"]["url"], (
            f"Expected SEC result first, got url={top_result['metadata']['url']}"
        )
        assert top_result["score_detail"]["source_boost"] > 0


# ══════════════════════════════════════════════════════════════════════════════
# Eval: no external dependency check
# ══════════════════════════════════════════════════════════════════════════════

class TestEvalNoDependencies:

    @pytest.mark.asyncio
    async def test_all_eval_cases_no_network(self):
        """Run all eval cases through keyword search; must pass with no network."""
        from app.agents.financial_rag_tool import financial_rag_search

        for case in EVAL_CASES:
            row = _make_row_for_case(case)
            mr = MagicMock()
            mr.fetchall.return_value = [row]

            mock_db = AsyncMock()
            mock_db.execute.return_value = mr

            result = await financial_rag_search(
                case["query"], mock_db, search_mode="keyword"
            )
            assert result["ok"] is True, f"Case {case['id']} failed: {result}"
            assert "diagnostics" in result

    @pytest.mark.asyncio
    async def test_mock_embed_used_not_openai(self):
        """Embedding must use mock provider (not OpenAI) in eval tests."""
        from app.agents.embedding_service import embed_texts, _get_provider

        # Default provider should be mock in test environment
        provider = _get_provider()
        assert provider in ("mock",), (
            f"Expected mock embedding provider in tests, got: {provider}"
        )

        vecs = await embed_texts(["test text"], provider="mock")
        assert len(vecs) == 1
        assert len(vecs[0]) == 1536
