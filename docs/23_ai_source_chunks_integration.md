# Phase 6H — AI Source Chunks Integration

## Overview

Phase 6H injects report RAG (Retrieval-Augmented Generation) chunks into the AI fundamental analysis pipeline, enabling the LLM to cite real annual report passages in its output. The feature is strictly opt-in per request: RAG context is only fetched when the API endpoint receives a database session (i.e., a live HTTP request), and the system never raises if the RAG layer is unavailable or returns no results.

---

## Architecture

```
GET /api/v1/stock/{code}/modules/ai_analysis
        │
        ▼ db=AsyncSession (injected via Depends)
FundamentalAIOrchestrator.run(market, symbol, mode, force_refresh, db)
        │
        ▼
FundamentalDataAgent.collect(..., db=db)
  ├── existing: fetch_module × N (concurrent)
  └── new: _collect_rag_context(ts_code, db, mode)
             └── ReportRagService.query() × up to 6 queries
                 dedup by chunk_id, limit 4 (summary) / 8 (full)
        │
        ▼ data_pack with report_rag_context + allowed_chunk_ids + rag_meta
FundamentalAnalysisAgent.analyze(data_pack, mode)
  └── _compress_data_pack_for_prompt includes report_rag_context
  └── LLM may output source_chunks[] citing chunk_ids
        │
        ▼ raw_analysis (may include source_chunks)
FundamentalReviewAgent.review(analysis, data_pack)
  └── _check_source_chunks: removes invalid chunk_ids (not in allowed_chunk_ids)
  └── chunk_issues → revised_needed (soft, not rejected)
        │
        ▼ final_analysis (cleaned source_chunks)
Orchestrator: enrich source_chunks with full content + provider metadata
Orchestrator: compute rag_status (unavailable / mock / local / keyword_only)
        │
        ▼
_build_envelope: data.ai_analysis.source_chunks + data.ai_analysis.rag_status
```

---

## New / Changed Files

### Backend

| File | Change |
|------|--------|
| `app/agent/schemas.py` | `make_data_pack` gains `report_rag_context`, `allowed_chunk_ids`, `rag_meta` params |
| `app/agent/fundamental_data_agent.py` | `collect()` accepts `db=None`; new `_collect_rag_context()` + `_RAG_QUERIES_*` |
| `app/agent/prompts/analysis_agent_system.md` | Rules 7–11 for `source_chunks`; `source_chunks` added to JSON schema |
| `app/agent/fundamental_analysis_agent.py` | `_compress_data_pack_for_prompt` includes `report_rag_context` |
| `app/agent/fundamental_review_agent.py` | `_check_source_chunks()`, `_check_hallucination_patterns()`; `_rule_based_review` returns `(result, cleaned_analysis)` tuple |
| `app/agent/fundamental_ai_orchestrator.py` | `run()` / `_run_internal()` accept `db=None`; enrich source_chunks; add `rag_status` to envelope |
| `app/agent/ai_cache.py` | `_input_hash` includes `chunk_ids` so cache busts when RAG results change |
| `app/routers/fundamentals_compat.py` | `get_stock_module_compat` injects `db` via `Depends(get_db)` and passes to orchestrator |

### Frontend

| File | Change |
|------|--------|
| `src/components/fundamentals/AiAnalysisCard.vue` | Adds `effectiveSourceChunks` + `effectiveChunksMeta` computed props; falls back to `analysis.source_chunks` when not passed as props |

### Tests

- `tests/fundamental/test_phase6h_ai_source_chunks.py` — 13 tests covering the full pipeline

---

## Data Pack New Fields

```python
data_pack = {
    # ... existing fields ...
    "report_rag_context": [
        {
            "chunk_id": 42,
            "report_id": 100,
            "ts_code": "600519.SH",
            "report_type": "annual",
            "report_year": 2023,
            "period": "20231231",
            "chunk_index": 0,
            "section_title": "管理层讨论与分析",
            "content": "公司主营业务为酱香型白酒...",  # truncated to 1000 chars
            "has_embedding": True,
            "score": 0.87,
        }
    ],
    "allowed_chunk_ids": [42],          # for Review Agent validation
    "rag_meta": {
        "provider": "mock",             # "mock" | "local"
        "fallback_used": False,         # True if keyword search was used
        "search_mode": "vector",        # "vector" | "keyword"
        "chunk_count": 1,
    }
}
```

---

## Envelope Response Shape

```json
{
  "data": {
    "ai_analysis": {
      "summary": "...",
      "overall_score": 78,
      "dimensions": [...],
      "highlights": [...],
      "risks": [...],
      "watch_items": [...],
      "source_chunks": [
        {
          "chunk_id": 42,
          "report_id": 100,
          "ts_code": "600519.SH",
          "report_type": "annual",
          "report_year": 2023,
          "period": "20231231",
          "section_title": "管理层讨论与分析",
          "content": "公司主营业务为酱香型白酒...",
          "score": 0.87,
          "citation": "主营业务为酱香型白酒",
          "provider": "mock",
          "fallback_used": false
        }
      ],
      "rag_status": "mock",
      "data_quality": {...},
      "disclaimer": "..."
    }
  }
}
```

`rag_status` values:
- `"unavailable"` — no DB or no chunks indexed for this stock
- `"mock"` — mock embedding provider (development)
- `"local"` — local sentence-transformer embedding
- `"keyword_only"` — vector search failed, keyword fallback used

---

## Safety Invariants

1. **Never raises if db=None** — `_collect_rag_context` is only called when `db is not None`; all RAG errors are caught and logged.
2. **Never rejects analysis for empty source_chunks** — empty `source_chunks` is valid output.
3. **Review Agent removes, not rejects** — invalid `chunk_id`s are silently removed from `source_chunks`; issues are noted as `revised_needed` (not `rejected`).
4. **Hallucination patterns** ("第X页", "完整覆盖所有财报") trigger `rejected` status.
5. **Cache key includes chunk_ids** — changing RAG results busts the cache correctly.
6. **PROMPT_VERSION stays "v1"** — cache key version not bumped; chunk_ids in hash handle invalidation.

---

## RAG Query Set

| Mode | Queries |
|------|---------|
| summary (4 max chunks) | 主营业务/收入来源, 盈利能力变化, 经营活动现金流, 主要风险 |
| full (8 max chunks) | above + 未来发展战略/经营计划, 分红政策/利润分配情况 |

Each query fetches `top_k=3` from `ReportRagService`; results are deduplicated by `chunk_id` and capped at the mode limit.

---

## Phase 6I Extensions

Phase 6I adds strict Review Agent validation on top of Phase 6H. See [`docs/24_review_agent_source_chunk_validation.md`](24_review_agent_source_chunk_validation.md) for details:

- `_canonicalize_source_chunks()`: chunk_id whitelist enforcement + metadata override from `rag_context`
- `_check_and_remove_page_citations()`: strips "第N页" references
- `_check_and_rewrite_coverage_claims()`: rewrites "完整覆盖所有财报"
- `_check_citation_consistency()`: rewrites orphaned citation signal words
- `review_audit` trail in `data.ai_analysis` for frontend inspection
- Frontend "✓ 引用已通过系统校验" badge in `AiAnalysisCard.vue`
