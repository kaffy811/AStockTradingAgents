# Data Field Contract

This document defines the stable field contracts for quote and kline responses.  
Frontend and agent code should be written against this contract, not against any specific provider's raw output.

---

## Quote Response Contract

### Envelope

```typescript
interface QuoteResponse {
  market:         string;          // "CN" | "HK"
  symbol:         string;          // as requested
  provider:       string;          // which source served this response
  cached:         boolean;         // true = served from in-memory TTL cache
  stale:          boolean;         // true = all live sources failed, showing last known value
  fallback_chain: FallbackEntry[]; // ordered list of provider attempts
  message:        string | null;   // human-readable status note (present when stale or 503)
  data:           QuoteData;
}
```

### `QuoteData` field contract

| Field | Type | Always present | Notes |
|---|---|---|---|
| `symbol` | `string` | Yes | Exchange-normalised (e.g. `"00700"` for HK) |
| `name` | `string \| null` | Usually | Company name in Chinese. Null in `quote_from_kline` mode. |
| `price` | `number` | Yes | Latest trade price. Use this as the primary display price. |
| `open` | `number \| null` | Usually | Today's opening price |
| `prev_close` | `number \| null` | Usually | Previous session close. Null in `quote_from_kline` mode. |
| `high` | `number \| null` | Usually | Today's session high |
| `low` | `number \| null` | Usually | Today's session low |
| `volume` | `number \| null` | Usually | Unit: shares (股). See volume unit section. |
| `amount` | `number \| null` | Usually | **Real 成交额**, unit: CNY (CN) or HKD (HK). See amount section. |
| `change` | `number \| null` | Usually | Price change vs prev_close. Null in `quote_from_kline` mode. |
| `change_pct` | `number \| null` | Usually | Change percentage. Null in `quote_from_kline` mode. |

**Optional fields that may appear depending on provider:**

| Field | Provider | Type | Notes |
|---|---|---|---|
| `trade_time` | Sina CN | `string` | `"YYYY-MM-DD HH:MM:SS"` — last tick timestamp |
| `trade_date` | `quote_from_kline` only | `string` | `"YYYY-MM-DD"` — date of the kline bar used |
| `source_note` | `quote_from_kline` only | `"quote_from_kline"` | Signals degraded non-realtime data |

> **Note:** The `turnover` field that previously appeared in Tencent HK quote responses has been removed. It was a duplicate of the `volume` field with a misleading name. Do not use or rely on `turnover` in any context.

---

## Kline Response Contract

### Envelope

```typescript
interface KlineResponse {
  market:         string;
  symbol:         string;
  provider:       string;
  period:         string;          // "daily" | "weekly" | "monthly"
  adjust:         string;          // "" | "qfq" | "hfq"
  count:          number;          // == data.length, == requested limit (guaranteed)
  volume_unit:    string;          // "lot" (CN) or "share" (HK) — see volume unit section
  cached:         boolean;
  stale:          boolean;
  fallback_chain: FallbackEntry[];
  message:        string | null;
  data:           KlineBar[];
}
```

### `KlineBar` field contract

| Field | Type | Always present | Notes |
|---|---|---|---|
| `date` | `string` | Yes | `"YYYY-MM-DD"` |
| `open` | `number \| null` | Yes | Adjusted if `adjust=qfq/hfq` |
| `close` | `number \| null` | Yes | Adjusted if `adjust=qfq/hfq` |
| `high` | `number \| null` | Yes | Adjusted if `adjust=qfq/hfq` |
| `low` | `number \| null` | Yes | Adjusted if `adjust=qfq/hfq` |
| `volume` | `number \| null` | Yes | Unit defined by `volume_unit` in envelope |
| `amount` | `number \| null` | No | **Real 成交额**. Always `null` for Tencent kline (API does not return it). |
| `amount_estimated` | `number \| null` | Yes | **Estimated 成交额**. See estimation section. `null` if high/low/volume missing. |
| `amount_estimated_method` | `string \| null` | Yes | Estimation method identifier. `null` if `amount_estimated` is `null`. |

**Additional fields from Eastmoney kline (when reachable):**

| Field | Type | Notes |
|---|---|---|
| `change_pct` | `number \| null` | 涨跌幅 |
| `change` | `number \| null` | 涨跌额 |

---

## Amount (成交额) Contract

### `amount` — real 成交额

`amount` holds the **real, exchange-reported transaction value** for the period.

| Source | CN amount | HK amount |
|---|---|---|
| Sina quote | Full CNY value (元) ✓ | — (CN only) |
| Tencent CN quote | Full CNY value (元) ✓ — parsed from field[35] composite `price/vol/amount` | — |
| Tencent HK quote | — | Full HKD value (港元) ✓ — parsed from field[37] |
| Eastmoney kline | Full CNY value (元) ✓ | — (CN only) |
| Tencent kline | `null` — API does not return 成交额 | `null` |
| AkShare | Provided if API returns it | Provided if API returns it |

**Units:**
- CN `amount` is in **元 (CNY)**
- HK `amount` is in **港元 (HKD)**

**Rule:** Only real, exchange-sourced values are written to `amount`. Estimated values are never written to `amount`.

### `amount_estimated` — estimated 成交额

When real `amount` is unavailable (e.g. Tencent kline), an estimated value is provided separately.

**Estimation formula:**

```
amount_estimated = avg_price × volume_in_shares

where:
  avg_price        = (high + low) / 2
  volume_in_shares = volume * 100   (CN: volume is in lots)
                   = volume          (HK: volume is in shares)
```

**`amount_estimated_method` value:** `"avg_price_high_low_x_volume"`

**Characteristics:**
- This is a rough estimate based on the mid-price of the bar's range
- Actual 成交额 is weighted by intraday price distribution, which this formula does not capture
- Error margin grows with intraday volatility
- `amount_estimated = null` when any of `high`, `low`, or `volume` is missing

**Critical constraint — Agent analysis:**

> When using `amount_estimated`, the analysis **must** state: "此成交额为估算值，仅供参考，不作为精确资金流向依据"
>
> Do NOT draw strong conclusions from `amount_estimated`, such as:
> - "资金大幅流入" / "资金大幅流出"
> - Precise turnover ranking
> - Absolute liquidity conclusions

---

## Volume Unit Contract

Volume units differ by market and data type.

| Context | Unit | Value |
|---|---|---|
| `KlineResponse.volume_unit` when market=CN | `"lot"` | 1 lot = 100 shares |
| `KlineResponse.volume_unit` when market=HK | `"share"` | already in shares |
| CN kline `bar.volume` | lots (手) | divide by 1, multiply by 100 to get shares |
| HK kline `bar.volume` | shares (股) | use directly |
| CN quote `data.volume` | shares (股) | use directly |
| HK quote `data.volume` | shares (股) | use directly |

**Summary rule for frontend:**

```typescript
// Convert kline volume to shares for display
function klineVolumeToShares(volume: number, volumeUnit: string): number {
  return volumeUnit === "lot" ? volume * 100 : volume;
}

// Quote volume is always in shares — no conversion needed
function quoteVolumeShares(volume: number): number {
  return volume;
}
```

**Why the difference?**  
Tencent's kline API returns CN volume in 手 (trading lots). HK stocks have variable lot sizes, so Tencent returns HK kline volume in raw shares.

---

## `turnover` Field — Deprecated

The `turnover` field **no longer appears** in any response. It was previously present in Tencent HK quote responses where it contained the same value as `volume` (a field[36] duplicate), making it semantically meaningless.

- Do not reference `turnover` in frontend code
- Do not reference `turnover` in agent prompts
- Do not interpret `turnover` as 换手率 (turnover rate) or 成交额

---

## `quote_from_kline` Non-Realtime Mode

When all live quote sources fail but kline data is available, the service synthesises a quote from the last kline bar. This is a best-effort degraded mode.

**Detection:** `data.source_note === "quote_from_kline"`

**Fields that are always null in this mode:**
- `name`
- `prev_close`
- `change`
- `change_pct`
- `amount`

**Fields that are populated:**
- `price` — equal to last bar's `close`
- `open`, `high`, `low`, `volume` — from the last kline bar
- `trade_date` — the date of the kline bar (not a live timestamp)

**Frontend guidance:** When `source_note === "quote_from_kline"`, show a banner or tooltip indicating the price is end-of-day from the last available session, not a real-time tick.

---

## `fallback_chain` Contract

```typescript
interface FallbackEntry {
  source: string;          // provider name
  status?: "ok";           // present if this provider succeeded
  error?:  string;         // present if this provider failed (error message)
}
```

The array is ordered chronologically. The successful provider is the last entry with `"status": "ok"`.

Example — Eastmoney failed, Sina succeeded:
```json
[
  {"source": "eastmoney", "error": "Connection aborted ('', RemoteDisconnected(...))"},
  {"source": "sina",      "status": "ok"}
]
```

---

## HTTP Status Semantics

| HTTP status | `stale` | Meaning |
|---|---|---|
| `200` | `false` | Fresh data (live provider or valid TTL cache) |
| `200` | `true` | All live sources down; last-known-good value returned |
| `400` | — | Invalid request parameter (bad market, bad adjust, etc.) |
| `401/403` | — | Missing or invalid authentication token |
| `422` | — | FastAPI validation error (e.g. limit out of 1–500 range) |
| `503` | — | All sources failed AND no historical cache exists |

The server will never return `502`. If you see `502`, it originates from a reverse proxy (Nginx, Caddy, etc.) in front of the FastAPI process — investigate the proxy layer.

---

## Frontend Usage Notes

1. **Always check `stale` before displaying prices.** When `stale=true`, show a visual indicator (grey badge, tooltip "数据可能延迟") so users know the price is not real-time.

2. **Do not hardcode expected provider names.** The `provider` field is informational. The active provider can change silently as sources come up and down.

3. **`count` is guaranteed to equal `limit`.** The kline endpoint always returns exactly the requested number of bars (or fewer if the symbol has less history than requested). Do not re-count `data.length`.

4. **Use `close` not `price` for kline charting.** The kline `close` field is the canonical closing price for each bar. The quote `price` is the last tick price.

5. **Do not parse `trade_time` for precise ordering.** Use `date` from kline bars for time-axis ordering. `trade_time` from Sina quote is a display string, not an ISO timestamp.

6. **Kline volume unit is in the envelope, not the bar.** Read `KlineResponse.volume_unit` once per response, then apply to all bars. Do not hardcode `"lot"` or `"share"` by market name — use the field.

7. **Amount display priority:**
   - Use `amount` if non-null (real 成交额)
   - If `amount` is null, optionally display `amount_estimated`, but **label it** as "估算成交额"
   - If both are null, show "—"
   
   ```typescript
   const amountDisplay =
     bar.amount != null ? formatCurrency(bar.amount) :
     bar.amount_estimated != null ? `${formatCurrency(bar.amount_estimated)} (估算)` :
     "—";
   ```

8. **Do not use the `turnover` field.** It has been removed. Any code referencing it will receive `undefined`.

9. **Handle `503` gracefully.** This means the symbol has never been successfully fetched since the server started (or cache was cleared). Show an error state, not a loading spinner.

---

## Agent Analysis Notes

When building agents that analyse stock data:

1. **`amount` = real 成交额** — use for precise volume-price analysis, money flow, liquidity assessment.

2. **`amount_estimated` = rough estimate only** — suitable for relative comparison between bars (e.g. "volume was higher on day X"), not for absolute conclusions. Always disclose when using estimated values:
   > "以下成交额分析基于估算值（均价×成交量），仅供参考，不代表交易所真实成交数据。"

3. **CN kline `volume` is in lots (手)** — when reasoning about share count, multiply by 100. When reasoning about turnover (占流通盘比例), use the lot value consistently.

4. **HK kline `volume` is in shares (股)** — use directly.

5. **`quote.volume` is always in shares** — both CN and HK quote.

6. **Do not confuse `amount` (成交额, transaction value) with `volume` (成交量, share count).** These are fundamentally different metrics.
