# Review Agent Source Chunk Validation (Phase 6I)

## Overview

Phase 6I hardens the Review Agent with strict `source_chunks` canonicalization, citation consistency enforcement, and a `review_audit` trail surfaced to the frontend.

The Review Agent now acts as a **semantic firewall** between the LLM's output and the API response — it ensures every chunk reference is traceable to a real, indexed report chunk, and that no citation claims exceed the available data.

---

## What Was Changed

### 1. `source_chunks` Canonicalization (`_canonicalize_source_chunks`)

The LLM is not trusted to report its own chunk metadata accurately. For every `chunk_id` the LLM cites:

| Check | Action |
|-------|--------|
| `chunk_id` not in `allowed_chunk_ids` | Remove chunk entirely |
| LLM modified `section_title`, `report_type`, `period`, etc. | Override with `rag_context` ground truth |
| Duplicate `chunk_id` | Deduplicate (keep first) |
| More than 8 chunks cited | Truncate to 8 |

**Metadata trust model**: All `report_id`, `section_title`, `report_type`, `report_year`, `period`, `ts_code` values come exclusively from `data_pack.report_rag_context`. The LLM's own values for these fields are discarded.

`pdf_url` is always set to `None` — the backend fills this in via a separate route if needed. The LLM does not know the backend's URL scheme.

### 2. Page Citation Removal (`_check_and_remove_page_citations`)

Pattern `第\s*\d+\s*页` (e.g., "第12页", "第 3 页") is removed from all text fields. Reason: chunk `page_start`/`page_end` metadata is not reliably populated, so page-level references can't be verified.

### 3. Coverage Claim Rewrite (`_check_and_rewrite_coverage_claims`)

Claims like "完整覆盖所有财报" are rewritten to "基于已接入的公开财报片段和结构化数据". The LLM doesn't have access to every filing — it only sees what was collected by the Data Agent.

### 4. Citation Consistency Check (`_check_citation_consistency`)

If the analysis body contains citation signal words ("根据年报", "财报显示", "报告披露", etc.) but `source_chunks` and `report_rag_context` are both empty, those phrases are rewritten to generic equivalents:

- "根据年报" → "根据已接入的结构化公开数据"
- "财报显示" → "已有数据显示"
- etc.

### 5. `review_audit` Trail

Every API response `data.ai_analysis` now includes a `review_audit` dict:

```json
{
  "review_audit": {
    "source_chunks_checked": true,
    "invalid_chunk_ids_removed": [],
    "metadata_canonicalized": false,
    "page_citation_removed": false,
    "coverage_claim_rewritten": false,
    "citation_consistency_rewritten": false,
    "investment_advice_blocked": false,
    "mild_phrases_rewritten": []
  }
}
```

This is safe for frontend display — it contains no prompt text, no raw chunk content, and no PII.

---

## Processing Order

```
raw LLM output
    │
    ▼
1. _canonicalize_source_chunks()    — chunk_id whitelist + metadata override
    │
    ▼
2. _check_and_remove_page_citations()  — strip 第N页
    │
    ▼
3. _check_and_rewrite_coverage_claims() — rewrite "完整覆盖"
    │
    ▼
4. _check_citation_consistency()       — rewrite orphaned citation signals
    │
    ▼
5. Standard checks (banned words, structure, fact_ids, numeric hallucination)
    │
    ▼
approved / revised / rejected
```

---

## Frontend Changes

`AiAnalysisCard.vue` now:
- Reads `analysis.review_audit` from the envelope
- Shows a "✓ 引用已通过系统校验" badge (teal) in the "引用财报片段" section header when `review_audit.source_chunks_checked` is `true`

No `v-html` is used anywhere — all content rendered via `{{ }}` text interpolation.

---

## API Response

```json
{
  "data": {
    "ai_analysis": {
      "summary": "...",
      "overall_score": 72,
      "source_chunks": [
        {
          "chunk_id": 42,
          "report_id": 1,
          "section_title": "管理层讨论与分析",
          "report_type": "annual",
          "period": "2023-12-31",
          "content": "...",
          "score": 0.87,
          "citation": "根据年报管理层章节...",
          "pdf_url": null
        }
      ],
      "rag_status": "local",
      "review_audit": {
        "source_chunks_checked": true,
        "invalid_chunk_ids_removed": [],
        "metadata_canonicalized": false,
        "page_citation_removed": false,
        "coverage_claim_rewritten": false,
        "citation_consistency_rewritten": false,
        "investment_advice_blocked": false,
        "mild_phrases_rewritten": []
      }
    }
  }
}
```

---

## Tests

18 tests in `tests/fundamental/test_phase6i_review_source_chunks_strict.py`:

| # | Test | What it verifies |
|---|------|-----------------|
| 1 | `test_valid_chunk_passes` | Valid chunk_id keeps correct metadata |
| 2 | `test_invalid_chunk_id_removed` | chunk_id not in allowed list → removed |
| 3 | `test_llm_modified_section_title_canonicalized` | LLM section_title override → ignored |
| 4 | `test_llm_modified_report_type_canonicalized` | LLM report_type override → ignored |
| 5 | `test_duplicate_chunk_id_deduped` | Same chunk_id cited twice → deduped |
| 6 | `test_more_than_8_chunks_truncated` | 11 chunks → truncated to 8 |
| 7 | `test_page_citation_removed` | "第12页" removed from summary |
| 7b | `test_page_citation_regex_variants` | "第 3 页" (with spaces) also caught |
| 8 | `test_coverage_claim_rewritten` | "完整覆盖所有财报" → accurate phrasing |
| 9 | `test_citation_signal_rewritten_when_no_data` | "根据年报" → generic when no chunks |
| 9b | `test_citation_signal_not_rewritten_when_chunks_present` | Signal preserved when chunks exist |
| 10 | `test_review_audit_has_expected_keys` | All 8 audit keys present |
| 11 | `test_review_audit_canonicalization_flag` | `metadata_canonicalized` set when LLM modified |
| 12 | `test_investment_advice_blocked_flag` | Banned phrase → audit flag set |
| 13 | `test_orchestrator_includes_review_audit` | Envelope contains review_audit |
| 14 | `test_make_review_result_carries_audit` | schemas.make_review_result propagates audit |
| 14b | `test_make_review_result_without_audit_defaults_to_empty` | Missing audit → `{}` |
| 15 | `test_no_v_html_in_ai_analysis_card` | No XSS risk in Vue components |

---

## Graceful Degradation

When `db=None` (no database connection), `allowed_chunk_ids=[]` and `report_rag_context=[]`. The canonicalization pass runs but finds no valid chunks — `source_chunks` is returned as `[]` and `review_audit.source_chunks_checked=True` still. No error is raised.
