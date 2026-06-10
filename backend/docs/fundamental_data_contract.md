# Fundamental Data Contract

## Overview

`GET /api/v1/stocks/{market}/{symbol}/fundamentals` returns a structured snapshot of a stock's
fundamental data. This document defines every field, its unit, data source, and the phase in which
it was introduced.

The endpoint **always returns HTTP 200** with a well-formed JSON body. Fields that cannot be
fetched are `null`; they are also listed in `data_quality.missing_fields`. The endpoint never
returns HTTP 5xx due to a data-source failure.

---

## Response Structure

```json
{
  "market": "CN",
  "symbol": "600519",
  "company": { ... },
  "valuation": { ... },
  "profitability": { ... },
  "growth": { ... },
  "financial_health": { ... },
  "data_quality": { ... }
}
```

---

## Field Reference

### `company`

| Field | Type | Unit | Phase | CN Source | HK Source |
|---|---|---|---|---|---|
| `name` | string \| null | — | 1 | AkShare `stock_zh_a_spot_em` → `名称`; fallback: `quote_optional` | `quote_optional` (Tencent HK) |
| `industry` | string \| null | — | **3** | `stock_individual_info_em` | TBD |
| `business_summary` | string \| null | — | **3** | TBD | TBD |

### `valuation`

| Field | Type | Unit | Phase | CN Source | HK Source |
|---|---|---|---|---|---|
| `pe` | float \| null | — (倍) | 1 | AkShare `stock_zh_a_spot_em` → `市盈率-动态` | null (Phase 2) |
| `pb` | float \| null | — (倍) | 1 | AkShare `stock_zh_a_spot_em` → `市净率` | null (Phase 2) |
| `ps` | float \| null | — (倍) | **3** | TBD | TBD |
| `market_cap` | float \| null | CNY / HKD (元) | 1 | yfinance `fast_info.market_cap` (optional) | yfinance (optional) |
| `market_cap_unit` | string \| null | — | 1 | `"CNY"` when available | `"HKD"` when available |
| `dividend_yield` | float \| null | % | **3** | TBD | TBD |

### `profitability`

| Field | Type | Unit | Phase | CN Source | HK Source |
|---|---|---|---|---|---|
| `roe` | float \| null | **%** | **2** | AkShare THS `stock_financial_abstract_ths` → `净资产收益率` | null |
| `gross_margin` | float \| null | **%** | **2** | AkShare THS `stock_financial_abstract_ths` → `销售毛利率` | null |
| `net_margin` | float \| null | **%** | **2** | AkShare THS `stock_financial_abstract_ths` → `销售净利率` | null |

> **Unit note:** All percentage fields use the numeric percentage value.
> `roe = 54.27` means 54.27 %, **not** 0.5427.

### `growth`

| Field | Type | Unit | Phase | CN Source | HK Source |
|---|---|---|---|---|---|
| `revenue_growth_yoy` | float \| null | **%** | **2** | AkShare THS `stock_financial_abstract_ths` → `营业总收入同比增长率` | null |
| `net_profit_growth_yoy` | float \| null | **%** | **2** | AkShare THS `stock_financial_abstract_ths` → `净利润同比增长率` | null |

### `financial_health`

| Field | Type | Unit | Phase | CN Source | HK Source |
|---|---|---|---|---|---|
| `debt_ratio` | float \| null | **%** | **2** | AkShare THS `stock_financial_abstract_ths` → `资产负债率` | null |
| `operating_cashflow` | float \| null | **元 CNY** (raw yuan) | **2** | AkShare THS `stock_financial_cash_ths` → `*经营活动产生的现金流量净额` | null |

> **Unit note:** `operating_cashflow` is in raw yuan (CNY).
> Example: `61522000000.0` = 615.22亿元 = approximately ¥61.5B.

### `data_quality`

| Field | Type | Description |
|---|---|---|
| `provider` | string \| null | Primary provider used for this snapshot |
| `data_sources` | object | Maps each filled field path to its data source key |
| `missing_fields` | array[string] | Field paths that were expected but unavailable |
| `stale` | bool | `true` when returning a past-TTL cached snapshot |
| `message` | string \| null | Human-readable note about partial failures |
| `latest_report_date` | string \| null | ISO date of the most recent financial report period (e.g. `"2025-12-31"`) |

#### `data_sources` key values

| Value | Meaning |
|---|---|
| `akshare_spot_em` | AkShare `stock_zh_a_spot_em()` — real-time quote (daily refresh) |
| `akshare_ths_financial_abstract` | AkShare `stock_financial_abstract_ths()` — THS quarterly financial summary |
| `akshare_ths_cash_flow` | AkShare `stock_financial_cash_ths()` — THS quarterly cash flow statement |
| `yfinance_fast_info` | yfinance `fast_info.market_cap` — optional, may fail |
| `quote_optional` | Internal quote fallback chain (Tencent / Sina / stale) |

---

## Data Update Frequency

| Field Group | Source Update Frequency | Cache TTL |
|---|---|---|
| `company.name`, `valuation.pe/pb` | Real-time (intraday) | 3600s (1 hour) — inherited from snapshot TTL |
| `profitability`, `growth`, `financial_health` | Quarterly (报告期) | 3600s (1 hour) |
| `valuation.market_cap` | Real-time via yfinance | 3600s (optional, may be null) |

> The entire fundamentals snapshot shares a single 3600-second TTL.
> pe/pb change daily with price, but an hourly staleness is acceptable for fundamentals snapshots.
> Real-time pe/pb are available via `GET /stocks/{market}/{symbol}/quote` (60s TTL).

---

## Parsing Rules for THS String Values

All `stock_financial_abstract_ths` and `stock_financial_cash_ths` columns return `object` dtype
(strings). The internal `_parse_ths_value()` function applies these rules:

| Raw String | Parsed Value | Notes |
|---|---|---|
| `"54.27%"` | `54.27` | Strip `%`, keep as-is |
| `"615.22亿"` | `61522000000.0` | ×10⁸ (亿 → yuan) |
| `"1.23万"` | `12300.0` | ×10⁴ (万 → yuan) |
| `"False"` | `null` | THS sentinel for missing data |
| `""` / `"—"` / `"-"` | `null` | Empty or dash |
| Parse error | `null` | Never raises exception |

---

## `latest_report_date` Semantics

`data_quality.latest_report_date` is the `报告期` value from the most recent row returned by
`stock_financial_abstract_ths()`, sorted descending by date.

**Critical rules for consumers (especially FundamentalAnalystAgent):**

1. The date may be a **quarterly report** (Q1/Q3: `YYYY-03-31` / `YYYY-09-30`),
   a **semi-annual** (`YYYY-06-30`), or an **annual** (`YYYY-12-31`).
2. Do **not** assume the data represents full-year performance.
   - `2026-03-31` = Q1 2026 only — roughly 3 months of data
   - `2025-12-31` = full-year 2025 — complete annual data
3. Growth rates (`revenue_growth_yoy`, `net_profit_growth_yoy`) are always **year-over-year**
   vs. the same period one year prior. They are internally consistent regardless of report type.
4. `operating_cashflow` from `stock_financial_cash_ths` covers the period **from the fiscal year
   start to the report date** (累计值), not just that quarter.
5. Agents must **disclose the report date** in every analysis and must not use "全年表现" or
   "annual performance" phrasing unless `latest_report_date` ends in `12-31`.

---

## Agent Usage Boundary (FundamentalAnalystAgent)

When `FundamentalAnalystAgent` calls this endpoint, the following rules are **mandatory**:

### What the Agent MUST do

- **Disclose `latest_report_date`** at the top of every report.
  Write: "以下分析基于 `{latest_report_date}` 报告期数据。"
- **Check each field before using it.** A `null` value means the data was unavailable from
  all sources, not that the metric is zero or unknown.
- **Report `missing_fields` honestly.** For each field in `missing_fields`, state explicitly
  that it is "数据不足，暂不评估" — do not skip it silently.
- **Cite `data_sources`** for any field used in analysis (e.g. "来源：同花顺季度摘要").
- **Use correct units.** Percentage fields (`roe`, `gross_margin`, etc.) are already in
  percentage form. Do not re-multiply or divide.

### What the Agent MUST NOT do

| Prohibition | Reason |
|---|---|
| Invent values for `null` fields | No data source returned a value — any guess is fabrication |
| Judge PE/PB valuation if `valuation.pe` or `valuation.pb` is `null` | No basis for valuation conclusion |
| Describe industry, sector, or business model if `company.industry` / `company.business_summary` is `null` | Phase 3 not implemented; no data |
| Call results "全年表现" unless `latest_report_date` ends in `12-31` | Quarterly data ≠ annual data |
| Use `operating_cashflow` without noting it is cumulative YTD (累计) | Misrepresents the number |
| Give directional investment recommendations | Beyond scope of fundamental data analysis |
| Compare to industry average without actual peer data | Industry data not in this snapshot |
| Present stale data as current without noting `data_quality.stale = true` | Misleading timing |

### HK-specific restrictions (Phase 2)

For HK stocks, `profitability`, `growth`, and `financial_health` fields are all `null`.
The Agent must not:
- Describe ROE, margins, or cash flow for HK stocks (no data source)
- Claim the stock is "financially healthy" or "growing rapidly" without data
- Reference any financial ratio that is `null` in the response

The Agent may only describe:
- `company.name` (if available)
- `valuation.pe / pb` (Phase 3 planned — currently null for HK)
- Boilerplate data-unavailability note

---

## Phase Roadmap

| Phase | New Fields | Data Sources |
|---|---|---|
| **Phase 1** (done) | `company.name`, `valuation.pe/pb/market_cap` | AkShare spot, quote_optional, yfinance |
| **Phase 2** (done) | `profitability.*`, `growth.*`, `financial_health.*` | AkShare THS financial_abstract, cash_flow |
| **Phase 3** (planned) | `company.industry/business_summary`, `valuation.ps/dividend_yield` | `stock_individual_info_em`, yfinance `Ticker.info` |
| **Phase 4** (planned) | HK `pe/pb/profitability/growth` | FUTU OpenAPI / AkShare HK financial reports |

---

## Error Handling Guarantees

1. **HTTP 200 always** — data-source failures do not produce HTTP 5xx.
2. **`null` + `missing_fields`** — every unavailable field is `null` and listed in
   `data_quality.missing_fields`.
3. **`stale` fallback** — if the live fetch fails but a cached snapshot exists (any age),
   it is returned with `data_quality.stale = true`.
4. **Partial fill** — if the quote fetch succeeds but the financial report fetch fails,
   `name/pe/pb` are filled and the financial fields are `null` in `missing_fields`.
5. **No invented data** — values are never estimated or defaulted from industry averages.

---

## Example Response (CN/600519, Phase 2, normal case)

```json
{
  "market": "CN",
  "symbol": "600519",
  "company": {
    "name": "贵州茅台",
    "industry": null,
    "business_summary": null
  },
  "valuation": {
    "pe": 28.5,
    "pb": 12.3,
    "ps": null,
    "market_cap": null,
    "market_cap_unit": null,
    "dividend_yield": null
  },
  "profitability": {
    "roe": 33.51,
    "gross_margin": 91.97,
    "net_margin": 49.55
  },
  "growth": {
    "revenue_growth_yoy": 15.66,
    "net_profit_growth_yoy": 15.38
  },
  "financial_health": {
    "debt_ratio": 17.51,
    "operating_cashflow": 61522000000.0
  },
  "data_quality": {
    "provider": "akshare",
    "data_sources": {
      "company.name":                      "akshare_spot_em",
      "valuation.pe":                      "akshare_spot_em",
      "valuation.pb":                      "akshare_spot_em",
      "profitability.roe":                 "akshare_ths_financial_abstract",
      "profitability.gross_margin":        "akshare_ths_financial_abstract",
      "profitability.net_margin":          "akshare_ths_financial_abstract",
      "growth.revenue_growth_yoy":         "akshare_ths_financial_abstract",
      "growth.net_profit_growth_yoy":      "akshare_ths_financial_abstract",
      "financial_health.debt_ratio":       "akshare_ths_financial_abstract",
      "financial_health.operating_cashflow": "akshare_ths_cash_flow"
    },
    "missing_fields": [],
    "stale": false,
    "message": null,
    "latest_report_date": "2025-12-31"
  }
}
```
