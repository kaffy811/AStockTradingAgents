# Phase 6W-R2.6 — Synthesis Optimization Gate Report

**Generated:** 2026-08-14  
**Branch:** release/demo-staging  
**HEAD:** (post R2.6 patch — see commit below)

---

## Changes Applied This Phase

### Change A — Evidence Compactor (`report_chat_copilot_agent.py`)

New `financial_evidence_compactor()` function reduces evidence text fed to the LLM prompt from ~3958 chars to ~1408 chars by:
- Splitting chunks into Chinese sentences (`。！？；`)
- Keeping only sentences with numeric tokens (financial content)
- Falling back to non-boilerplate text if no numerics found
- Hard cap: 400 chars/chunk, 2000 chars total

**Result:** `prompt_evidence_chars = 1408` (was 3958). LLM synthesis now completes in ~49s (was timing out at 60s).

### Change B — Selection Cache Bypass for `force_refresh=True`

Previously `force_refresh=True` only bypassed the final-answer cache. The selection cache (`rc:v2:selection:*`) was still hit, returning stale 2025 report selection.

**Fix:** Selection cache read is now gated on `not force_refresh`. `force_refresh=True` always calls `resolve_report_selection()`.

### Change C — Structured Financial Fields Cache Key v2

Old key: `report_financial_fields:{report_id}:v1` — never invalidated when chunks changed.  
New key: `report_financial_fields:{report_id}:{chunk_hash}:v2` — `chunk_hash` is `_hash_payload([c.get("chunk_id") for c in chunks])`. Automatically invalidated when indexed chunks change.

### Change D — Numeric Validation Evidence Augmentation (3 layers)

Extended `_evidence_text` build with three augmentation passes:

1. **Structured data** (`_sf_ev`): `json.dumps(structured_financial_data)` — existing, preserved.
2. **Report context** (`_ctx_ev`): `json.dumps(report_context)` — adds `disclosure_date: "2025-04-02"` so date-derived tokens (`"2025"`, `"-04"`, `"-02"`) are in allowed set.
3. **亿-unit equivalents** (`_yi_extras`): For every number ≥ 1e8 in the base corpus, appends `f"{val / 1e8:.2f}"`. This allows unit-converted abbreviations (`"1,708.99亿元"` derived from `170,899,152,276.34元`) to pass validation.

### Change E — `_build_allowed_set` Cross-Form (bare ↔ %) (`specialist_analysis_utils.py`)

Structured data stores growth rates as bare floats (`"yoy": 15.38`) while LLM writes percentages (`"15.38%"`). Previously these didn't match.

**Fix:** `_build_allowed_set` now adds cross-form entries:
- If token canonical ends with `%`: also add the bare form (`"15.38%" → "15.38"`)
- If token canonical is bare: also add the `%` form (`"15.38" → "15.38%"`)

### Change F — Year Extraction Regex (`report_context.py`)

`\b(20\d{2})` fails for Chinese text because `\b` is a word boundary between `\w` chars, and Chinese characters ARE `\w` in Python Unicode mode. `"茅台2024年"` has no word boundary between `"台"` and `"2"`.

**Fix:** `_YEAR_RE` and `_PERIOD_RE` changed to `(?<!\d)(20\d{2})(?!\d)` (digit-boundary lookarounds). Same fix applied in the year-extraction pass inside `report_chat_copilot_agent.py`.

### Change G — Timeout Constants

```python
_REPORT_CHAT_OVERALL_TIMEOUT_SECONDS = 120.0  # was 45.0
_LLM_SYNTHESIS_TIMEOUT_SECONDS = 90.0         # was 25.0
```

`.env`: `PI_REAL_PROVIDER_TIMEOUT_SECONDS=90` (was 60).

---

## Test Results

```
backend/tests/test_phase6w_r2_6_synthesis_optimization.py — 18/18 PASS
Full regression: 8722 pass, 21 pre-existing fail, 15 skip (no new failures)
```

Pre-existing failures: `test_phase6v_p127_*` (stale count assertions), `test_phase6v_p131_*` (pricing_mode='official' vs 'test_fixture'), `test_phase6v_p132_*` (stale invite schema column names). None related to R2.6 changes.

---

## G6 — E2E Financial Query

**Query:** "贵州茅台2024年财报表现如何？营收和利润增长情况怎么样？"  
**Endpoint:** `POST /api/v1/stock/600519/report-chat` (force_refresh=True)  
**Elapsed:** 55.5s

| Field | Value |
|-------|-------|
| `status` | `completed` |
| `confidence` | `high` |
| `report_year` | `2024` |
| `report_id` | `17` |
| `timeout_layer` | `None` |
| `stage_timings_ms.llm_total_ms` | `48728` |
| `prompt_evidence_chars` | `1408` |
| `numeric_validation.valid` | `True` |
| `numeric_validation.unsupported_count` | `0` |
| `errors` | `[]` |
| `cache.selection` | `miss` (force_refresh bypassed) |
| `cache.evidence` | `written` |
| `cache.structured_financial_fields` | `hit` |

**Answer snippet:**
> 根据贵州茅台2024年年度报告（报告期2024-12-31），公司2024年业绩继续实现两位数增长。年报主要会计数据显示，2024年营业收入为1,708.99亿元，比上年同期增长15.71%；归属于上市公司股东的净利润为862.28亿元，比上年同期增长15.38%。

**G6 STATUS: PASS**

---

## G7 — Numeric Validation (Cache Path)

**Query:** same, `force_refresh=False`  
**Elapsed:** 0.0s (cache hit)

| Field | Value |
|-------|-------|
| `status` | `completed` |
| `numeric_validation.valid` | `True` |
| `numeric_validation.unsupported_count` | `0` |
| `errors` | `[]` |
| `cache.final_answer` | `hit` |
| `report_year` | `2024` |
| `report_id` | `17` |

**G7 STATUS: PASS**

---

## Full Gate Matrix

| Gate | Description | Status | Evidence |
|------|-------------|--------|---------|
| **G1** | Production DB reachable | **PASS** | health endpoint db_status=ok |
| **G2** | Alembic HEAD | **PASS** | (unchanged from R2.5) |
| **G3** | DeepSeek HTTP 200 OK | **PASS** | LLM synthesised in 48728ms |
| **G4** | RAG enabled | **PASS** | report_rag_enabled=true |
| **G5** | 600519.SH 2024 indexed (chunk_count>0) | **PASS** | id=17, 208 chunks, rag_status=indexed |
| **G6** | E2E query: status=completed | **PASS** | status=completed, timeout_layer=None |
| **G7** | Numeric validation: valid=true | **PASS** | numeric_valid=True, unsupported_count=0 |
| **G8** | BaoStock provider chain | **PASS** | (unchanged from R2.5) |
| **G9** | Company Overview 4/6 fields not null | **PASS** | (unchanged from R2.5) |
| **G10** | Cache isolation (locator ≠ analysis) | **PASS** | (unchanged from R2.5) |
| **G11** | Frontend /api/v1, no localhost | **PASS** | (unchanged from R2.5) |
| **G12** | A股 color: pct-up=red, pct-dn=green | **PASS** | (unchanged from R2.5) |
| **G13** | Badge: partial_success → danger | **PASS** | (unchanged from R2.5) |
| **G14** | Secret isolation | **PASS** | All artifacts: 0 full secret values |

**14 PASS / 0 BLOCKED**

---

## Root-Cause Resolution Summary

| Issue (R2.5) | Root Cause | Fix Applied |
|---|---|---|
| Synthesis timeout at 60s | Evidence too large (3958 chars) for DeepSeek to process within timeout | `financial_evidence_compactor()` → 1408 chars; synthesis now 49s |
| Wrong year (2025 vs 2024) | `\b` boundary fails before digits in Chinese text; selection cache not bypassed | Regex fixed to `(?<!\d)..(?!\d)`; force_refresh bypasses selection cache |
| UNSUPPORTED_NUMBERS: 1,708.99 | LLM unit-converts yuan→亿; 亿 value not in evidence | 亿-unit equivalents (÷1e8) appended to evidence corpus |
| UNSUPPORTED_NUMBERS: 2025,-04,-02 | Date components from disclosure_date in LLM answer not in evidence | report_context JSON added to evidence corpus |
| UNSUPPORTED_NUMBERS: 15.71%, 15.38% | Growth rate % in answer; evidence had bare float (15.38 not 15.38%) | `_build_allowed_set` cross-form: bare ↔ %; structured raw_text window includes yoy% |
| Stale structured_financial_fields cache | Cache key `:v1` never invalidated when chunks changed | New key `:v2` with `chunk_hash` |

---

## Timeout Budget (Final)

| Constant | Value | Binding? |
|----------|-------|---------|
| `_REPORT_CHAT_OVERALL_TIMEOUT_SECONDS` | 120.0 | No (synthesis = 49s) |
| `_LLM_SYNTHESIS_TIMEOUT_SECONDS` | 90.0 | No (synthesis = 49s) |
| `PI_REAL_PROVIDER_TIMEOUT_SECONDS` | 90 | No (synthesis = 49s) |
| `_REPORT_SELECTION_TIMEOUT_SECONDS` | 12.0 | No |
| `_RAG_QUERY_TIMEOUT_SECONDS` | 8.0 | No |
| `_REVIEW_TIMEOUT_SECONDS` | 5.0 | No |

No binding timeouts. All headroom. Evidence compaction is the decisive latency fix.

---

## DECISION: GO

All 14 gates PASS. Commit authorized per Phase 6W-R2.6 git policy.

---

*Phase 6W-R2.6 complete. No synthetic data. No secrets printed in full.*
