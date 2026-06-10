# Fundamental Data Smoke Test

Manual validation guide for `GET /api/v1/stocks/{market}/{symbol}/fundamentals`.

---

## Prerequisites

Server running at `http://localhost:8000`.

```bash
# Start server
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

---

## Step 1 — Get Token

```bash
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"<your_username>","password":"<your_password>"}' | \
  python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

echo "Token: ${TOKEN:0:20}..."
```

---

## Step 2 — Test CN/600519 (贵州茅台)

```bash
curl -s "http://localhost:8000/api/v1/stocks/CN/600519/fundamentals" \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
```

### Expected HTTP Status

`200 OK` — always, even when data sources fail.

### Expected Fields (Phase 2, normal environment)

| Field | Expected Value | Notes |
|---|---|---|
| `market` | `"CN"` | |
| `symbol` | `"600519"` | |
| `company.name` | `"贵州茅台"` | From AkShare spot or quote_optional |
| `company.industry` | `null` | Phase 3 |
| `valuation.pe` | float or **null** | null if AkShare spot blocked by proxy |
| `valuation.pb` | float or **null** | null if AkShare spot blocked by proxy |
| `valuation.market_cap` | float or **null** | yfinance optional |
| `profitability.roe` | float (%) | e.g. `10.57` means 10.57% |
| `profitability.gross_margin` | float (%) | e.g. `89.76` means 89.76% |
| `profitability.net_margin` | float (%) | e.g. `52.22` means 52.22% |
| `growth.revenue_growth_yoy` | float (%) | YoY vs same period last year |
| `growth.net_profit_growth_yoy` | float (%) | YoY vs same period last year |
| `financial_health.debt_ratio` | float (%) | e.g. `12.12` means 12.12% |
| `financial_health.operating_cashflow` | float (元) | e.g. `2.691e10` = 269.1亿元 |
| `data_quality.latest_report_date` | `"YYYY-MM-DD"` | Most recent 报告期 |
| `data_quality.stale` | `false` | `true` only when all live sources fail |

### Expected `data_sources` Keys

When all sources succeed:
```json
{
  "company.name":                        "akshare_spot_em",
  "valuation.pe":                        "akshare_spot_em",
  "valuation.pb":                        "akshare_spot_em",
  "profitability.roe":                   "akshare_ths_financial_abstract",
  "profitability.gross_margin":          "akshare_ths_financial_abstract",
  "profitability.net_margin":            "akshare_ths_financial_abstract",
  "growth.revenue_growth_yoy":           "akshare_ths_financial_abstract",
  "growth.net_profit_growth_yoy":        "akshare_ths_financial_abstract",
  "financial_health.debt_ratio":         "akshare_ths_financial_abstract",
  "financial_health.operating_cashflow": "akshare_ths_cash_flow"
}
```

When AkShare spot is blocked (Clash dev environment):
- `company.name` source becomes `"quote_optional"` (Tencent / Sina fallback)
- `valuation.pe` and `valuation.pb` are absent from `data_sources` and appear in `missing_fields`

### Fields Expected to be `null` (by design, not failures)

These are `null` in Phase 2 and must **not** appear in `missing_fields`:

| Field | Reason | Target Phase |
|---|---|---|
| `company.industry` | Planned Phase 3 | Phase 3 |
| `company.business_summary` | Planned Phase 3 | Phase 3 |
| `valuation.ps` | Planned Phase 3 | Phase 3 |
| `valuation.dividend_yield` | Planned Phase 3 | Phase 3 |
| `valuation.market_cap` | yfinance optional | Phase 1 (optional) |

---

## Step 3 — Test HK/700 (腾讯控股)

```bash
curl -s "http://localhost:8000/api/v1/stocks/HK/700/fundamentals" \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
```

### Expected HK/700 Response (Phase 2)

| Field | Expected | Notes |
|---|---|---|
| `company.name` | `"腾讯控股"` | From Tencent HK quote |
| `valuation.pe` | `null` | Phase 3 |
| `valuation.pb` | `null` | Phase 3 |
| `profitability.*` | all `null` | Phase 3/4 |
| `growth.*` | all `null` | Phase 3/4 |
| `financial_health.*` | all `null` | Phase 3/4 |
| `data_quality.missing_fields` | `[]` | HK nulls are by design, not failures |
| `data_quality.message` | contains `"Phase 2"` | Explains limitation |
| HTTP status | `200` | Never 5xx |

---

## Step 4 — Validate Unit Semantics

Run this quick validation script:

```bash
python3 - << 'EOF'
import json, sys

with open("/tmp/cn_fund.json") as f:
    d = json.load(f)

errors = []

# All percentage fields must be in human percentage form (> 1.0 for typical stocks)
for section, field in [
    ("profitability", "roe"),
    ("profitability", "gross_margin"),
    ("profitability", "net_margin"),
    ("growth", "revenue_growth_yoy"),
    ("growth", "net_profit_growth_yoy"),
    ("financial_health", "debt_ratio"),
]:
    v = d[section][field]
    if v is not None and v < 0.1:
        errors.append(f"UNIT ERROR: {section}.{field}={v} looks like decimal (should be %, e.g. 54.27)")

# operating_cashflow should be in raw yuan (large number)
ocf = d["financial_health"]["operating_cashflow"]
if ocf is not None and ocf < 1e6:
    errors.append(f"UNIT ERROR: operating_cashflow={ocf} suspiciously small (should be in raw yuan)")

# latest_report_date must be present and valid
lrd = d["data_quality"]["latest_report_date"]
if lrd is None:
    errors.append("MISSING: latest_report_date is null")
elif len(lrd) != 10 or lrd[4] != "-":
    errors.append(f"FORMAT ERROR: latest_report_date={lrd!r} not YYYY-MM-DD")

if errors:
    print("UNIT VALIDATION FAILED:")
    for e in errors: print(f"  {e}")
    sys.exit(1)
else:
    print("Unit validation PASSED")
    print(f"  Report date: {lrd}")
    print(f"  Period type: {'Annual' if lrd.endswith('12-31') else 'Interim/Quarterly'}")
EOF
```

---

## Common Failure Patterns

### `valuation.pe` and `valuation.pb` are `null`

**Cause:** AkShare `stock_zh_a_spot_em()` requires access to `push2.eastmoney.com`, which is
blocked in environments running Clash without a direct rule for `eastmoney.com`.

**Diagnosis:** Check `data_quality.message` — it will contain "Connection aborted" or similar.

**Fix (dev):** Add Clash rule: `DOMAIN-SUFFIX,eastmoney.com,DIRECT`

**In production:** These fields should be populated. If not, check network access to Eastmoney.

**Note:** `valuation.pe` and `valuation.pb` being `null` will appear in `missing_fields`.
The THS financial data (roe/margins/growth) is **unaffected** — it uses a different domain.

### All financial fields are `null`

**Cause:** `stock_financial_abstract_ths()` or `stock_financial_cash_ths()` failed.

**Diagnosis:** Check `data_quality.message` for error detail. Check server logs.

**Common reasons:**
- Network connectivity to `basic.10jqka.com.cn` (Tonghuashun / 同花顺)
- AkShare version incompatibility — run `uv run pip show akshare`
- Symbol not found in THS database (rare for major A-share stocks)

### `data_quality.stale = true`

**Cause:** All live data sources failed on this request, but a prior cached snapshot existed.

**Meaning:** The returned data is from a previous successful fetch (may be hours old).
The `data_quality.message` will note "实时数据源暂不可用，当前展示最近一次历史缓存。"

**Action:** No action required — this is intentional degradation. Investigate source failures separately.

### `company.name = null`

**Cause:** Both AkShare spot and quote_optional (Tencent/Sina fallback) failed.

**Diagnosis:** Check `stock_data_service` logs for quote failures. Extremely rare — Tencent is very
reliable. May indicate network isolation in the deployment environment.

---

## How to Interpret `null` and `missing_fields`

### `null` value

A field being `null` means one of two things:

1. **By design (Phase not implemented):** `company.industry`, `company.business_summary`,
   `valuation.ps`, `valuation.dividend_yield`. These are planned for Phase 3/4.
   They are `null` and do **not** appear in `missing_fields`.

2. **Data source failed:** The field was expected (e.g. `valuation.pe`) but no provider
   returned a value. These appear in `missing_fields`.

### `missing_fields`

`missing_fields` only contains fields that were **expected to have a value but didn't**.
Fields that are intentionally `null` (not yet implemented) are **excluded** from this list.

**For FundamentalAnalystAgent:** Any field in `missing_fields` must be reported as
"数据不足，暂不评估" — never inferred, estimated, or skipped silently.

---

## Validation Checklist

Before marking the data layer as production-ready, confirm:

- [ ] `GET /CN/600519/fundamentals` returns HTTP 200
- [ ] `GET /HK/700/fundamentals` returns HTTP 200
- [ ] CN `company.name` is non-null
- [ ] CN `profitability.roe` is a float > 1.0 (i.e. percentage, not decimal)
- [ ] CN `financial_health.operating_cashflow` is > 1e8 (raw yuan, not亿)
- [ ] CN `data_quality.latest_report_date` is present and in YYYY-MM-DD format
- [ ] CN `data_quality.missing_fields` does not contain `company.industry` (planned null)
- [ ] HK returns HTTP 200 with all financial fields null
- [ ] HK `data_quality.message` mentions "Phase 2" or data limitation
- [ ] Second request hits cache (response time < 100ms)
- [ ] No HTTP 5xx under any conditions
