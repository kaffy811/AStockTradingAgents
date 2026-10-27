# Phase 6W-R2.0 — Browser Validation

**Generated:** 2026-08-12  
**Branch:** release/demo-staging  
**HEAD:** a542bc1  
**Tool:** Playwright Chromium (headless), system Python 3.8  
**Target:** Staging frontend at http://127.0.0.1:18080  
**Environment:** Staging (same CSS bundle as production)

---

## G22: A股 Color Convention — BROWSER_EVIDENCE_PASS

### Test Method

Playwright headless Chromium loaded the staging frontend and used `document.styleSheets` iteration to:
1. Read all CSS rules applied in the browser (including scoped Vue component rules)
2. Verify `.pct-up[data-v-*]` rules use `color: var(--danger)`
3. Verify `.pct-dn[data-v-*]` rules use `color: var(--success)`
4. Resolve `--danger` and `--success` via `getComputedStyle(document.documentElement)`
5. Create inline elements to get resolved RGB values

### Active Theme

Browser loaded with `data-theme = light-holo` (user's persisted preference).

| CSS Variable | Hex Value | Resolved RGB |
|-------------|-----------|-------------|
| `--danger` | `#e5485d` | `rgb(229, 72, 93)` |
| `--success` | `#16a085` | `rgb(22, 160, 133)` |

Note: Default theme has `--danger: #ef5350`. Both are red/green variants. A股 convention holds across all themes.

### CSS Rules Verified in Browser

| Selector | CSS Color Property | Status |
|----------|-------------------|--------|
| `.pct-up[data-v-ce6f7f0c]` | `color: var(--danger)` | ✅ PASS |
| `.pct-up[data-v-88df557e]` | `color: var(--danger)` | ✅ PASS |
| `.pct-dn[data-v-ce6f7f0c]` | `color: var(--success)` | ✅ PASS |
| `.pct-dn[data-v-88df557e]` | `color: var(--success)` | ✅ PASS |

### Color Verification

| Check | Expected | Actual | Pass |
|-------|----------|--------|------|
| `.pct-up` uses `var(--danger)` | true | true | ✅ |
| `.pct-dn` uses `var(--success)` | true | true | ✅ |
| `--danger` resolves to red (R > G, R > B) | true | `rgb(229,72,93)` R=229 > G=72 ✓ | ✅ |
| `--success` resolves to green (G > R, G > B) | true | `rgb(22,160,133)` G=160 > R=22 ✓ | ✅ |

**G22 Verdict: BROWSER_EVIDENCE_PASS**

A股 convention confirmed at browser runtime:
- 涨 (up) → `.pct-up` → `var(--danger)` → **red** `rgb(229, 72, 93)`
- 跌 (down) → `.pct-dn` → `var(--success)` → **green** `rgb(22, 160, 133)`

This supersedes prior `SOURCE_ONLY` evidence from R1.6. G22 is now closed.

---

## G25: Badge Semantics

### CSS Rules Verified in Browser

| Class | Background | Color |
|-------|-----------|-------|
| `.badge-success` | `rgba(45, 217, 139, 0.12)` | `var(--success)` |
| `.badge-failed` | `rgba(245, 85, 74, 0.12)` | `var(--danger)` |

### Semantics Check

`partial_success` status → `badgeClass('partial_success')` → `'badge-failed'` (from Vue source)

- `badge-failed` background: `rgba(245, 85, 74, 0.12)` — red-tinted ✅
- `badge-failed` color: `var(--danger)` — red text ✅
- `badge-success` NOT applied to partial_success states ✅

**G25 Verdict: PASS** — `partial_success` badge displays in red (failed color), not green.

---

## G23: Skeleton States

### Evidence

Skeleton CSS rules in production bundle (`index-CQLORyqy.css`): 1 rule containing "loading".  
Browser-loaded stylesheets show skeleton animation rules are loaded.

**Staging verification (R1.6 evidence):** Skeleton loading states were confirmed in staging — shown during API fetch, removed on data load.

**Browser-level skeleton test not re-run** (requires live data-loading page + network throttling). R1.6 staging evidence is accepted as code-level verification. CSS rules confirmed present in production bundle.

**G23 Verdict: STAGING_EVIDENCE_PASS** — Cannot reclassify to BROWSER_EVIDENCE_PASS without throttled network test. Acceptable for 1% canary.

---

## CSS Bundle Reference

Production CSS: `frontend/dist/assets/index-CQLORyqy.css`

Relevant rules confirmed present:
```css
.pct-up[data-v-ce6f7f0c]{color:var(--danger)}
.pct-up[data-v-88df557e]{color:var(--danger);font-weight:600}
.pct-dn[data-v-ce6f7f0c]{color:var(--success)}
.pct-dn[data-v-88df557e]{color:var(--success);font-weight:600}
--danger: #ef5350;  (default theme)
--danger: #e5485d;  (light-holo theme)
--danger: #c86f75;  (light theme variant)
--success: #26a69a; (default theme)
--success: #16a085; (light-holo theme)
--success: #6f9f91; (light theme variant)
```

All three theme variants: danger = red family, success = green family. ✅
