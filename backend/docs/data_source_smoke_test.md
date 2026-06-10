# Data Source Smoke Test

Quick manual tests to verify the stock data API is functioning end-to-end.  
All requests require a valid Bearer token (obtain via `POST /auth/login`).

Set a shell variable before running:

```bash
TOKEN="<your_jwt_token>"
BASE="http://localhost:8000"
```

---

## Quote Endpoints

### CN/600519 — 贵州茅台 (Shanghai, prefix 6)

```bash
curl -s -w "\nHTTP %{http_code}\n" \
  -H "Authorization: Bearer $TOKEN" \
  "$BASE/stocks/CN/600519/quote" | python3 -m json.tool
```

**Expected (market hours or post-close):**
```json
{
  "market":    "CN",
  "symbol":    "600519",
  "provider":  "sina",
  "cached":    false,
  "stale":     false,
  "data": {
    "symbol":     "600519",
    "name":       "贵州茅台",
    "price":      1324.3,
    "open":       1321.9,
    "prev_close": 1323.0,
    "high":       1329.99,
    "low":        1318.0,
    "volume":     432546400,
    "amount":     5719170335.0,
    "change":     1.3,
    "change_pct": 0.098,
    "trade_time": "2026-05-19 15:00:02"
  }
}
```
HTTP status: `200`

**Key checks:**
- `provider` is `sina` or `tencent` (Eastmoney unreachable in current env)
- `price` > 0
- `stale` is `false` during or after trading hours
- `data.amount` is a positive float (Sina provides this)

---

### CN/000001 — 平安银行 (Shenzhen, prefix 0)

```bash
curl -s -w "\nHTTP %{http_code}\n" \
  -H "Authorization: Bearer $TOKEN" \
  "$BASE/stocks/CN/000001/quote" | python3 -m json.tool
```

**Key checks:**
- `price` > 0
- `data.symbol` is `"000001"`
- `provider` in `["eastmoney", "sina", "tencent"]`
- secid mapping: Shenzhen code should produce `0.000001` internally (verify no market error)

---

### CN/300750 — 宁德时代 (ChiNext, prefix 3)

```bash
curl -s -w "\nHTTP %{http_code}\n" \
  -H "Authorization: Bearer $TOKEN" \
  "$BASE/stocks/CN/300750/quote" | python3 -m json.tool
```

**Key checks:**
- `price` > 0
- ChiNext (创业板) stocks use Shenzhen exchange → `sz300750` in Tencent, `0.300750` in Eastmoney
- No `400` or `500` errors

---

### HK/700 — 腾讯控股

```bash
curl -s -w "\nHTTP %{http_code}\n" \
  -H "Authorization: Bearer $TOKEN" \
  "$BASE/stocks/HK/700/quote" | python3 -m json.tool
```

**Expected:**
```json
{
  "market":   "HK",
  "symbol":   "700",
  "provider": "tencent_hk",
  "cached":   false,
  "stale":    false,
  "data": {
    "symbol":     "00700",
    "name":       "腾讯控股",
    "price":      460.0,
    "open":       449.2,
    "prev_close": 449.2,
    "high":       468.8,
    "low":        448.6,
    "volume":     33736701,
    "amount":     null,
    "change":     10.8,
    "change_pct": 2.4,
    "turnover":   33736701.0
  }
}
```
HTTP status: `200`

**Key checks:**
- `provider` is `tencent_hk`
- `data.amount` is `null` (expected — Tencent HK does not return 成交额 reliably)
- `data.volume` is in shares (no ×100 for HK) — should equal `data.turnover`
- `data.symbol` is `"00700"` (5-digit zero-padded format)

---

## Kline Endpoints

### CN/600519/kline — daily, qfq, 120 bars

```bash
curl -s -w "\nHTTP %{http_code}\n" \
  -H "Authorization: Bearer $TOKEN" \
  "$BASE/stocks/CN/600519/kline?period=daily&adjust=qfq&limit=120" | python3 -m json.tool
```

**Expected:**
```json
{
  "market":    "CN",
  "symbol":    "600519",
  "provider":  "tencent_kline",
  "period":    "daily",
  "adjust":    "qfq",
  "count":     120,
  "cached":    false,
  "stale":     false,
  "data": [
    {
      "date":   "2025-11-17",
      "open":   1430.04,
      "close":  1447.04,
      "high":   1449.04,
      "low":    1421.83,
      "volume": 34462.0,
      "amount": null
    },
    "...",
    {
      "date":   "2026-05-19",
      "open":   1321.9,
      "close":  1324.3,
      "high":   1329.99,
      "low":    1318.0,
      "volume": 43255.0,
      "amount": null
    }
  ]
}
```
HTTP status: `200`

**Key checks:**
- `count` == `120` exactly (not 121)
- `data[0].date` is the oldest bar (approx 120 trading days ago)
- `data[-1].date` is today or the most recent trading day
- `data[*].amount` is `null` throughout (Tencent kline does not provide 成交额)
- `data[*].volume` unit is **手 (lots)** — multiply by 100 to convert to shares
- `provider` is `tencent_kline` (Eastmoney unreachable in current env)

**Additional spot checks:**

```bash
# Weekly bars
curl -s -H "Authorization: Bearer $TOKEN" \
  "$BASE/stocks/CN/600519/kline?period=weekly&adjust=qfq&limit=52" \
  | python3 -c "import json,sys; d=json.load(sys.stdin); print('count:', d['count'])"

# No adjust (unadjusted)
curl -s -H "Authorization: Bearer $TOKEN" \
  "$BASE/stocks/CN/600519/kline?period=daily&adjust=&limit=5" \
  | python3 -c "import json,sys; d=json.load(sys.stdin); print([b['date'] for b in d['data']])"
```

---

### HK/700/kline — daily, qfq, 120 bars

```bash
curl -s -w "\nHTTP %{http_code}\n" \
  -H "Authorization: Bearer $TOKEN" \
  "$BASE/stocks/HK/700/kline?period=daily&adjust=qfq&limit=120" | python3 -m json.tool
```

**Expected:**
```json
{
  "market":   "HK",
  "symbol":   "700",
  "provider": "tencent_kline",
  "period":   "daily",
  "adjust":   "qfq",
  "count":    120,
  "cached":   false,
  "stale":    false,
  "data": [
    {
      "date":   "2025-11-19",
      "open":   627.5,
      "close":  622.5,
      "high":   631.5,
      "low":    619.5,
      "volume": 13959708.0,
      "amount": null
    },
    "...",
    {
      "date":   "2026-05-19",
      "open":   449.2,
      "close":  460.0,
      "high":   468.8,
      "low":    448.6,
      "volume": 33736701.0,
      "amount": null
    }
  ]
}
```
HTTP status: `200`

**Key checks:**
- `count` == `120` exactly
- `data[*].volume` unit is **shares** (not lots) — consistent with HK quote `volume`
- `data[*].amount` is `null` (same limitation as CN kline)
- Last bar `close` matches HK quote `price` (within the same trading session)

---

## Cache Behaviour Test

```bash
# First call — should be fresh (cached=false)
curl -s -H "Authorization: Bearer $TOKEN" \
  "$BASE/stocks/CN/600519/quote" \
  | python3 -c "import json,sys; d=json.load(sys.stdin); print('cached:', d['cached'])"

# Immediate second call — should hit TTL cache (cached=true)
curl -s -H "Authorization: Bearer $TOKEN" \
  "$BASE/stocks/CN/600519/quote" \
  | python3 -c "import json,sys; d=json.load(sys.stdin); print('cached:', d['cached'])"
```

Expected output:
```
cached: False
cached: True
```

---

## Error Cases

### Invalid market

```bash
curl -s -w "\nHTTP %{http_code}\n" \
  -H "Authorization: Bearer $TOKEN" \
  "$BASE/stocks/US/AAPL/quote"
```
Expected: HTTP `400`, body contains `"Unsupported market"`

### Invalid adjust parameter

```bash
curl -s -w "\nHTTP %{http_code}\n" \
  -H "Authorization: Bearer $TOKEN" \
  "$BASE/stocks/CN/600519/kline?adjust=badvalue"
```
Expected: HTTP `400`, body contains `"adjust 参数非法"`

### Invalid limit (out of range)

```bash
curl -s -w "\nHTTP %{http_code}\n" \
  -H "Authorization: Bearer $TOKEN" \
  "$BASE/stocks/CN/600519/kline?limit=0"
```
Expected: HTTP `422` (FastAPI validation error)

### Unauthenticated request

```bash
curl -s -w "\nHTTP %{http_code}\n" \
  "$BASE/stocks/CN/600519/quote"
```
Expected: HTTP `401` or `403`
