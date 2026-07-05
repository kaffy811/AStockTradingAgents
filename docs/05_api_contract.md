# 05 API Contract — Fundamental Data Service (Phase 2D)

> Freeze date: 2026-07-05  
> Version: v1  
> Status: **Stable** — no breaking changes planned for Phase 3

---

## 1. API Overview

| Item | Value |
|------|-------|
| Base URL | `http://localhost:8000/api/v1` (dev) |
| Auth | Bearer token (Supabase JWT via `Authorization: Bearer <token>`) |
| Content-Type | `application/json` |
| Disclaimer Header | `X-Data-Disclaimer: For informational purposes only. Not investment advice. Invest at your own risk.` |
| Rate limiting | None (Phase 1–2); planned for Phase 3 |

---

## 2. DataEnvelope Top-Level Fields

Every successful or failed response from `/api/v1/stock/*/modules/*` and `/api/v1/stock/*/overview` returns a **DataEnvelope**:

| Field | Type | Description |
|-------|------|-------------|
| `market` | string | Market code: `CN`, `HK`, `US` |
| `symbol` | string | Stock symbol (e.g. `600519`) |
| `ts_code` | string | Tushare ts_code (e.g. `600519.SH`) |
| `module_key` | string | Canonical module identifier (e.g. `valuation`) |
| `module_name` | string | Chinese module name |
| `group` | string | Group name (e.g. `财务分析`). Added in Phase 2D. |
| `group_seq` | int | Group sort order 1–8. Added in Phase 2D. |
| `data` | object \| null | Module payload. `null` only if `errors` is non-empty and `partial=false`. |
| `errors` | array[string] | **Always an array** (never null). Empty when no errors. |
| `partial` | bool | `true` when `data` is non-null but some sub-fields failed. |
| `stale` | bool | `true` when data came from expired cache (source temporarily unavailable). |
| `generated_at` | string | ISO 8601 timestamp with +08:00 timezone. |
| `source` | object | Data source info (see below). |
| `meta` | object | Rendering contract (see below). Added in Phase 2D. |

### `source` sub-object

```json
{
  "primary": "tushare",
  "fallback": null,
  "akshare_enabled": false,
  "actual": "tushare"
}
```

| Field | Description |
|-------|-------------|
| `primary` | Primary data source (always `"tushare"`) |
| `fallback` | Fallback source if enabled (`"akshare"` or `null`) |
| `akshare_enabled` | Whether AkShare fallback is configured |
| `actual` | Which source was actually used for this response |

### `meta` sub-object (Phase 2D)

```json
{
  "render_type": "chart_table",
  "chart_type": "line",
  "unit_hints": {"pe_ttm": "倍", "change_pct": "%"},
  "field_labels": {"pe_ttm": "PE(TTM)", "change_pct": "涨跌幅"},
  "empty_state": "暂无数据"
}
```

| Field | Type | Values | Description |
|-------|------|--------|-------------|
| `render_type` | string | `metric_cards`, `chart_table`, `table`, `timeline`, `mixed`, `ai_card`, `placeholder` | Primary UI layout |
| `chart_type` | string | `line`, `bar`, `stacked_bar`, `area`, `pie`, `donut`, `radar`, `timeline`, `none` | ECharts chart type hint |
| `unit_hints` | object | `{field: unit}` | Append unit string to field values in display |
| `field_labels` | object | `{field: chinese_label}` | Use as column headers and metric card labels |
| `empty_state` | string | — | Message to show when `data` is null |

---

## 3. GET /api/v1/modules

### Request

```
GET /api/v1/modules
Authorization: Bearer <token>
```

No query parameters required.

### Response

HTTP 200 — array of module metadata objects.

Each entry includes all MODULE_CATALOG fields plus a computed `available` boolean.

```json
[
  {
    "seq": 1,
    "key": "snapshot",
    "name_zh": "基础信息与行情",
    "name_en": "Quote Snapshot",
    "phase": 1,
    "requires_llm": false,
    "cache_ttl": 60,
    "status": "available",
    "display": true,
    "alias_of": null,
    "group": "概览",
    "group_seq": 1,
    "render_type": "metric_cards",
    "chart_type": "none",
    "table_primary_key": null,
    "default_limit": 1,
    "supports_period": false,
    "supports_export": true,
    "field_labels": {"name": "公司名称", "price": "最新价"},
    "unit_hints": {"price": "元", "pe_ttm": "倍"},
    "description": "行情基础信息快照，含价格、市值、估值比率",
    "data_freshness": "daily",
    "disclaimer_type": "data_only",
    "available": true
  }
]
```

### Example curl

```bash
curl -s http://localhost:8000/api/v1/modules \
  -H "Authorization: Bearer $TOKEN" | jq '.[].key'
```

---

## 4. GET /api/v1/stock/{code}/overview

### Request

```
GET /api/v1/stock/{code}/overview
Authorization: Bearer <token>
```

| Parameter | Description |
|-----------|-------------|
| `code` | Stock code in any supported format (see §10) |

### Response

HTTP 200 — dict with keys `"snapshot"` and `"financial_summary"`, each being a full DataEnvelope.

```json
{
  "snapshot": { ... DataEnvelope ... },
  "financial_summary": { ... DataEnvelope ... }
}
```

### Example curl

```bash
curl -s http://localhost:8000/api/v1/stock/600519/overview \
  -H "Authorization: Bearer $TOKEN" | jq '.snapshot.data.price'
```

---

## 5. GET /api/v1/stock/{code}/modules/{module_id}

### Request

```
GET /api/v1/stock/{code}/modules/{module_id}
Authorization: Bearer <token>
```

| Parameter | Description |
|-----------|-------------|
| `code` | Stock code (any format) |
| `module_id` | Module key or alias (see §7) |

### Response

- HTTP 200 — DataEnvelope with `ok=true` (data may be partial)
- HTTP 503 — DataEnvelope with `ok=false`, `data=null`, `errors[0]` describes failure

```json
{
  "market": "CN",
  "symbol": "600519",
  "ts_code": "600519.SH",
  "module_key": "valuation",
  "module_name": "估值分位",
  "group": "财务分析",
  "group_seq": 2,
  "data": { "series": [...] },
  "errors": [],
  "partial": false,
  "stale": false,
  "generated_at": "2026-07-05T10:23:45+08:00",
  "source": { "primary": "tushare", "fallback": null, "akshare_enabled": false, "actual": "tushare" },
  "meta": {
    "render_type": "chart_table",
    "chart_type": "line",
    "unit_hints": {"pe_ttm": "倍", "pe_percentile": "%"},
    "field_labels": {"pe_ttm": "PE(TTM)", "pe_percentile": "PE历史分位"},
    "empty_state": "暂无数据"
  }
}
```

### Example curl

```bash
curl -s http://localhost:8000/api/v1/stock/600519.SH/modules/valuation \
  -H "Authorization: Bearer $TOKEN"
```

---

## 6. GET /api/v1/stocks/{market}/{symbol}/fundamentals/modules/{module_key}

Main route (Phase 1+), requires explicit market and symbol.

```
GET /api/v1/stocks/CN/600519/fundamentals/modules/valuation
```

Returns the same DataEnvelope structure. Note: `module_meta` is not yet wired into this route (Phase 3 task). The `group`, `group_seq`, and `meta` fields will use defaults until updated.

---

## 7. Module Alias Table

| Alias | Canonical Key |
|-------|--------------|
| `cashflow` | `cashflow_quality` |
| `quote` | `snapshot` |
| `quote_snapshot` | `snapshot` |
| `cashflow_health` | `cashflow_quality` |
| `growth_metrics` | `growth` |
| `profit_quality` | `profitability` |
| `operating_efficiency` | `operation_capability` |
| `industry_ranking` | `industry_rank` |
| `peer_rank` | `industry_rank` |
| `industry_position` | `industry_rank` |
| `dividend` | `dividend_history` |
| `holders` | `major_holders` |
| `shareholders` | `major_holders` |
| `events` | `announcements` |
| `forecast_rating` | `analyst_ratings` |
| `rating` | `analyst_ratings` |

---

## 8. errors / partial / stale Semantics

| Scenario | `errors` | `partial` | `stale` | `data` |
|----------|----------|-----------|---------|--------|
| Full success | `[]` | `false` | `false` | non-null |
| Partial (some fields failed) | `["field X missing: ..."]` | `true` | `false` | non-null |
| Stale cache (source down) | `[]` | `false` | `true` | non-null |
| Complete failure | `["reason"]` | `false` | `false` | `null` |
| Stale + partial | `["field X missing"]` | `true` | `true` | non-null |

Frontend rule: **Always check `data !== null` before rendering**. Show `errors` as a warning badge when `partial=true`. Show a stale indicator when `stale=true`.

---

## 9. source Field Semantics

The `source.actual` field indicates which data provider was used:

- `"tushare"` — Tushare Pro API (primary, requires token)
- `"akshare"` — AkShare (free fallback, if `ENABLE_AKSHARE=true` env var set)
- `"cache"` — Returned from Redis cache (stale=true implies this)

AkShare is disabled by default (`akshare_enabled=false`). Enable with env var `ENABLE_AKSHARE=true`.

---

## 10. Stock Code Format Support

| Input Format | Parsed as |
|-------------|-----------|
| `600519` | CN, 600519 |
| `600519.SH` | CN, 600519 |
| `000001.SZ` | CN, 000001 |
| `688981.SH` | CN, 688981 |
| `838030.BJ` | CN, 838030 |
| `00700.HK` | HK, 00700 |
| `700.HK` | HK, 00700 (zero-padded) |
| `AAPL` | US, AAPL |

---

## 11. Available Modules Table (19 modules as of Phase 2C)

| seq | key | group | render_type | data_freshness | description |
|-----|-----|-------|-------------|----------------|-------------|
| 1 | snapshot | 概览 | metric_cards | daily | 行情基础信息快照 |
| 2 | financial_summary | 概览 | metric_cards | quarterly | 最新财报核心数据汇总 |
| 3 | valuation | 财务分析 | chart_table | daily | 估值历史分位 |
| 4 | dupont | 财务分析 | chart_table | quarterly | 杜邦分解 |
| 5 | cashflow_quality | 财务分析 | chart_table | quarterly | 经营现金流质量 |
| 6 | growth | 财务分析 | chart_table | quarterly | 成长性趋势 |
| 7 | profitability | 财务分析 | chart_table | quarterly | 盈利质量 |
| 8 | expense_analysis | 财务分析 | chart_table | quarterly | 费用结构分析 |
| 9 | main_business | 财务分析 | table | quarterly | 主营业务构成 |
| 10 | income_statement | 财务分析 | table | quarterly | (legacy) 利润表 |
| 11 | asset_structure | 资产负债 | chart_table | quarterly | 资产结构 |
| 12 | solvency | 资产负债 | chart_table | quarterly | 偿债能力 |
| 13 | operation_capability | 资产负债 | chart_table | quarterly | 营运能力 |
| 14 | capital_occupation | 资产负债 | chart_table | quarterly | 资金占用分析 |
| 15 | balance_sheet | 资产负债 | table | quarterly | (legacy) 资产负债表 |
| 16 | industry_rank | 同行对比 | chart_table | daily | 行业排名分位 |
| 19 | major_holders | 股东分红 | table | quarterly | 十大股东及户数 |
| 20 | equity_structure | 股东分红 | metric_cards | daily | 股权结构快照 |
| 21 | dividend_history | 股东分红 | table | annual | 历史分红记录 |
| 22 | announcements | 事件观点 | timeline | daily | 近期业绩预告 |
| 23 | analyst_ratings | 事件观点 | mixed | daily | 业绩预期汇总（非机构评级）|

---

## 12. Example curl Commands

```bash
# 1. List all modules
curl http://localhost:8000/api/v1/modules

# 2. Get overview for 贵州茅台
curl http://localhost:8000/api/v1/stock/600519/overview

# 3. Get valuation module
curl http://localhost:8000/api/v1/stock/600519/modules/valuation

# 4. Use alias (dividend → dividend_history)
curl http://localhost:8000/api/v1/stock/600519/modules/dividend

# 5.港股 (HK)
curl http://localhost:8000/api/v1/stock/00700.HK/modules/snapshot

# 6. 美股 (US)
curl http://localhost:8000/api/v1/stock/AAPL/modules/snapshot

# 7. With auth token
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/v1/stock/600519/modules/industry_rank
```

---

## 13. Frontend Handling Recommendations

1. **Initialize module navigation** by calling `GET /api/v1/modules` once on app load. Use `group_seq` → `seq` sort order for sidebar rendering.

2. **Check `data !== null`** before any rendering. When `data=null`, show `meta.empty_state` string.

3. **Show stale indicator** (e.g. clock icon with tooltip "数据可能已过期") when `stale=true`.

4. **Show partial warning badge** when `partial=true`. Render `errors[0]` as tooltip on hover.

5. **Planned modules** have `render_type="placeholder"`. Render as a locked card with `description` text and a "敬请期待" message.

6. **analyst_ratings disclaimer**: Always render the `data.data_note` field prominently. Never label this module as "机构买入评级" — it is based on company self-disclosed performance forecast types only.

7. **unit_hints**: Append to displayed values (e.g. `28.5 倍`, `91.8 %`). Handle null values gracefully (display `—`).

8. **field_labels**: Use as table column headers and metric card labels. Fall back to field name if label not found.
