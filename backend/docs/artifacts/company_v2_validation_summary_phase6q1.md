# CompanyV2 Validation Summary

| Symbol | Status | Score | Checks | Pass | Warning | Fail | Strong Fail | Semantic Warning | Context Skipped | Critical |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 600519 | warning | 89 | 27 | 16 | 3 | 0 | 0 | 2 | 1 | 0 |
| 000725 | warning | 94 | 27 | 17 | 2 | 0 | 0 | 2 | 1 | 0 |
| 601686 | warning | 84 | 27 | 15 | 4 | 0 | 0 | 2 | 1 | 0 |

## Strong Failures


## Semantic Warnings

### 600519
- `dupont_roe_formula` `weak` `warning` module=`dupont` field=`roe` diff=`48.5332` tags=`DUPONT_PROVIDER_DEFINED,ACCOUNTING_DEFINITION_DIFFERENCE,DUPONT_FORMULA_WEAK_CHECK`
- `net_margin_formula` `weak` `warning` module=`profitability` field=`net_margin` diff=`68.6673` tags=`FORMULA_CONTEXT_MISSING`

### 000725
- `dupont_roe_formula` `weak` `warning` module=`dupont` field=`roe` diff=`96.649` tags=`DUPONT_PROVIDER_DEFINED,ACCOUNTING_DEFINITION_DIFFERENCE,DUPONT_FORMULA_WEAK_CHECK`
- `net_margin_formula` `weak` `warning` module=`profitability` field=`net_margin` diff=`75.0717` tags=`FORMULA_CONTEXT_MISSING`

### 601686
- `dupont_roe_formula` `weak` `warning` module=`dupont` field=`roe` diff=`98.6467` tags=`DUPONT_PROVIDER_DEFINED,ACCOUNTING_DEFINITION_DIFFERENCE,DUPONT_FORMULA_WEAK_CHECK`
- `net_margin_formula` `weak` `warning` module=`profitability` field=`net_margin` diff=`78.993` tags=`FORMULA_CONTEXT_MISSING`

## Skipped Due To Missing Context

- 600519: 1 skipped, 2 context-missing checks
- 000725: 1 skipped, 2 context-missing checks
- 601686: 1 skipped, 2 context-missing checks

## Provider / Accounting Definition Differences

Provider-defined financial ratios are reported as semantic warnings when period/value-basis context is incomplete.