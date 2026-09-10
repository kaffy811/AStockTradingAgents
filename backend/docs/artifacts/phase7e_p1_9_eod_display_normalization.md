# Phase 7E-P1.9 EOD Financial Display Normalization

## Conclusion

`EOD_DISPLAY_NORMALIZATION_READY`

This candidate changes only the deterministic user-facing projection of already validated stock EOD facts. It does not modify provider retrieval, raw values, routing, cache, numeric-validation rules, calculations, credentials, Docker, dependencies, database, migrations, or news capabilities.

## Implementation

- Added a backend-only display policy keyed by `(module, metric)`.
- Used `Decimal` and `ROUND_HALF_UP` with exactly two decimal places.
- Preserved the original `canonical_value`, `canonical_unit`, `as_of`, `report_period`, source, and request-local evidence ID.
- Added `display_value`, `display_unit`, `rounding_policy`, and `evidence_id` to every projected fact.
- Retained the existing numeric validator and its strict claim/evidence matching unchanged.
- Unknown or mismatched canonical units are not converted. A present but rejected fact produces controlled `partial` or `unavailable` status with `EOD_DISPLAY_NORMALIZATION_UNAVAILABLE`; its raw numeric value is not rendered.

## Display policy

| Financial meaning | Canonical unit | Display conversion | Display |
|---|---|---|---|
| Price/change | `CNY` | identity | `元`, 2 decimals |
| Ratios/ROE | `%` | identity | `%`, 2 decimals |
| PE/PB/PS | `multiple` | identity | `倍`, 2 decimals |
| Amount | `CNY_thousand` | × `0.00001` | `亿元`, 2 decimals |
| Market value | `CNY_10k` | × `0.0001` | `亿元`, 2 decimals |
| Volume | `lot` | × `0.0001` | `万手`, 2 decimals |

Volume is never converted to shares. Because one 万手 equals 10,000 手, canonical `7,616,584.07 lot` deterministically displays as `761.66 万手`; the contrary `7,616.58 万手` example would be a tenfold magnitude error and is intentionally rejected.

## Verified examples

```text
4169035.35291 CNY_thousand -> 41.69 亿元
20226203.088 CNY_10k       -> 2,022.62 亿元
7616584.07 lot             -> 761.66 万手
25.7405 multiple           -> 25.74 倍
5.46 CNY                   -> 5.46 元
17.9543 %                  -> 17.95 %
```

No output uses “约” or “估算”.

## Request-level regression

Redacted fixtures cover:

- `CN/000725 公司资料 + EOD`
- `贵州茅台近期情况`
- `600519 财务指标、ROE、估值`

All three retain `stock_eod_research`, `fulfilled`, `numeric_validation.valid=true`, and `unsupported_tokens=[]`. Each rendered numeric fact contains:

```text
metric
canonical_value
canonical_unit
display_value
display_unit
rounding_policy
evidence_id
request_local_evidence_id
as_of
report_period (financial facts)
source
```

The deterministic stock route continues to use zero LLM, general skill, Tushare news, AKShare, Eastmoney, Sina, and Tencent calls in controlled tests.

## Negative verification

- Wrong canonical unit: rejected before conversion.
- Unknown unit: raw value omitted and response safely downgraded.
- Wrong rounding (`41.70`, `41.690`) and wrong magnitude (`416.90`): numeric validation returns invalid.
- Volume unit remains 手/万手 and never becomes 股.
- Existing report-period, source, code, evidence-ID, and numeric-token checks remain active.

## Gates

- Related backend display, routing, Company/EOD, theme and numeric regression: **108 passed**.
- Targeted frontend fulfillment/status regression: **24 passed**.
- Full frontend suite: **769 passed**.
- Frontend production build: passed; existing large-chunk advisory only.
- Python compile, JSON validation, secret scan and `git diff --check`: recorded in the runtime manifest.
- Live providers were not called.
