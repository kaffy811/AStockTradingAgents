# Update 50 - Phase 6U-D4.2 Report Chat Timeout Fix

Date: 2026-07-15

## Summary

Fixed the ReportChatCopilotAgent timeout path for indexed financial reports. The report chat flow now uses an indexed-report fast path, bounded evidence retrieval, layered timeouts, stage timing metadata, and evidence-based fallback answers when synthesis times out.

## Root Cause

The 60-75 second timeout was caused by the report chat path entering the Company V2 RAG bridge and loading the full indexed document with 211 chunks. A real diagnostic call showed `get_document(2)` taking about 54.2 seconds before the retriever loaded the document again. The legacy `report_chunks` table had 0 rows for `report_id=2`, so the old path could not use a lightweight persisted chunk query.

## Changes

- Added report-context metadata for persisted PDF URL, source URL, parsed status, RAG status, and chunk count.
- Added layered ReportChatCopilotAgent timing and timeout metadata.
- Added indexed-report fast path for persisted indexed reports.
- Added bounded direct evidence retrieval from `company_v2_report_rag_documents` and `company_v2_report_rag_chunks`.
- Limited report evidence to top-k <= 8 and total evidence characters <= 6000.
- Added direct PDF-question answer path that skips heavy RAG and LLM synthesis.
- Added cache keys for report selection and evidence bundles using the existing cache abstraction.
- Added evidence-based fallback for LLM timeout with retrieved chunks.
- Preserved non-empty answer guarantees for completed and partial-success responses.
- Added frontend reducer coverage for `partial_success` answer rendering.

## Validation

- Targeted backend: `37 passed`.
- Full backend: `3193 passed, 1 skipped`.
- Frontend Vitest: `666 passed`.
- Frontend build: passed.

## Performance Notes

Real 600519 report-chat validation for `贵州茅台最新财报表现如何？` returned non-empty answers in all 5 runs. Total latency ranged from about 13.6s to 23.8s, with `report_id=2`, `report_year=2025`, and 3-4 source chunks.

The PDF follow-up used the persisted official URL path and returned in about 982ms without invoking heavy RAG or LLM synthesis.

## Boundaries

- No P1-P4 Prompt content changes.
- No Stage 3 authorization changes.
- No `auto_run` or `rollout_percent` changes.
- No database migration.
- No public API field removal.

