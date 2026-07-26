# CompanyV2 Validation Summary

| Symbol | Status | Score | Checks | Pass | Warning | Fail | Skipped | Critical |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 600519 | fail | 65 | 27 | 16 | 1 | 2 | 8 | 0 |
| 000725 | fail | 70 | 27 | 17 | 0 | 2 | 8 | 0 |
| 601686 | fail | 60 | 27 | 15 | 2 | 2 | 8 | 0 |

## Top Checks

### 600519
- `dupont_roe_formula` `fail` `error` module=`dupont` field=`roe` diff=`48.5332`
- `net_margin_formula` `fail` `error` module=`profitability` field=`net_margin` diff=`68.6673`
- `receivable_turnover_sanity` `warning` `info` module=`operation_capability` field=`receivable_turnover` diff=`None`
- `market_cap_formula` `pass` `info` module=`quote_overview` field=`market_cap` diff=`0.0`
- `float_market_cap_formula` `pass` `info` module=`quote_overview` field=`float_market_cap` diff=`0.0`
- `float_market_cap_lte_market_cap` `pass` `info` module=`quote_overview` field=`float_market_cap` diff=`0.0`
- `pe_ttm_sanity` `pass` `info` module=`valuation` field=`pe_ttm` diff=`None`
- `pb_sanity` `pass` `info` module=`valuation` field=`pb` diff=`None`

### 000725
- `dupont_roe_formula` `fail` `error` module=`dupont` field=`roe` diff=`96.649`
- `net_margin_formula` `fail` `error` module=`profitability` field=`net_margin` diff=`75.0717`
- `market_cap_formula` `pass` `info` module=`quote_overview` field=`market_cap` diff=`0.0`
- `float_market_cap_formula` `pass` `info` module=`quote_overview` field=`float_market_cap` diff=`0.0`
- `float_market_cap_lte_market_cap` `pass` `info` module=`quote_overview` field=`float_market_cap` diff=`0.0`
- `pe_ttm_sanity` `pass` `info` module=`valuation` field=`pe_ttm` diff=`None`
- `pb_sanity` `pass` `info` module=`valuation` field=`pb` diff=`None`
- `ps_ttm_sanity` `pass` `info` module=`valuation` field=`ps_ttm` diff=`None`

### 601686
- `dupont_roe_formula` `fail` `error` module=`dupont` field=`roe` diff=`98.6467`
- `net_margin_formula` `fail` `error` module=`profitability` field=`net_margin` diff=`78.993`
- `pcf_ncf_ttm_sanity` `warning` `info` module=`valuation` field=`pcf_ncf_ttm` diff=`None`
- `ocf_to_np_sanity` `warning` `warning` module=`cashflow_quality` field=`ocf_to_np` diff=`None`
- `market_cap_formula` `pass` `info` module=`quote_overview` field=`market_cap` diff=`0.0`
- `float_market_cap_formula` `pass` `info` module=`quote_overview` field=`float_market_cap` diff=`0.0`
- `float_market_cap_lte_market_cap` `pass` `info` module=`quote_overview` field=`float_market_cap` diff=`0.0`
- `pe_ttm_sanity` `pass` `info` module=`valuation` field=`pe_ttm` diff=`None`
