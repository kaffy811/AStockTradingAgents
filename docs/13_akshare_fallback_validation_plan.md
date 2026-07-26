# AkShare Fallback Validation Plan

**Scope:** Staging only  
**Production default:** `ENABLE_AKSHARE=false` — do NOT change for production  
**Purpose:** Verify that AkShare can serve real financial rows when Tushare Pro is unavailable  
**Prerequisite:** Completed RC-2 / RC-2B / RC-2C validation

---

## Background

The fundamentals aggregator supports an AkShare fallback layer. When `ENABLE_AKSHARE=true`, modules that fail Tushare calls attempt to retrieve data from AkShare before returning `partial=True`.

AkShare is a community-maintained open-source library providing access to Chinese financial market data. It does not require a subscription token but:
- Has no formal SLA on data freshness or availability
- Field names may differ from Tushare output
- Coverage varies by stock and report period
- Must be validated against the frontend panel schemas before production use

This plan covers the validation steps required before AkShare can be considered for production activation.

---

## Step 1 — Enable AkShare in Staging

Edit `backend/.env` (staging environment only):

```bash
ENABLE_AKSHARE=true
```

Restart the backend:

```bash
cd backend && uvicorn app.main:app --port 8000 --reload
```

Verify the setting loaded:

```bash
python -c "from app.core.config import settings; print('ENABLE_AKSHARE:', settings.enable_akshare)"
# Expected: ENABLE_AKSHARE: True
```

---

## Step 2 — API Validation for Representative Stocks

Run against all three representative stocks: **600519** (贵州茅台), **000725** (京东方A), **600186** (莲花控股).

For each stock and each module, check:

| Check | Expected |
|---|---|
| HTTP status | 200 |
| `partial` | False (if AkShare returned rows) or True with `reasons` (if AkShare also empty) |
| `data.rows` | Non-empty list when AkShare has data |
| `source.actual` | `"akshare"` (not `"tushare"`) |
| `source.akshare_enabled` | `true` |
| `errors[]` | Empty when rows present |
| No Tushare fields missing | Verify row keys match panel schema |

Modules to validate:

```bash
# For each of 600519, 000725, 600186:
GET /api/v1/stocks/CN/{symbol}/fundamentals/modules/valuation
GET /api/v1/stocks/CN/{symbol}/fundamentals/modules/growth
GET /api/v1/stocks/CN/{symbol}/fundamentals/modules/profitability
GET /api/v1/stocks/CN/{symbol}/fundamentals/modules/cashflow_quality
GET /api/v1/stocks/CN/{symbol}/fundamentals/modules/asset_structure
GET /api/v1/stocks/CN/{symbol}/fundamentals/modules/solvency
GET /api/v1/stocks/CN/{symbol}/fundamentals/modules/operation_capability
GET /api/v1/stocks/CN/{symbol}/fundamentals/modules/dupont
```

---

## Step 3 — Field Schema Parity Check

For each module that returns rows via AkShare, verify the row keys match what the frontend panels expect.

### Valuation panel expected fields
`pe_ttm`, `pb`, `ps_ttm`, `dv_ttm`, `total_mv`, `circ_mv`, `close`

### Growth panel expected fields
`end_date`, `revenue`, `revenue_yoy`, `net_profit`, `net_profit_yoy`, `basic_eps`

### Profitability panel expected fields
`end_date`, `gross_profit_margin`, `net_profit_margin`, `roe`, `roa`, `roic`

### Asset Structure panel expected fields
`end_date`, `total_assets`, `fixed_assets`, `current_assets`, `intangible_assets`

### Solvency panel expected fields
`end_date`, `current_ratio`, `quick_ratio`, `debt_to_assets`, `interest_coverage`

If any expected field is absent in AkShare output:
- Note the gap
- Verify the frontend panel renders `—` for null values (not crashes)
- Document as a known field-gap in this plan

---

## Step 4 — Source Attribution Check

Verify the response correctly identifies AkShare as the data source:

```json
"source": {
  "primary": "tushare",
  "fallback": "akshare",
  "akshare_enabled": true,
  "actual": "akshare"
}
```

The `source.actual` field must be `"akshare"` — not `"tushare"` — when data was retrieved via fallback. This ensures the DataSourceBanner can display the correct attribution.

---

## Step 5 — DataSourceBanner Rendering Check

With `ENABLE_AKSHARE=true` and AkShare returning rows:

1. Open Company Tab for 600519
2. Verify DataSourceBanner **does not** show `no_token` or `etl_missing`
3. If AkShare only partially fills a module, verify:
   - `partial=True` in envelope
   - `reasons[]` populated with specific missing-field explanation
   - DataSourceBanner shows `generic` classification, not `no_token`
4. Verify disclaimer text does not misrepresent AkShare data as official Tushare Pro data

---

## Step 6 — Panel Rendering Spot Check (Frontend)

For 600519 with AkShare enabled:

| Panel | Check |
|---|---|
| Valuation | PE/PB chart renders with real numbers |
| Growth | Revenue bars show YoY comparison |
| Profitability | Gross/net margin line chart visible |
| Cashflow Quality | Ratio table rows present |
| null values | Display as `—` (not "null", not blank crash) |
| Partial panels | Show reason chip, not white space |

---

## Step 7 — Compliance Re-Check

Verify with AkShare rows present, the AI SummaryStrip:
1. Still runs through ReviewAgent
2. Still cannot output investment advice (buy/sell/target price)
3. `disclaimer` field still present in every AI output
4. `review.review_status` is `approved` or `revised`, not `rejected` (unless legitimately rejected)

---

## Step 8 — Disable AkShare After Validation

After completing Steps 1–7, **revert `ENABLE_AKSHARE` to false** for production:

```bash
# backend/.env
ENABLE_AKSHARE=false
```

Document the validation findings in a follow-up section of this file.

---

## Step 9 — Production Activation Criteria

AkShare may be activated in production only when **all** of the following are true:

- [ ] All 8 modules return rows for 600519 / 000725 / 600186
- [ ] Field schema parity verified for all panels (or gaps documented and handled)
- [ ] `source.actual = "akshare"` correctly set
- [ ] DataSourceBanner shows correct attribution (not `no_token`)
- [ ] No panel crashes on null/missing AkShare fields
- [ ] AI compliance re-check passed with real rows
- [ ] Data freshness verified (AkShare data ≤ 1 business day old)
- [ ] A disclaimer is added to the frontend that data source is AkShare (community data, no SLA)
- [ ] Legal/compliance review of AkShare terms of use completed

Until all criteria are met, production remains `ENABLE_AKSHARE=false`.

---

## Validation Findings (to be filled after running)

| Module | 600519 rows | 000725 rows | 600186 rows | Field parity | Notes |
|---|---|---|---|---|---|
| valuation | — | — | — | — | pending |
| growth | — | — | — | — | pending |
| profitability | — | — | — | — | pending |
| cashflow_quality | — | — | — | — | pending |
| asset_structure | — | — | — | — | pending |
| solvency | — | — | — | — | pending |
| operation_capability | — | — | — | — | pending |
| dupont | — | — | — | — | pending |

**Overall AkShare validation status:** ⏳ Pending  
**Recommended for production:** No — pending validation completion
