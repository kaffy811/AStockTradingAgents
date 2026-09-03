# Phase 6W-R1 Company/Financial Agents Production Correctness Repair Report

**Generated**: 2026-07-28
**Branch**: release/demo-staging
**Baseline SHA**: 9005c0879295833377ef7009f344afb67f93a2a7
**Repair round**: 6W-R1 (based on diagnostic from company_agents_data_diagnostic_report.md)

---

## Repair Summary

| Item | Priority | Status | Files Changed |
|------|----------|--------|---------------|
| P0-A: remove_unsupported_numbers() rewrite | P0 | ✅ FIXED | `specialist_analysis_utils.py` |
| P0-B: _ABS_PATH_RE over-matching | P0 | ✅ FIXED | `specialist_analysis_utils.py` |
| P0-C: financial report query early return | P0 | ✅ FIXED | `chat_orchestrator.py` |
| P1-A: A股 color convention inversion | P1 | ✅ FIXED | `IndustryHotStocksPanel.vue` |
| P1-B: Tushare permission error safe messages | P1 | ✅ FIXED | `base.py`, `profitability.py`, `growth.py`, `solvency.py`, `capital_occupation.py` |
| P1-C: Company overview field mapping | P1 | ✅ DOCUMENTED | (below) |
| P1-D: skeleton loading + duplicate banners | P1 | ✅ FIXED | `CompanyFundamentalsPanel.vue` |
| P1-E: report chat cache version bump | P1 | ✅ FIXED | `config.py` |

---

## P0-A: remove_unsupported_numbers() Rewrite

**Root cause** (from diagnostic):
- When `evidence_text=""`, the function did global `_NUMERIC_RE.sub("未提供数字", text)` → corrupted ALL output text
- Used `text.replace(token, "未提供数字")` which caused partial-match corruption: replacing `5.90` inside `1315.90` produced `1315未提供数字`
- No canonical equivalence: `1315.90` ≠ `1315.9`, `+19.80%` ≠ `19.8%`

**Fix applied** (`app/agents/specialist_analysis_utils.py`):

1. **Fail-closed contract**: When `evidence_text` is empty/absent, return `text` unchanged. No global replacement.
2. **Token-level substitution**: Replaced `text.replace(token, ...)` with `_NUMERIC_RE.sub(callback, text)`. Callback checks each match independently → no partial-match corruption.
3. **Canonical equivalence**: Added `_canonicalize_number()` helper:
   - `"1,315.90"` → `"1315.9"` (comma strip + float normalize)
   - `"+19.80%"` → `"19.8%"` (leading + strip + trailing-zero strip)
4. **Fixed `_NUMERIC_RE`**: Changed from `\d{1,3}(?:,\d{3})*` (greedy, could match `131` from `1315.90`) to TWO alternatives:
   - Alt-1 (comma-thousands): `\d{1,3}(?:,\d{3})+` — **requires ≥1 comma group**
   - Alt-2 (plain): `\d+(?:\.\d+)?%?` — handles all non-comma numbers
5. **`_build_allowed_set()`**: Builds expanded allowed set with raw + canonical + comma-stripped forms.

**Tests**: 5 new cases (A-E) in `tests/fundamental/test_phase6u_specialist_analysis.py`:
- Case A: empty evidence fail-closed
- Case B: no partial-match corruption
- Case C: canonical equivalence (trailing zeros)
- Case D: canonical equivalence (leading + percent)
- Case E: comma thousands separator

Updated existing test: `test_phase6u_common_formatting_keeps_zero_and_hides_missing_values` — `88%` is now PRESERVED when `evidence_text=""` (fail-closed behavior).

---

## P0-B: _ABS_PATH_RE Over-matching

**Root cause** (from diagnostic):
- `_ABS_PATH_RE = re.compile(r"(/[A-Za-z0-9_.@-]+)+")` matched ANY single `/word` pattern
- LLM output like `MA5/cross` would produce `MA5[path]` (false positive)
- Technical indicators, dates, and other single-segment tokens were being redacted

**Fix applied** (`app/agents/specialist_analysis_utils.py` line 20):
```python
_ABS_PATH_RE = re.compile(r"(?<![A-Za-z0-9_.])(?:/[A-Za-z0-9_.@-]+){2,}")
```
- **Requires ≥2 path segments**: `/MA5` alone → no match; `/usr/lib/python3.11` → match ✓
- Added `(?<![A-Za-z0-9_.])` lookbehind to avoid false matches inside word boundaries
- Preserved real multi-segment Unix path redaction

**Tests**: 4 new cases in `TestAbsPathReP0B`:
- Real multi-segment paths still matched
- Single segments not matched
- Technical indicators produce no `[path]` artifacts
- Date slash notation not matched

---

## P0-C: Financial Report Query Early Return

**Root cause** (from diagnostic):
- `_handle_latest_report_setup_direct()` was called as an early-return gate for queries matching `_LATEST_REPORT_SETUP_PATTERN`
- Pattern matches analysis queries: "最新财报表现如何", "最近报告怎么样", etc.
- The function found the report context but returned immediately with `status=partial_success`, WITHOUT invoking any Analysis/Review agents
- `ReportExplanationSkill` (which does actual RAG-based analysis) was never reached

**Fix applied** (`app/agents/chat_orchestrator.py`):
- Removed two early-return blocks that called `_handle_latest_report_setup_direct`:
  1. The early fast-path block at ~line 1428 (before entity resolution)
  2. The mid-path block at ~line 1678 (after shadow runner)
- Queries now fall through to the SkillRegistry path where `ReportExplanationSkill` (priority=10) handles them with full RAG analysis
- `_handle_latest_report_setup_direct()` function is preserved (still referenced by other callers)
- Added comments explaining the P0-C removal

**Intent separation preserved**:
- `_match_latest_report_setup_candidate()`: analysis queries ("最新财报如何") → now reach SkillRegistry
- `_match_official_report_pdf_shadow_candidate()`: PDF-find queries ("下载年报PDF") → still route to `_handle_official_report_pdf_direct()`

**Tests**: 6 new tests in `tests/test_phase6w_r1_p0c_report_query_routing.py`:
- Analysis intent queries still match the predicate
- PDF-find queries don't match analysis pattern
- Pattern intent separation verified
- Source code confirms no remaining early-return to `_handle_latest_report_setup_direct`

---

## P1-A: A股 Color Convention Inversion

**Root cause** (from diagnostic):
- `IndustryHotStocksPanel.vue` CSS had `.pct-up { color: var(--success) }` and `.pct-dn { color: var(--danger) }`
- A股 convention: **rise = red (danger)**, **fall = green (success)**
- `IndustryStockCard.vue` and `WatchlistStockCard.vue` already had correct convention: `.up { color: var(--danger) }`, `.down { color: var(--success) }`

**Fix applied** (`frontend/src/components/IndustryHotStocksPanel.vue` lines 382-383):
```css
/* A股 convention: up = red (danger), down = green (success) */
.pct-up { color: var(--danger);  font-weight: 600; }
.pct-dn { color: var(--success); font-weight: 600; }
```

**Tests**: 9 vitest tests in `frontend/src/tests/phase6wR1P1aColorConvention.test.js`:
- `changePctClass` logic: positive → pct-up, negative → pct-dn, zero/null/NaN → ""
- CSS variable mapping: pct-up → var(--danger), pct-dn → var(--success)
- Source comment confirms A股 convention intent

---

## P1-B: Tushare Permission Error Safe User-Facing Messages

**Root cause** (from diagnostic):
- `TushareAuthError` message "Tushare 权限不足或 Token 无效: ..." was propagating into `err_envelope.reason`
- `build_api_response` put this raw reason into `data.reasons[]` and `errors[]`
- Frontend `DataSourceBanner` / `firstReason()` could display the raw provider error to users
- `partial_errors` in individual tools also accumulated raw `TushareAuthError` messages

**Fix applied**:

1. **`app/tools/fundamental/base.py`** (`fetch_with_fallback`):
   - Added `except TushareAuthError as primary_err:` before generic `TushareError`
   - Logs raw error internally at WARNING level
   - Sets `primary_reason = "部分财务指标暂不可用，系统已继续使用其他可用数据源。"` (safe user-facing)
   - Sets `_is_permission_error = True` flag
   - AkShare fallback still attempted (AkShare is independent, doesn't need Tushare auth)
   - For combined errors (Tushare auth + AkShare failure): keeps safe primary_reason

2. **`app/tools/fundamental/profitability.py`**: Safe `partial_errors` for `TushareAuthError` in `asyncio.gather`
3. **`app/tools/fundamental/growth.py`**: Same pattern
4. **`app/tools/fundamental/solvency.py`**: Same pattern
5. **`app/tools/fundamental/capital_occupation.py`**: Same pattern

Safe message format: `"xxx 暂不可用（权限不足）"` (no raw Tushare error detail)

---

## P1-C: Company Overview Field Mapping Table

**Finding**: Field emptiness in Company overview traced to two sources:

### Module: `financial_summary` (Tushare fina_indicator)

| API Field | Tushare Source | Status When Perm-Denied |
|-----------|---------------|------------------------|
| `roe` | fina_indicator.roe | `null` → P1-B fix returns safe error |
| `roe_waa` | fina_indicator.roe_waa | `null` |
| `roa` | fina_indicator.roa | `null` |
| `roic` | fina_indicator.roic | `null` |
| `grossprofit_margin` | fina_indicator.grossprofit_margin | `null` |
| `netprofit_margin` | fina_indicator.netprofit_margin | `null` |
| `debt_to_assets` | fina_indicator.debt_to_assets | `null` |
| `current_ratio` | fina_indicator.current_ratio | `null` |
| `quick_ratio` | fina_indicator.quick_ratio | `null` |
| `assets_turn` | fina_indicator.assets_turn | `null` |
| `netprofit_yoy` | fina_indicator.netprofit_yoy | `null` |
| `tr_yoy` | fina_indicator.tr_yoy | `null` |
| `or_yoy` | fina_indicator.or_yoy | `null` |
| `ebit` | fina_indicator.ebit | `null` |
| `ebitda` | fina_indicator.ebitda | `null` |
| `beps` | fina_indicator.beps | `null` |
| `ocfps` | fina_indicator.ocfps | `null` |

**When Tushare permission denied**: All 17 fields return `null`. The `fetch_with_fallback` now catches `TushareAuthError`, uses safe message, and tries AkShare (`fetch_akshare()` from `FinancialSummaryTool` provides `roe`, `grossprofit_margin` etc. via `stock_financial_abstract_ths`).

### Module: `quote_snapshot` (real-time quote providers)

Fields: `price`, `change_pct`, `volume`, `turnover`, `market_cap`, `pe_ttm`, `pb`, `eps`, `dividend_yield`
Sources: Eastmoney → Sina → BaoStock (fallback chain)
Status: Not affected by Tushare auth errors.

---

## P1-D: Skeleton Loading + Duplicate Warning Banners

**Root cause** (from diagnostic):
- Two warning banners shown simultaneously for the same issue:
  1. `DataSourceBanner` (triggered by `dataSourceUnavailable.value = true`)
  2. `FundamentalStateBanner` (triggered by `overviewBanner.value = { type: 'warn', ... }`)
- When `overviewSnap.partial = true` AND `isUnavailable = true`, both fired
- Auth errors also showed both banners: `authRequired = true` + `overviewBanner` with AUTH_REQUIRED_MESSAGE

**Fix applied** (`frontend/src/components/CompanyFundamentalsPanel.vue`):

1. **Partial data deduplication**: Only set `overviewBanner` for partial data when `!dataSourceUnavailable.value`:
   ```javascript
   if (overviewSnap.value?.partial || overviewFin.value?.partial) {
     if (!dataSourceUnavailable.value) {
       overviewBanner.value = { type: 'warn', msg: '部分数据获取不完整...' }
     }
   }
   ```

2. **Auth error deduplication**: `isAuthError(e)` sets `authRequired.value = true` (which drives `DataSourceBanner`); no longer also sets `overviewBanner`:
   ```javascript
   if (isAuthError(e)) {
     authRequired.value = true
     // P1-D dedup: DataSourceBanner covers auth via authRequired; no overviewBanner
   }
   ```

**Skeleton persistence**: All async loaders (`loadOverview`, `loadModule`, `loadDiagnostics`, `loadAiSummary`) already had proper `finally` blocks. The `diagnosticsLoading` skeleton at line 91 is properly cleared in all paths.

---

## P1-E: Report Chat Cache Version Bump

**Root cause** (from diagnostic):
- `report_chat_cache_version: str = "v1"` in `config.py`
- Stale v1 caches may have held answers from before P0-A (sanitization) and P0-C (early return) fixes
- v1 caches could serve pre-fix answers where report analysis was never invoked

**Fix applied** (`app/core/config.py`):
```python
report_chat_cache_version: str = "v2"  # bumped v1→v2 after Phase 6W-R1 fixes
```

**No FLUSHALL**: Old v1 keys (`rc:v1:...`) will expire naturally. New requests generate v2 keys.
**Key structure preserved**: `rc:{version}:{ts_code}:{question_hash}:{filters_hash}`

---

## Test Results

| Test Suite | Count | Result |
|-----------|-------|--------|
| tests/fundamental/ (full) | 5230 | ✅ ALL PASS |
| tests/test_phase6w_r1_p0c_report_query_routing.py | 6 | ✅ ALL PASS |
| tests/fundamental/test_phase6u_specialist_analysis.py | 20 | ✅ ALL PASS |
| tests/fundamental/test_phase6k_report_chat_cache_rate_memory.py | 23 | ✅ ALL PASS |
| frontend/src/tests/phase6wR1P1aColorConvention.test.js | 9 | ✅ ALL PASS |

**Total new tests added**: 5 (P0-A Cases A-E) + 4 (P0-B) + 6 (P0-C) + 9 (P1-A) = **24 new tests**

---

## Files Changed

### Backend (`backend/`)
- `app/agents/specialist_analysis_utils.py` — P0-A, P0-B
- `app/agents/chat_orchestrator.py` — P0-C
- `app/tools/fundamental/base.py` — P1-B
- `app/tools/fundamental/profitability.py` — P1-B
- `app/tools/fundamental/growth.py` — P1-B
- `app/tools/fundamental/solvency.py` — P1-B
- `app/tools/fundamental/capital_occupation.py` — P1-B
- `app/core/config.py` — P1-E

### Frontend (`frontend/`)
- `src/components/IndustryHotStocksPanel.vue` — P1-A

### Tests (new)
- `tests/fundamental/test_phase6u_specialist_analysis.py` — P0-A, P0-B additions
- `tests/test_phase6w_r1_p0c_report_query_routing.py` — P0-C new file
- `frontend/src/tests/phase6wR1P1aColorConvention.test.js` — P1-A new file

---

## Prohibitions Respected

- ✅ No deployment executed
- ✅ No Redis FLUSHALL (cache version bump only; v1 keys expire naturally)
- ✅ No Tushare token exposure in any file
- ✅ No legacy code deleted (only behavior fixed)
- ✅ No mock data masking real errors
- ✅ Commit/push not executed (awaiting project lead review)
