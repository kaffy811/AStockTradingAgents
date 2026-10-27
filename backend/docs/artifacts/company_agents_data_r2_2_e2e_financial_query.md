# Phase 6W-R2.2 — E2E Financial Query & Numeric Validation

**Generated:** 2026-08-12  
**Branch:** release/demo-staging  
**HEAD:** a542bc18a21e465c7025d4bdc8c16f032f60736d  
**Gates:** G6, G7, G8, G9, G10

---

## Current State: BLOCKED (depends on G1, G5)

Cannot run E2E queries until database is reachable and real report is indexed.

---

## G6 — Financial Analysis E2E Query

### Target Query

```bash
curl -s -X POST http://localhost:8000/api/v1/stock/600519/report-chat \
  -H "Authorization: Bearer <USER_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{
    "question": "贵州茅台2024年财报表现如何？营收和利润增长情况怎么样？",
    "force_refresh": true
  }' | python3 -m json.tool
```

### Required Response Fields

| Field | Required Value | Evidence of |
|-------|---------------|------------|
| `status` | `"completed"` | Full chain success |
| `partial` | `false` | No degradation |
| `confidence` | `"high"` | Evidence quality |
| `rag_status` | `"indexed_fast_path"` | Real indexed chunks found via keyword search |
| `chunks_retrieved` | `>= 1` | Real document evidence retrieved |
| `llm_model` | `"deepseek-v4-flash"` | Real LLM invoked |
| `errors` | `[]` | No errors |

### Fail Conditions

- `status != "completed"` → G6 FAIL
- `rag_status != "indexed_fast_path"` → G6 FAIL (means keyword search found 0 chunks)
- `chunks_retrieved == 0` → G6 FAIL
- Response contains fabricated financial numbers not present in source chunks → G6 FAIL
- `errors` non-empty → G6 FAIL

---

## G7 — Numeric Validation

### Required Fields

| Field | Required Value | Evidence of |
|-------|---------------|------------|
| `numeric_validation.valid` | `true` | Numbers grounded in retrieved evidence |
| `numeric_validation.evidence_available` | `true` | Source chunk evidence chain complete |
| `numeric_validation.unsupported_claims` | `[]` | No hallucinated numbers |

### Fail Conditions

- `numeric_validation.valid = false` → G7 FAIL
- `numeric_validation.evidence_available = false` → G7 FAIL  
- Any financial figure in response without source chunk reference → G7 FAIL

---

## G10 — Cache Isolation Regression

### Query 1: Locator Intent

```bash
curl -s -X POST http://localhost:8000/api/v1/stock/600519/report-chat \
  -H "Authorization: Bearer <USER_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{
    "question": "贵州茅台最新报告是哪一份？"
  }' | python3 -c "
import sys, json
r = json.load(sys.stdin)
print('intent_type:', r.get('intent_type'))
print('rag_status:', r.get('rag_status'))
print('cache_key_prefix: rc:v2:' + str(r.get('intent_type','?')) + ':600519')
"
```

Expected:
```
intent_type: locator
rag_status: not_required
cache_key_prefix: rc:v2:locator:600519
```

### Query 2: Analysis Intent

```bash
curl -s -X POST http://localhost:8000/api/v1/stock/600519/report-chat \
  -H "Authorization: Bearer <USER_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{
    "question": "贵州茅台2024财报表现如何？"
  }' | python3 -c "
import sys, json
r = json.load(sys.stdin)
print('intent_type:', r.get('intent_type'))
print('rag_status:', r.get('rag_status'))
print('cache_key_prefix: rc:v2:' + str(r.get('intent_type','?')) + ':600519')
"
```

Expected:
```
intent_type: analysis
rag_status: indexed_fast_path
cache_key_prefix: rc:v2:analysis:600519
```

### Cache Key Isolation Verification

| Cache Key | Intent | Cannot Conflict |
|-----------|--------|----------------|
| `rc:v2:locator:600519:<hash>` | locator | Separate key space |
| `rc:v2:analysis:600519:<hash>` | analysis | Separate key space |

The `intent_type` segment in position 3 of the key structurally prevents cross-contamination.

### G10 Pass Criterion

`intent_type` field differs between the two responses AND cache key prefixes differ → G10 PASS.

---

## G8/G9 — Company Overview Verification

### Request

```bash
curl -s http://localhost:8000/api/v1/stocks/CN/600519/profile \
  -H "Authorization: Bearer <USER_TOKEN>" | python3 -c "
import sys, json
r = json.load(sys.stdin)
snap = r.get('snapshot', {})
fin = r.get('financials', {})
series = fin.get('series', [{}])
latest = series[0] if series else {}

print('--- G8/G9 Company Overview ---')
print(f'price:    {snap.get(\"close\") or snap.get(\"latest_price\") or snap.get(\"price\")}')
print(f'pe_ttm:   {snap.get(\"pe_ttm\")}')
print(f'pb:       {snap.get(\"pb\")}')
print(f'roe:      {latest.get(\"roe\")}')
print(f'total_mv: {snap.get(\"total_mv\")}  (null acceptable)')
print(f'dv_ttm:   {snap.get(\"dv_ttm\")}  (null acceptable)')
print(f'source:   {snap.get(\"source\")}')
"
```

### G9 Pass Criteria

| Field | Required | Acceptable Null |
|-------|----------|----------------|
| `price` (close/latest_price) | **NOT NULL** | No |
| `pe_ttm` | **NOT NULL** | No |
| `pb` | **NOT NULL** | No |
| `roe` | **NOT NULL** | No |
| `total_mv` | null OK | Yes (BaoStock kline limitation) |
| `dv_ttm` | null OK | Yes (BaoStock kline limitation) |

Expected source: `"baostock_kline_fallback"` (from R2.0 provider validation)

---

## Pre-verified Data (R2.0 Provider Test — BaoStock Live)

| Field | Value | Verified |
|-------|-------|---------|
| close | 1346.50 CNY | ✓ R2.0 |
| peTTM | 20.35 倍 | ✓ R2.0 |
| pbMRQ | 6.21 倍 | ✓ R2.0 |
| roeAvg | 38.43% | ✓ R2.0 |
| total_mv | — (null graceful) | ✓ R2.0 |
| dv_ttm | — (null graceful) | ✓ R2.0 |

These values will differ at live-test time (market data is time-sensitive). What matters is `!= null`, not specific values.

---

## G6/G7/G10 Verdicts

**ALL BLOCKED** — awaiting G1 (database) + G5 (real report indexed).

*Update this file after production E2E queries complete.*
