# Update 51 - Phase 6U-D5 Industry Metrics and Report Answer Consistency

Date: 2026-07-16

## Summary

Implemented industry-aware Company V2 metric applicability and hardened report-chat answer consistency. Bank/insurance/securities/real-estate profiles now distinguish non-applicable fields from true missing data. Report chat now has deterministic structured metric extraction, field reconciliation utilities, verified-report sanitizer context, and final answer consistency guards.

## Company V2

- Expanded industry metric profiles: `general_corporate`, `bank`, `insurance`, `securities`, `real_estate`.
- Bank profile excludes generic corporate fields such as inventory turnover, receivable turnover, current ratio, quick ratio, cash ratio, and gross margin from applicable coverage.
- Coverage denominator now uses applicable fields only.
- History responses include per-series stats: actual, expected, not-applicable, conflict, and missing points.
- Implausible history values are retained but tagged as `OUTLIER_REQUIRES_REVIEW`; chart contracts disable misleading line connection for those modules.
- Normal UI maps internal codes to friendly copy such as "暂无可用数据", "指标口径待确认", and "该行业不适用".

## Report Chat

- Added `ReportFinancialTableExtractorTool` for deterministic extraction from parsed official report chunks.
- Added `FinancialFieldReconciliationTool` with official-report-first priority and conflict provenance.
- ReportChatCopilotAgent now injects structured financial fields into synthesis context and caches them under `report_financial_fields:{report_id}:v1`.
- Successful report answers carry `answer_owner=report_explanation_skill` and verified financial context.
- The financial safety sanitizer now preserves report-backed revenue/profit numbers instead of replacing them with tool-required placeholders.
- Successful report answers no longer receive generic data-boundary/news fallback notes.
- Final report answers are checked for placeholder leakage, contradictory news-only notes, markdown table misalignment, and duplicate disclaimers.

## Validation

- Targeted backend D5: `8 passed`.
- Related backend regression: `94 passed`.
- Full backend: `3201 passed, 1 skipped`.
- Targeted frontend: `3 passed`.
- Full frontend Vitest: `669 passed`.
- Frontend build: passed.

## Boundaries

- P1-P4 prompts were not changed.
- Stage 3 authorization was not changed.
- `auto_run` and `rollout_percent` were not changed.
- No fake financial data or interpolation was added.
- No database migration was added.
- Public API fields were not removed; changes are additive metadata/behavior.

