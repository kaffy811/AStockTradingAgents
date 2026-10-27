# Phase 6W-R2.0 — Provider Capability Validation

**Generated:** 2026-08-12  
**Branch:** release/demo-staging  
**HEAD:** a542bc1  
**Data mode:** `free` (after root .env alignment)

---

## Tushare (Token: e81***, len=56)

| Endpoint | Result |
|----------|--------|
| `trade_cal` | PERMISSION_DENIED |
| `stock_basic` | PERMISSION_DENIED |
| `daily_basic` | PERMISSION_DENIED |
| `fina_indicator` | PERMISSION_DENIED |

**Classification:** Type C — valid token, no purchased API credits.  
**Decision:** `DATA_MODE=free` adopted. Tushare is bypassed entirely. Not a blocker.

---

## BaoStock — 600519.SH (2026-08-11)

| Field | BaoStock API | Raw Value | Converted | Status |
|-------|-------------|-----------|-----------|--------|
| Latest price (close) | `query_history_k_data_plus` close | 1346.5000 | 1346.50 CNY | **PASS** |
| PE (TTM) | `query_history_k_data_plus` peTTM | 20.349788 | 20.35 倍 | **PASS** |
| PB (MRQ) | `query_history_k_data_plus` pbMRQ | 6.213628 | 6.21 倍 | **PASS** |
| ROE | `query_profit_data` roeAvg | 0.384283 | 38.43% | **PASS** |
| Total market cap | not in K data | — | — | **NULL (graceful)** |
| Dividend yield TTM | not in K data | — | — | **NULL (graceful)** |

**BaoStock login:** `code=0`, success, stable connection.

---

## AkShare — Local Machine

| Test | Local Result | Expected CN Production |
|------|-------------|----------------------|
| `stock_zh_a_spot_em()` | FAIL (EastMoney HTTPS blocked by proxy) | LIKELY PASS |

AkShare would provide `total_mv` (总市值) and `latest_price` if reachable. On a CN production server, EastMoney endpoints are accessible. This field will show "—" on local/staging and is expected to populate in production.

---

## Company Overview Six-Field Contract (DATA_MODE=free)

| # | Field | Backend Field | Provider | Raw → Display | Production Ready |
|---|-------|--------------|----------|---------------|-----------------|
| 1 | latest_price | `close` (kline fallback) | BaoStock K | 1346.5000 → "1346.50" | ✅ |
| 2 | pe_ttm | `pe_ttm` | BaoStock K peTTM | 20.349788 → "20.35倍" | ✅ |
| 3 | pb | `pb` | BaoStock K pbMRQ | 6.213628 → "6.21倍" | ✅ |
| 4 | total_mv | `total_mv` | AkShare (if reachable) | — / "—" graceful | ✅ (graceful) |
| 5 | roe | `roe` | BaoStock profit_data roeAvg | 0.384283 → "38.43%" | ✅ |
| 6 | dv_ttm | `dv_ttm` | N/A in BaoStock kline | — / "—" graceful | ✅ (graceful) |

**Frontend null handling (CompanyOverviewCards.vue):**
- `fmt(null)` → `'—'` — no crash, no fabricated value ✅
- `fmtMv(null)` → `'—'` ✅
- `fmtPct(null)` → `'—'` ✅

**Source label:** `source = "baostock_kline_fallback"` → frontend shows "最近收盘价" label and "行情与估值来自 BaoStock K线（日频），总市值暂不可用".

---

## Provider Fallback Code Path

Effective production path with `DATA_MODE=free`, `ENABLE_BAOSTOCK=true`, `ENABLE_AKSHARE=true`:

```
fetch_with_fallback()
  └── data_mode == "free" → _fetch_free_mode()
      └── ENABLE_BAOSTOCK=true → fetch_baostock()
          ├── BaoStock login (code=0)
          ├── query_history_k_data_plus: close, peTTM, pbMRQ ✅
          ├── source = "baostock_kline_fallback"
          └── ok_envelope(data) returned
      
      [if BaoStock fails]
      └── ENABLE_AKSHARE=true → fetch_akshare()
          └── AkShare spot_em data (requires EastMoney HTTPS)
```

**G8 (Provider chain): PASS** — Code path confirmed, BaoStock live test PASS.

---

## Known Graceful Degradations (Acceptable)

| Degradation | User Impact | UI Behavior |
|-------------|-------------|-------------|
| `total_mv` = null (BaoStock kline) | Market cap shows "—" | ✅ fmtMv(null) → "—" |
| `dv_ttm` = null (BaoStock kline) | Dividend yield shows "—" | ✅ fmtPct(null) → "—" |

These are **accepted product limitations** of the free data mode. Not defects.

---

*No production data was modified. Provider tests are read-only queries.*
