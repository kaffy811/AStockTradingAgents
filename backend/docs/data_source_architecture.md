# Stock Data Source Architecture

## Overview

The stock data layer provides real-time quotes and historical OHLCV candlestick data for A-share (CN) and Hong Kong (HK) equities. It is organised as a **service → provider** hierarchy:

```
Router (stocks.py)
  └── StockDataService (stock_data_service.py)
        ├── Provider chain (ordered fallback)
        ├── StockCacheService (in-memory TTL + stale store)
        └── QuoteResult / KlineResult (typed return objects)
```

All business logic lives in `StockDataService`. The router is thin: it calls `get_quote()` / `get_kline()`, reads `http_status` from the result, and returns a `JSONResponse`.

---

## Provider Inventory

| Provider class | Module | Markets | Data type |
|---|---|---|---|
| `EastmoneyDirectProvider` | `eastmoney_provider.py` | CN | Quote |
| `EastmoneyKlineProvider` | `eastmoney_provider.py` | CN | Kline |
| `SinaQuoteProvider` | `sina_provider.py` | CN | Quote |
| `TencentQuoteProvider` | `tencent_provider.py` | CN, HK | Quote |
| `TencentKlineProvider` | `tencent_provider.py` | CN, HK | Kline |
| `AkShareStockDataProvider` | `akshare_provider.py` | CN, HK | Quote + Kline |
| `YFinanceStockDataProvider` | `yfinance_provider.py` | (bench only) | Quote + Kline |
| `BaoStockDataProvider` | `baostock_provider.py` | — | Stub / future |

---

## Quote Request Chain

### CN A-share quote

```
GET /stocks/CN/{symbol}/quote
  │
  ├─ 1. TTL cache hit (60 s)?  → return cached=true, HTTP 200
  │
  ├─ 2. EastmoneyDirectProvider  push2.eastmoney.com   (trust_env=False)
  ├─ 3. SinaQuoteProvider        hq.sinajs.cn          (gb18030, Referer required)
  ├─ 4. TencentQuoteProvider(CN) qt.gtimg.cn           (gb18030, proxies=_DIRECT)
  │
  ├─ 5. Stale cache found? → stale=true, HTTP 200
  └─ 6. No cache at all   → HTTP 503
```

### HK equity quote

```
GET /stocks/HK/{symbol}/quote
  │
  ├─ 1. TTL cache hit (60 s)?   → return cached=true, HTTP 200
  │
  ├─ 2. TencentQuoteProvider(HK) qt.gtimg.cn/q=hk00700 (gb18030, proxies=_DIRECT)
  ├─ 3. AkShareStockDataProvider
  │
  ├─ 4. Stale cache found? → stale=true, HTTP 200
  └─ 5. No cache at all   → HTTP 503
```

---

## Kline Request Chain

### CN A-share kline

```
GET /stocks/CN/{symbol}/kline?period=daily&adjust=qfq&limit=120
  │
  ├─ 1. TTL cache hit (600 s)?  → return cached=true, HTTP 200
  │
  ├─ 2. EastmoneyKlineProvider   push2his.eastmoney.com  (trust_env=False)
  ├─ 3. TencentKlineProvider(CN) web.ifzq.gtimg.cn       (proxies=_DIRECT)
  ├─ 4. AkShareStockDataProvider
  │
  ├─ 5. Stale cache found? → stale=true, HTTP 200
  └─ 6. No cache at all   → HTTP 503
```

### HK equity kline

```
GET /stocks/HK/{symbol}/kline?period=daily&adjust=qfq&limit=120
  │
  ├─ 1. TTL cache hit (600 s)?  → return cached=true, HTTP 200
  │
  ├─ 2. TencentKlineProvider(HK) web.ifzq.gtimg.cn/q=hk00700 (proxies=_DIRECT)
  ├─ 3. AkShareStockDataProvider
  │
  ├─ 4. Stale cache found? → stale=true, HTTP 200
  └─ 5. No cache at all   → HTTP 503
```

---

## Response Envelope Fields

### `fallback_chain`

An ordered list of attempts made during the request. Each entry is:

```json
{"source": "eastmoney", "status": "ok"}
{"source": "sina",      "error": "Connection aborted"}
```

Use this for debugging which provider ultimately served the data, or why earlier providers were skipped.

### `cached` vs `stale`

| Field | Meaning |
|---|---|
| `cached=true, stale=false` | Data served from in-memory TTL cache (fresh, within TTL window) |
| `cached=true, stale=true` | All live providers failed; data comes from the permanent stale store (last known good response, age unknown) |
| `cached=false, stale=false` | Fresh data from a live provider, just written to cache |

### HTTP 200 + `stale=true` vs HTTP 503

| Status | Meaning | Frontend action |
|---|---|---|
| `200 + stale=false` | Fresh data (live or TTL cache) | Display normally |
| `200 + stale=true` | All live sources down, showing last known value | Display with staleness warning |
| `503` | All sources failed AND no historical cache exists (first-ever call for this symbol or cache cleared) | Show error state |

The server never returns HTTP 502. HTTP 503 is only returned when there is genuinely no data to show.

---

## Standard Quote Fields

**CN A-share (e.g. 600519, provider = sina or tencent):**
```json
{
  "symbol":     "600519",
  "name":       "贵州茅台",
  "price":      1324.3,
  "open":       1321.9,
  "prev_close": 1323.0,
  "high":       1329.99,
  "low":        1318.0,
  "volume":     4325500,
  "amount":     5719170335.0,
  "change":     1.3,
  "change_pct": 0.1,
  "trade_time": "2026-05-19 15:00:02"
}
```

**HK equity (e.g. 700, provider = tencent_hk):**
```json
{
  "symbol":     "00700",
  "name":       "腾讯控股",
  "price":      460.0,
  "open":       449.2,
  "prev_close": 449.2,
  "high":       468.8,
  "low":        448.6,
  "volume":     33736701,
  "amount":     15552380252.51,
  "change":     10.8,
  "change_pct": 2.4
}
```

**Notes:**

- `amount` is **real 成交额** in CNY (CN) or HKD (HK). Both CN and HK now return real values via Tencent.
- `volume` unit is **shares (股)** for all quote responses.
- `trade_time` appears only from Sina CN provider.
- The `turnover` field has been **removed**. It was a duplicate of `volume` with a misleading name.

### Tencent Quote Field Parsing Details

Tencent's quote API returns a `~`-delimited string. CN and HK have different field layouts:

**CN (e.g. `sh600519`):**
| Index | Field | Notes |
|---|---|---|
| [3] | price | current price |
| [6] | volume | **in 手 (lots)** → multiply by 100 for shares |
| [35] | composite | `"price/volume_lots/amount_yuan"` — third segment is real 成交额 in 元 |

**HK (e.g. `hk00700`):**
| Index | Field | Notes |
|---|---|---|
| [3] | price | current price |
| [6] | volume | **in shares** (HK lot sizes vary) |
| [35] | price (duplicate) | not used |
| [36] | volume (duplicate) | not used |
| [37] | amount | real 成交额 in **港元 (HKD)** — direct value, no scaling |

---

## Standard Kline Fields

**Kline response envelope (top-level):**
```json
{
  "market":      "CN",
  "symbol":      "600519",
  "provider":    "tencent_kline",
  "period":      "daily",
  "adjust":      "qfq",
  "count":       50,
  "volume_unit": "lot",
  "data":        [...]
}
```

`volume_unit` is `"lot"` for CN (1 lot = 100 shares) and `"share"` for HK.

**Each bar:**
```json
{
  "date":                    "2026-05-19",
  "open":                    1321.9,
  "close":                   1324.3,
  "high":                    1329.99,
  "low":                     1318.0,
  "volume":                  43255.0,
  "amount":                  null,
  "amount_estimated":        5726940372.5,
  "amount_estimated_method": "avg_price_high_low_x_volume"
}
```

**Volume units:**

| Market | `volume_unit` | Bar `volume` unit | To get shares |
|---|---|---|---|
| CN | `"lot"` | 手 (lots) | `volume × 100` |
| HK | `"share"` | 股 (shares) | use directly |

**Amount fields:**

| Field | CN | HK |
|---|---|---|
| `amount` | `null` (Tencent kline API has no 成交额) | `null` |
| `amount_estimated` | `((high+low)/2) × volume × 100` 元 | `((high+low)/2) × volume` 港元 |
| `amount_estimated_method` | `"avg_price_high_low_x_volume"` | `"avg_price_high_low_x_volume"` |

`amount_estimated` is a rough estimate. It uses the bar's midprice — actual 成交额 depends on intraday price distribution. Use it only for relative comparison, not for precise money-flow analysis.

---

## `quote_from_kline` (Degraded Mode)

`_quote_from_kline()` in `stock_data_service.py` synthesises a quote-shaped dict from the last kline bar when all live quote sources fail but kline data is available. The result uses the same field names as a live quote, but several fields will be `null`:

```json
{
  "symbol":      "600519",
  "name":        null,
  "price":       1324.3,
  "open":        1321.9,
  "high":        1329.99,
  "low":         1318.0,
  "prev_close":  null,
  "volume":      43255.0,
  "amount":      null,
  "change":      null,
  "change_pct":  null,
  "trade_date":  "2026-05-19",
  "source_note": "quote_from_kline"
}
```

Frontend: check `source_note == "quote_from_kline"` to detect this degraded mode and display an appropriate indicator.

---

## Known Network Issues

### Eastmoney domains currently unreachable

`push2.eastmoney.com` and `push2his.eastmoney.com` are blocked in the local development environment (Clash HTTP proxy at `127.0.0.1:7890` drops the HTTPS CONNECT tunnel to Eastmoney CDN nodes, even with `session.trust_env = False`).

**Impact:** Eastmoney is first in the CN fallback chain but always fails silently. Sina (quote) and Tencent (kline) become the effective primaries.

**Fix:** Add a Clash rule to bypass the proxy for Eastmoney domains:
```yaml
# In Clash rules (before MATCH):
- DOMAIN-SUFFIX,eastmoney.com,DIRECT
```

After this rule is added, Eastmoney will become the true primary for CN quote and CN kline, improving latency and data freshness.

### yfinance removed from core chains

Yahoo Finance (`finance.yahoo.com`) returns HTTP 429 (rate-limited) for both CN and HK requests in the current environment. yfinance was removed from the CN quote, HK quote, CN kline, and HK kline primary chains to avoid 10–30 s timeout delays.

The `YFinanceStockDataProvider` class remains in the codebase with a CN-quote circuit breaker (10-minute freeze on 429). It can be re-added to a fallback position if Yahoo rate limits are resolved (e.g., via a rotating proxy or authenticated Yahoo Finance API access).

---

## Cache Configuration

| Data type | TTL | Stale store |
|---|---|---|
| Quote | 60 seconds | Permanent (until process restart) |
| Kline | 600 seconds (10 min) | Permanent (until process restart) |

Cache is in-process memory (`dict`). It resets on server restart. To persist across restarts, replace `stock_cache_service.py` with a Redis backend — the public API (`get_quote_cache`, `set_quote_cache`, `get_quote_stale`, etc.) is unchanged.

---

## Suggestions for Future Extensions

### AllTick or paid real-time provider

Insert a new class implementing `BaseStockDataProvider` and prepend it to the relevant provider list in `StockDataService._get_quote_cn()` / `_get_quote_hk()`. No other changes are required.

### Database / time-series provider

A `DatabaseKlineProvider` could serve historical bars from a local PostgreSQL or TimescaleDB table, acting as a very fast cache layer before hitting external APIs. Place it first in the kline chain with a live provider as fallback for missing date ranges.

### Health-check endpoint

Expose `GET /stocks/health` that calls each provider with a known symbol (e.g., CN/600519) and returns a per-provider status map. Useful for uptime monitoring and alerting when a primary source degrades before users notice.

```json
{
  "eastmoney_quote": "unreachable",
  "sina_quote":      "ok",
  "tencent_quote":   "ok",
  "tencent_kline":   "ok",
  "akshare":         "ok"
}
```

### Per-provider timeout and retry configuration

Currently timeouts are hardcoded in each provider (8 s quote, 12 s kline). Consider centralising them in `app/core/config.py` under a `[stock]` section so they can be tuned per environment without touching provider code.
