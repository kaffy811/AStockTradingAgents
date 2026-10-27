# Phase 6W-R1.8 — Provider Capability Matrix

**Generated:** 2026-08-12  
**Branch:** release/demo-staging  
**HEAD:** a542bc1  
**Purpose:** Establish which data providers can supply Company Overview six fields in production.  
**Status:** Read-only probe. No configuration changes made.

---

## 1. Provider Test Results

### Tushare Pro (Token: e81***, len=56)

All endpoints tested against production token from root `.env`:

| Endpoint | Result | Error |
|----------|--------|-------|
| `trade_cal` | **PERMISSION_DENIED** | 没有接口访问权限 |
| `stock_basic` | **PERMISSION_DENIED** | 没有接口访问权限 |
| `daily_basic` | **PERMISSION_DENIED** | 没有接口访问权限 |
| `fina_indicator` | **PERMISSION_DENIED** | 没有接口访问权限 |

**Classification:** Type C — Token valid (format correct, authentication accepted), no purchased API credits.

**Implication:** In `DATA_MODE=standard`, Tushare is tried first for every field. All calls will fail with `TushareAuthError`. The fallback chain is only activated if `ENABLE_AKSHARE=true`.

**Root cause:** The Tushare account (e81***) has not purchased any data credits. This is a **billing decision**, not a code defect.

---

### BaoStock (Free, no token required)

Test environment: local machine, direct connection.

| Field | BaoStock API | Test Result | Sample Value (600519) |
|-------|-------------|-------------|----------------------|
| Latest price (close) | `query_history_k_data_plus` fields=`close` | **PASS** | 1346.50 CNY |
| PE (TTM) | `query_history_k_data_plus` fields=`peTTM` | **PASS** | 20.35 倍 |
| PB (MRQ) | `query_history_k_data_plus` fields=`pbMRQ` | **PASS** | 6.21 倍 |
| Total market cap | Not available in kline data | **NULL** | — (needs share count × price) |
| ROE | `query_profit_data` roeAvg | **PASS** | 0.384283 → 38.43% |
| Dividend yield TTM | `query_dividend_data` dividCashPsBeforeTax | **PARTIAL** | computed ≈ 0.41% (requires calc) |

**BaoStock kline fallback limitations (from `quote_snapshot.py:fetch_baostock`):**
- `dv_ttm`: Returns `None` — BaoStock kline has no dividend data
- `total_mv`: Returns `None` — BaoStock kline has no share count

**UI graceful degradation:** `CompanyOverviewCards.vue`:
- `fmtMv(null)` → `'—'` ✅
- `fmtPct(null)` → `'—'` ✅
- No crash, no fabricated numbers

---

### AkShare (EastMoney-backed)

| Test | Local Machine Result | Expected in CN Production |
|------|---------------------|--------------------------|
| `stock_zh_a_spot_em()` | **FAIL** — ProxyError HTTPS EastMoney blocked | **LIKELY PASS** |

**Local machine limitation:** EastMoney HTTPS (port 443) is blocked at local proxy/firewall (same observation as R1.7).  
Production server in mainland China is expected to reach EastMoney directly.

**AkShare fields available (from prior staging tests and code review):**
- `最新价` → latest_price ✅
- `市盈率-动态` → pe_ttm ✅
- `市净率` → pb ✅
- `总市值` → total_mv (unit: CNY) ✅
- No direct ROE or dividend yield in spot data

---

## 2. Provider Capability Matrix

| Field | Tushare (standard) | BaoStock (free kline) | AkShare (free) | Production w/ current config | Production w/ target config |
|-------|--------------------|-----------------------|----------------|-------------------------------|------------------------------|
| latest_price | ❌ PERMISSION_DENIED | ✅ close | ✅ 最新价 | **NULL** | ✅ BaoStock kline |
| pe_ttm | ❌ PERMISSION_DENIED | ✅ peTTM | ✅ 市盈率-动态 | **NULL** | ✅ BaoStock kline |
| pb | ❌ PERMISSION_DENIED | ✅ pbMRQ | ✅ 市净率 | **NULL** | ✅ BaoStock kline |
| total_market_cap (total_mv) | ❌ PERMISSION_DENIED | ❌ not in kline | ✅ 总市值 | **NULL** | ❌ NULL (kline only) → ✅ if AkShare works |
| roe | ❌ PERMISSION_DENIED | ✅ roeAvg (profit_data) | ❌ not in spot | **NULL** | ✅ BaoStock profit_data |
| dividend_yield_ttm (dv_ttm) | ❌ PERMISSION_DENIED | ❌ not in kline | ❌ not in spot | **NULL** | ❌ NULL |

**Legend:**
- ✅ = data available
- ❌ = data not available / blocked
- **NULL** = user sees "—" in UI

---

## 3. Company Overview Production Data Contract

### With Target Configuration (DATA_MODE=free, ENABLE_BAOSTOCK=true, ENABLE_AKSHARE=true)

| # | Field | Backend API Field | Source | Unit | Frontend Field | Display | Expected |
|---|-------|------------------|--------|------|----------------|---------|----------|
| 1 | latest_price | `price` / `latest_price` / `close` | BaoStock kline | CNY | `snapData.price ?? snapData.latest_price ?? snapData.close` | N.NN | **≈1346.50** |
| 2 | pe_ttm | `pe_ttm` | BaoStock kline (peTTM) | 倍 | `snapData.pe_ttm` | N.NN倍 | **≈20.35** |
| 3 | pb | `pb` | BaoStock kline (pbMRQ) | 倍 | `snapData.pb` | N.NN倍 | **≈6.21** |
| 4 | total_market_cap | `total_mv` | AkShare 总市值 (if reachable) | CNY | `snapData.total_mv` → fmtMv() | N.NN亿元 | **≈16,900亿** if AkShare reachable, else **—** |
| 5 | roe | `roe` | BaoStock profit_data (roeAvg) | % | `finData.roe` → fmtPct() | N.NN% | **≈38.43** |
| 6 | dividend_yield_ttm | `dv_ttm` | Not available in kline/spot | % | `snapData.dv_ttm` → fmtPct() | — | **—** (graceful) |

**Source label:** When BaoStock kline fallback is used, `source = "baostock_kline_fallback"` → frontend shows "最近收盘价" label and source note "行情与估值来自 BaoStock K线（日频）".

### With Current Configuration (DATA_MODE=standard, no BaoStock/AkShare)

All six fields → `err_envelope` → null in response → UI displays "—" for all.

---

## 4. Provider Fallback Code Path (Verified from Source)

### Standard Mode (`data_mode == "standard"`, CURRENT PRODUCTION):
```
fetch_with_fallback()
  └── Tushare fetch() → TushareAuthError (permission denied)
      └── if ENABLE_AKSHARE: fetch_akshare() → False (missing) → SKIP
  └── err_envelope("部分财务指标暂不可用...") returned
      └── Company Overview: all 6 fields null
```

### Free Mode (`data_mode == "free"`, TARGET):
```
fetch_with_fallback()
  └── _fetch_free_mode()
      └── if ENABLE_BAOSTOCK: fetch_baostock() → BaoStock data ✅ (for price/PE/PB/ROE)
          └── ok_envelope(data) returned
      └── [if BaoStock fails] if ENABLE_AKSHARE: fetch_akshare() → AkShare data
```

---

## 5. Tushare Strategy Decision

**Recommended production strategy:** `DATA_MODE=free`

**Rationale:**
- Tushare Type C failure is not recoverable without purchasing API credits
- BaoStock provides free, no-registration, reliable data for CN A-shares
- BaoStock covers: price, PE, PB, ROE — the three most user-visible fields
- AkShare provides: total market cap, latest price (secondary)
- The gap (dv_ttm in kline mode) is a known, acceptable degradation
- Production server in CN will likely have AkShare access for total_mv

**Action required:** Project owner authorization to add `DATA_MODE=free` to root `.env`.

---

## 6. Safe Degradation Verification

The code correctly handles null values at every layer:

| Layer | Null Handling | Evidence |
|-------|--------------|---------|
| Provider | err_envelope returned | `base.py:_fetch_free_mode` line 119 |
| Aggregator | envelope.data = {} | DataEnvelope propagation |
| API response | fields absent or null | FastAPI response serialization |
| Frontend fmtMv | `if v == null → '—'` | `CompanyOverviewCards.vue:94-97` |
| Frontend fmt | `if v != null && isFinite → toFixed else '—'` | `CompanyOverviewCards.vue:70` |
| Frontend fmtPct | Same as fmt | `CompanyOverviewCards.vue:71` |

**Verdict:** No crash, no fabricated numbers, no null-as-0 bug. Graceful "—" display confirmed.

---

*This is an audit/probe document. No production data was modified.*
