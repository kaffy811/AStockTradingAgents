# Phase 7E-P0.1 Tushare EOD Numeric Reconciliation

## First root cause

The Tushare EOD facts were correct. `600519` resolved to `600519.SH`; daily and valuation facts used trade date `2026-09-09`, financial facts used report period `2026-06-30`, and PE/PB/ROE units and decimal precision remained intact.

The first mismatch occurred after EOD answer construction: `_handle_stock_eod_research` appended persisted CNINFO event titles and publication dates to the same answer, while `validate_stock_eod_numeric_claims` correctly accepted only request-local EOD evidence and explicit metadata dates. A CNINFO title containing a year therefore produced unsupported token `2026`, changing both target queries to `partial / NUMERIC_EVIDENCE_VALIDATION_FAILED`. The prior unit test fixture used an empty event list and did not exercise this production shape.

## Minimal fix

The deterministic stock EOD route is now isolated from CNINFO event/report content. It renders only normalized Tushare quote, valuation, and financial facts and does not call the CNINFO event service, Report RAG, a synthesis LLM, news tools, or model memory. Official reports and events remain available through their existing dedicated routes.

No integer or metadata-wide exemption was added. The validator remains fail-closed. A metric/module unit contract was added so a provider-shaped fact with the wrong unit cannot become request-local evidence.

## Single live provider probe

One actual local Tushare probe ran with a 45-second total bound and no Provider retry. It made exactly four approved endpoint calls: `stock_basic`, `daily`, `daily_basic`, and `fina_indicator`. It made zero LLM, Tushare-news, AKShare, Eastmoney, Sina, or Tencent calls. No Token, header, database string, or raw Provider body was recorded.

The sanitized response was `fulfilled`, source `tushare`, EOD as-of `2026-09-09`, and financial report period `2026-06-30`. Key normalized facts were close `1290.88 CNY`, PE TTM `19.8161 multiple`, PB `6.4226 multiple`, and ROE `17.9543%`.

## End-to-end controlled replay

The sanitized shape from that probe was stored as a test fixture and replayed through intent routing, entity resolution output, answer rendering, evidence creation, and numeric validation:

| Query | Symbol | Result | Numeric validation | Calls during replay |
|---|---|---|---|---|
| `贵州茅台近期情况` | `600519` → `600519.SH` | `fulfilled`, no reason code | valid; 18 checked claims; 18 evidence facts; unsupported `[]` | fixture gateway 1; live Provider 0; CNINFO 0; LLM 0 |
| `600519 财务指标、ROE、估值` | `600519` → `600519.SH` | `fulfilled`, no reason code | valid; 18 checked claims; 18 evidence facts; unsupported `[]` | fixture gateway 1; live Provider 0; CNINFO 0; LLM 0 |
| `AI 半导体设备主题问题` | none | `unavailable / NO_APPROVED_INDUSTRY_NEWS_SOURCE` | not applicable | all LLM/Provider/resolver calls 0 |

The replay is explicitly not described as two additional live Provider calls. It proves that the exact response shape obtained by the one live probe now survives the deterministic request-local evidence chain.

## Safety and UI state

- Unsupported numbers are still removed through safe `partial` fallback.
- Missing facts remain `partial` or `unavailable`; no missing number is synthesized.
- The answer explicitly says EOD/report-period data is not real time.
- Theme/news fail-closed routing is unchanged.
- Existing frontend fulfillment tests confirm: `fulfilled` → “已完成研究”, `partial` → “部分完成”, `unavailable` → “当前缺少所需数据”; only fulfilled shows the completed state.

## Tests and gates

- Related backend regression: 59 passed.
- Focused numeric/theme regression: included in the 59-pass run; earlier focused run was 26 passed.
- Frontend fulfillment/EOD state tests: 19 passed across 2 files.
- Frontend production build: passed; Vite emitted only its existing large-chunk warning.
- Python compile, JSON validation, secret scan, and `git diff --check`: recorded after final gate execution.
