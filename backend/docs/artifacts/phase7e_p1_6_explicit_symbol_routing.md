# Phase 7E-P1.6 Explicit Symbol Routing

## Conclusion

`OWNER_REVIEW_READY`

This candidate was developed from `184dcadb47b52245b2ffe3a4b56418f9a30fc8d6` in an isolated worktree. It was not pushed, merged, deployed, or exercised against a live provider.

## First root cause

The deterministic EOD intent expression did not recognize `公司资料` or `EOD`. Consequently, `CN/000725 公司资料 + EOD` missed the pre-memory stock route. Later orchestration could incorporate conversation memory and dispatch to `general_financial_answer_skill`, allowing a previous `600519` entity to supersede the current-turn identifier.

A second parser defect allowed an exchange-qualified token such as `000725.SH` to be evaluated again as bare `000725`, bypassing the suffix mismatch rejection.

## Minimal fix

- Recognize company-profile, EOD, quote, close, valuation, PE, PB, ROE, and financial-metric intents.
- Detect an explicit CN security token in the raw current-turn message before memory, page context, skill routing, general tools, or LLM execution.
- Resolve and validate the token through the existing security master resolver; unresolved six-digit candidates return controlled `unavailable`.
- Preserve official-report/CNINFO routing and the unapproved-theme fail-closed gate.
- Include Company Profile fields and canonical Tushare `ts_code` in the EOD result; expose the latest verified financial `report_period`.
- Preserve the request-level numeric validator without changing its rules or evidence allow-set.

## Routing priority matrix

| Input condition | Route | Context allowed | Downstream restrictions |
|---|---|---|---|
| Explicit symbol + official announcement/report intent | `official_company_events` | Current turn | Existing CNINFO path |
| Explicit symbol + Company/EOD/price/valuation/financial intent | `stock_eod_research` | Current turn only for entity selection | LLM, general skill, generic quote/news and unapproved providers: 0 |
| Explicit company name + EOD intent | `stock_eod_research` | Resolver-validated name | Same controlled EOD path |
| Unapproved industry/theme request | `industry_news` fail-closed | None | `NO_APPROVED_INDUSTRY_NEWS_SOURCE`; LLM/providers: 0 |
| Unknown explicit six-digit candidate + EOD intent | controlled `unavailable` | No fallback to history | No gateway, skill, tool, or LLM call |

## Controlled runtime matrix

All results below use redacted fixtures matching the Tushare gateway contract. They are not live-provider validation.

| Query | Result | Canonical symbol | Numeric evidence | LLM | Generic skill/tools | Unapproved providers |
|---|---|---|---|---:|---:|---:|
| `CN/000725 公司资料 + EOD` | `fulfilled` | `000725.SZ` | valid; unsupported `[]` | 0 | 0 | 0 |
| `贵州茅台近期情况` | `fulfilled` | `600519.SH` | valid; unsupported `[]` | 0 | 0 | 0 |
| `600519 财务指标、ROE、估值` | `fulfilled` | `600519.SH` | valid; unsupported `[]` | 0 | 0 | 0 |
| `AI 半导体设备主题问题` | `unavailable / NO_APPROVED_INDUSTRY_NEWS_SOURCE` | n/a | n/a | 0 | 0 | 0 |

The controlled EOD facade is invoked once per successful stock request. Live Tushare endpoint calls are 0. AKShare, Eastmoney, Sina, Tencent, generic real-time quote/news tools, and synthesis LLM calls are all 0.

## Cross-turn evidence

- Same session: `600519` followed by `CN/000725 公司资料 + EOD` resolves the second turn to `000725.SZ`.
- Reverse order resolves the second turn to `600519.SH`.
- Separate sessions and a request without session history preserve the current-turn symbol.
- `CN/`, bare six-digit, `.SZ`, `.SH`, and explicit company-name forms are covered.
- Wrong exchange suffixes are rejected rather than silently treated as bare codes.
- Tests make the memory loader raise if invoked on explicit-symbol EOD requests, proving that these requests bypass history during entity selection.

## Verification

- Related backend route, theme, Company history, Tushare gateway, numeric evidence, and resolver tests: **90 passed**.
- Frontend fulfillment/status targeted tests: **24 passed**.
- Full frontend suite: **769 passed**.
- Frontend production build: passed (existing Vite large-chunk advisory only).
- Python compile, JSON validation, secret scan, and `git diff --check`: recorded in the runtime manifest.

## Scope exclusions

No changes were made to Report RAG runtime, financial interpretation depth, EOD unit formatting, UI completion wording, industry-news providers, Docker, dependencies, lockfiles, migrations, tokens, provider configuration, Company public-history allowlist, or the global Report RAG numeric validator.
