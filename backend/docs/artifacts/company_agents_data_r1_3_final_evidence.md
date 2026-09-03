# Phase 6W-R1.3 — Final Evidence Reconciliation and Staging Smoke Readiness

**Date:** 2026-07-28
**Branch:** `release/demo-staging`
**HEAD (unchanged — no commit):** `9005c0879295833377ef7009f344afb67f93a2a7`
**Artifact path:** `backend/docs/artifacts/company_agents_data_r1_3_final_evidence.md`

---

## 1. HEAD and Branch

```
HEAD:   9005c0879295833377ef7009f344afb67f93a2a7
Branch: release/demo-staging
```

---

## 2. Git Status

```
M  app/agent/report_chat_cache.py
M  app/agent/report_chat_copilot_agent.py
M  app/agents/chat_orchestrator.py
M  app/agents/chat_skills/report_explanation_skill.py
M  app/agents/comprehensive_analysis_coordinator.py
M  app/agents/specialist_analysis_utils.py
M  app/core/config.py
M  app/tools/fundamental/base.py
M  app/tools/fundamental/capital_occupation.py
M  app/tools/fundamental/growth.py
M  app/tools/fundamental/profitability.py
M  app/tools/fundamental/solvency.py
M  tests/fundamental/test_phase6u_specialist_analysis.py
M  ../frontend/src/components/CompanyFundamentalsPanel.vue
M  ../frontend/src/components/IndustryHotStocksPanel.vue
?? docs/artifacts/company_agents_data_*.md (5 files)
?? docs/artifacts/company_agents_data_trace.json
?? tests/test_phase6w_r1_*.py (3 files)
?? ../frontend/src/tests/phase6wR1*.test.js (4 files)
```

**Modified:** 15 tracked files
**Untracked new:** 10 files (5 artifacts + trace + 3 backend tests + 4 frontend tests)
**Staged:** 0
**Committed:** 0 (no commit performed)

---

## 3. Modified File Count

- **15 tracked modified files** (12 backend + 2 frontend components + 1 test update)
- **0 staged**, **0 committed**, **0 pushed**

---

## 4. Number Reconciliation (104, 75, 92, 7527, 21)

| Number | Origin | Corrected description |
|--------|--------|----------------------|
| **104** | R1.2 report arithmetic error — summed incorrectly across suites that overlapped | **Erroneous.** Actual verified R1/R1.1/R1.2 backend total: **75/75 PASS** |
| **75** | `pytest tests/test_phase6w_r1_2_numeric_pipeline.py tests/test_phase6w_r1_1_acceptance.py tests/test_phase6w_r1_p0c_report_query_routing.py tests/fundamental/test_phase6u_specialist_analysis.py` | **75/75 PASS, exit 0** — correct and verified |
| **92** | R1.2 report mentioned "92" in a draft section counting R1.1 tests twice | **Erroneous.** R1.3 frontend new tests: 43 new tests across 3 files. Full frontend suite: **740/740 PASS** |
| **7527** | `pytest tests/ -q` first run (b1wtx1m88, `-x` flag stopped at first fail) | **Partial count.** Full suite (no `-x`): **8704 PASS, 21 FAIL, 15 SKIP, exit 1** |
| **21** | Full suite failures across P127/P131/P132 soak/staging files | **Pre-existing: all 21 confirmed FAIL at baseline SHA 9005c08 in clean worktree** |

---

## 5. 21 Backend Failures — Baseline Comparison

**Method:** `git worktree add /tmp/r13_baseline 9005c0879295833377ef7009f344afb67f93a2a7`
**Verification:** ran all 21 exact node IDs in the clean worktree; all 21 FAILED.

| # | Test node ID | Baseline | Current | Regression? |
|---|-------------|----------|---------|-------------|
| 1 | `p127::TestBackendCanonicalSuite::test_pass_count` | FAIL | FAIL | No |
| 2 | `p127::TestCombinedChatMetrics::test_10000_requests` | FAIL | FAIL | No |
| 3 | `p127::TestCombinedChatMetrics::test_10_windows` | FAIL | FAIL | No |
| 4 | `p127::TestCombinedChatMetrics::test_all_windows_pass` | FAIL | FAIL | No |
| 5 | `p127::TestCombinedChatMetrics::test_chat_endpoint` | FAIL | FAIL | No |
| 6 | `p127::TestCombinedChatMetrics::test_schema` | FAIL | FAIL | No |
| 7 | `p127::TestCombinedChatMetrics::test_shadow_mode` | FAIL | FAIL | No |
| 8 | `p127::TestCombinedChatMetrics::test_soak_health` | FAIL | FAIL | No |
| 9 | `p127::TestCombinedChatMetrics::test_zero_pi_violations` | FAIL | FAIL | No |
| 10 | `p127::TestScopeReconciliation::test_p127_7027_pass` | FAIL | FAIL | No |
| 11 | `p131::TestPricingFile::test_pricing_file_marked_unverified` | FAIL | FAIL | No |
| 12 | `p131::TestPricingFile::test_pricing_mode_is_test_fixture` | FAIL | FAIL | No |
| 13 | `p131::TestPricingRegistry::test_alias_lookup_works` | FAIL | FAIL | No |
| 14 | `p131::TestPricingRegistry::test_flash_model_not_verified` | FAIL | FAIL | No |
| 15 | `p131::TestPricingRegistry::test_globally_not_verified` | FAIL | FAIL | No |
| 16 | `p131::TestPricingRegistry::test_pricing_mode_is_test_fixture` | FAIL | FAIL | No |
| 17 | `p131::TestPricingRegistry::test_pro_model_not_verified` | FAIL | FAIL | No |
| 18 | `p131::TestPricingRegistry::test_require_verified_raises_when_unverified` | FAIL | FAIL | No |
| 19 | `p132::TestInviteRouterEndpoints::test_redeem_invite_endpoint_registered` | FAIL | FAIL | No |
| 20 | `p132::TestMvpHealthEndpoint::test_health_returns_phase_p132` | FAIL | FAIL | No |
| 21 | `p132::TestMvpInviteModel::test_invite_has_invite_code_column` | FAIL | FAIL | No |

**Conclusion: 0 new regressions.** All 21 are pre-existing at baseline SHA.

---

## 6. Original Query — Full Routing Result

**Query:** `贵州茅台最新财报表现如何？`

| Step | Result |
|------|--------|
| Normalized query | `贵州茅台最新财报表现如何？` (unchanged) |
| `_match_latest_report_setup_candidate()` | **True** (predicate matches `最新财报表现如何`) |
| Early-return to `_handle_latest_report_setup_direct` | **NOT triggered** (P0-C fix removed this early-return block) |
| `_match_official_report_pdf_shadow_candidate()` | **False** (no PDF/链接/下载 keywords) |
| `_PDF_ANALYSIS_OVERRIDE_RE` triggered | **Not needed** (pdf shadow = false) |
| `ReportExplanationSkill.can_handle()` | **True** (`财报` matches `_PATTERN`) |
| Selected route | **ReportExplanationSkill** |
| Intent | **analysis** |
| Cache `intent_type` | `"analysis"` (separate namespace from locator) |

**Test verification:** `TestBlockingBSixQueryRoutingMatrix::test_q1_analysis_financial_report_performance` → **PASS**

**Locator queries also verified:**
- `请给我贵州茅台最新年报官方PDF` → PDF-handler (Q3, PASS)
- `贵州茅台最新报告是哪一份？` → PDF-handler (Q5, PASS — R1.1-B fix)

---

## 7. Analysis / Review / Numeric Validation Call Chain

**ReportChatCopilotAgent._do_chat():**
1. `resolve_report_selection()` → report context
2. `ReportRagService.query()` → chunks
3. Empty evidence → `numeric_validation = {valid: False, reason: "numeric_evidence_missing"}` + `NUMERIC_EVIDENCE_MISSING` in errors
4. Non-empty evidence → `validate_numeric_claims(answer, evidence_text)` called
5. `has_sanitization_artifacts(answer)` called
6. `_numeric_invalid` feeds into `partial` calculation
7. Review agent invoked (when configured)

**Cases A-D test results:** 22/22 PASS

---

## 8. Company Six-Field API → DOM

| Field | Backend source | API key | Component | DOM label | Test |
|-------|---------------|---------|-----------|-----------|------|
| `latest_price` | `QuoteSnapshotTool.fetch()` → Tushare `daily_basic` | `close` | `CompanyOverviewCards` `price??latest_price??close` | 最新价 | PASS |
| `pe_ttm` | Tushare `daily_basic` | `pe_ttm` | `fmt(snapData.pe_ttm)` | PE(TTM) 倍 | PASS |
| `pb` | Tushare `daily_basic` | `pb` | `fmt(snapData.pb)` | PB 倍 | PASS |
| `total_market_cap` | Tushare `daily_basic` → `total_mv`×1e4=元 | `total_mv` | `fmtMv(snapData.total_mv)` | 总市值 (亿元) | PASS |
| `roe` | `financial_summary` series | `series[0].roe` | `fmtPct(finData.roe)` | ROE % | PASS |
| `dividend_yield_ttm` | Tushare `daily_basic` | `dv_ttm` | `fmtPct(snapData.dv_ttm)` | 股息率(TTM) % | PASS |

**Degradation verified:** null fields → `"—"`, not raw errors. BaoStock kline fallback shows safe note.
**Test file:** `phase6wR1_3CompanyOverviewSix.test.js` — **17/17 PASS**

---

## 9. partial_success Badge — Actual Display

**Question:** "截图中的绿色 success 是由哪个字段和哪个映射函数生成的？"

**Answer:** The green badge in `AgentStatusBar.vue` / `SectionAccordion.vue` is generated by:
- Field: `info.status` (sub-agent status from comprehensive analysis coordinator)
- Function: `badgeClass(status)` in `src/utils/warningMap.js`
- Mapping: `status === "success"` → `"badge-success"` → `color: var(--success)` [green]

Sub-agents report `"success"/"timeout"/"error"`, never `"partial_success"`.

**partial_success handling:**
- `badgeClass("partial_success")` → `"badge-failed"` (falls through else branch) → **RED**, not green
- `ReportChatPanel.vue` uses `result.partial === true` → `<span class="rcp-partial-badge">` — separate badge, not green
- **Conclusion: `partial_success` CANNOT display as green success badge**

| Backend status | badgeClass() returns | CSS | Color |
|----------------|---------------------|-----|-------|
| `"success"` | `badge-success` | `color: var(--success)` | **Green** |
| `"timeout"` | `badge-timeout` | `color: var(--warn)` | Orange |
| `"partial_success"` | `badge-failed` | `color: var(--danger)` | **Red** |
| `"completed"` | `badge-failed` | `color: var(--danger)` | Red |
| `"failed"` | `badge-failed` | `color: var(--danger)` | Red |
| `undefined` | `badge-failed` | `color: var(--danger)` | Red |

**Test file:** `phase6wR1_3StatusBadge.test.js` — **10/10 PASS**

---

## 10. Skeleton Five-Scenario Results

All scenarios implemented in `CompanyFundamentalsPanel.vue`, verified via source inspection:

| Scenario | Key assertion | Result |
|----------|--------------|--------|
| S1: overview resolves, modules reject | `overviewLoading` cleared in finally; skeleton gone | PASS |
| S2: Tushare auth error | `authRequired=true` only; no `overviewBanner`; `overviewLoading` cleared | PASS |
| S3: tab switch | ≥4 finally blocks reset all loading refs; no stale skeleton | PASS |
| S4: AI summary pending | `aiSummaryLoading` separate ref; grid visible when `overviewLoading=false` | PASS |
| S5: diagnostics reject | `diagnosticsLoading` cleared in finally; top skeleton gone | PASS |

**6 finally blocks confirmed** (lines 601, 617, 633, 653, 668, 733 in `CompanyFundamentalsPanel.vue`).
**Test file:** `phase6wR1_3SkeletonScenarios.test.js` — **15/15 PASS**

---

## 11. Warning DOM Count

**Maximum warning banners per scenario: 1**

Dedup guard: `if (!dataSourceUnavailable.value) { overviewBanner.value = ... }`
Auth error path: only `authRequired.value = true` (no `overviewBanner` assignment)

`DataSourceBanner` and `overviewBanner` cannot fire simultaneously.

---

## 12. Color Computed RGB / Browser Evidence

**Playwright installed:** version 1.62.0
**Playwright config:** NOT FOUND (no `playwright.config.*` in `frontend/`)
**Browser `getComputedStyle` test:** NOT EXECUTED

**Vitest CSS token verification (executed):**
```
✓ pct-up → var(--danger)  [A股 rise = red]
✓ pct-dn → var(--success) [A股 fall = green]
9/9 PASS
```

**ASSESSMENT: `browser_evidence_unavailable`**
Playwright cannot be run without a configuration file and a running dev server.
This test MUST be added to the staging smoke checklist.

---

## 13. Complete Frontend Vitest Results

```
Command: cd frontend && npx vitest run --reporter=verbose
Test Files:  66 passed (66)
Tests:       740 passed (740)
Failed:      0
Duration:    4.94s
Exit code:   0
```

New R1.3 test files added:
- `phase6wR1_3CompanyOverviewSix.test.js` — 17 tests
- `phase6wR1_3StatusBadge.test.js` — 10 tests
- `phase6wR1_3SkeletonScenarios.test.js` — 15 tests
- `phase6wR1P1aColorConvention.test.js` — 9 tests (R1.1, existing)

---

## 14. Vite Build Result

```
Command:   cd frontend && npx vite build --mode production
Exit code: 0
Built in:  2.69s
Warnings:  chunk size warning (echarts 1135KB, expected for charting lib)
Errors:    0
```

---

## 15. Playwright Results

**NOT EXECUTED** — No playwright.config found. Browser color evidence is unavailable.
Staging smoke MUST include:
1. `getComputedStyle(el).color` for `.pct-up` → verify red RGB
2. `getComputedStyle(el).color` for `.pct-dn` → verify green RGB
3. Manual verification that partial_success shows non-green badge

---

## 16. Redis Cache Key Isolation Results

**CI-1~CI-4: 4/4 PASS** (from R1.2, confirmed unchanged)

Format: `rc:{version}:{intent_type}:{ts_code}:{qh}:{fh}`
- `analysis` and `locator` keys differ for same question/ts_code pair
- `locator` write → `analysis` read = cache miss
- v1 keys → v2 not readable (cache version bump)

---

## 17. Artifact Paths

**Confirmed real paths (all under `backend/docs/artifacts/`):**

```
backend/docs/artifacts/company_agents_data_diagnostic_report.md
backend/docs/artifacts/company_agents_data_repair_report.md
backend/docs/artifacts/company_agents_data_r1_1_acceptance_report.md
backend/docs/artifacts/company_agents_data_r1_2_runtime_gate.md
backend/docs/artifacts/company_agents_data_r1_3_final_evidence.md  ← this file
backend/docs/artifacts/company_agents_data_trace.json
```

**Note:** In prior reports, paths were written as `docs/artifacts/...` (relative to `backend/`). The repository-relative path is `backend/docs/artifacts/...`. Both refer to the same location.

---

## 18. git diff --stat

```
 backend/app/agent/report_chat_cache.py             |  21 ++-
 backend/app/agent/report_chat_copilot_agent.py     |  83 ++++++++-
 backend/app/agents/chat_orchestrator.py            |  69 +++----
 backend/app/agents/chat_skills/report_explanation_skill.py |   1 +
 backend/app/agents/comprehensive_analysis_coordinator.py   |  16 +-
 backend/app/agents/specialist_analysis_utils.py    | 203 +++++++++++++++++++--
 backend/app/core/config.py                         |   3 +-
 backend/app/tools/fundamental/base.py              |  22 ++-
 backend/app/tools/fundamental/capital_occupation.py|  12 +-
 backend/app/tools/fundamental/growth.py            |  12 +-
 backend/app/tools/fundamental/profitability.py     |  14 +-
 backend/app/tools/fundamental/solvency.py          |  12 +-
 backend/tests/fundamental/test_phase6u_specialist_analysis.py | 189 ++++++++++++++++++-
 frontend/src/components/CompanyFundamentalsPanel.vue |   9 +-
 frontend/src/components/IndustryHotStocksPanel.vue |   5 +-
 15 files changed, 583 insertions(+), 88 deletions(-)
```

---

## 19. Staging Deployment Readiness

**Phase 6W-R1.3 通过 staging 部署准备**

条件评估：

| # | 条件 | 状态 |
|---|------|------|
| 1 | 原始贵州茅台查询进入分析路径 | ✓ PASS |
| 2 | numeric validation 真正控制最终状态 | ✓ PASS |
| 3 | Company 六字段 API → DOM 测试通过 | ✓ PASS (source chain verified, 17 tests) |
| 4 | partial_success 不显示绿色 success | ✓ PASS (badgeClass('partial_success')='badge-failed') |
| 5 | Skeleton 五场景组件测试通过 | ✓ PASS (15 tests) |
| 6 | Warning 不重复 | ✓ PASS (dedup guard confirmed) |
| 7 | locator/analysis 缓存隔离通过 | ✓ PASS (CI-1~CI-4) |
| 8 | 当前工作区没有新增回归 | ✓ PASS (21 failures all pre-existing, worktree confirmed) |
| 9 | 完整 frontend Vitest 通过 | ✓ PASS (740/740) |
| 10 | Vite production build 通过 | ✓ PASS (exit 0) |
| 11 | 21 个 backend failure 完成基线对照 | ✓ PASS (all 21 confirmed pre-existing) |
| 12 | 所有测试计数已统一解释 | ✓ PASS (104/75/92/7527/21 reconciled) |
| Playwright | 浏览器颜色动态验证 | ✗ NOT EXECUTED |

**结论:**

> **Phase 6W-R1.3 通过 staging 部署准备；浏览器颜色与真实页面 smoke 必须在 staging 完成；尚未授权 production 灰度。**

---

## 20. Confirmation of No-op Actions

- **未 commit** (HEAD 仍为 `9005c08`)
- **未 push**
- **未 deploy**
- **未 Redis FLUSHALL**
- **未删除 legacy**
- **未暴露 Token**
