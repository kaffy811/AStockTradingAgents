# Phase 7D-P0.8 Company Data + Stock Research Owner Release Review

## Decision

`OWNER_RELEASE_APPROVAL_READY`

技术候选可请求合并；公开部署仍等待 Owner 对 Tushare 商业展示、缓存、再分发和 AI 摘要使用权的书面确认，以及实际部署授权。

## Candidate identity and ancestry

- Release baseline: `5dad7228bb7b54338a946b49daeee5eae58348f9`, tree `0981783304376eed46a6a3276950aa95511f3b69`
- P0.1 original: `851264fa7a4cb1a2e58ad557d1a4c3ae910fc773`, tree `2e9e659cfb48a116dd3f7d621183e9d308fe6350`
- P0.2 original: `d5cab4aae988847fedb43483762f056b30e9416f`, tree `244ef8509153349ff9ac20c1e87198e6a1563710`
- P0.4 original: `c4a506c0c2fdcf985d779f005788f4059066605a`, tree `d821f6804a4a57dace95664e2249024e3d48b717`
- P0.5 review replay: `c812d4d2e572ffd08cfd56b8110c0ba87b0cab05`, tree `d821f6804a4a57dace95664e2249024e3d48b717`
- P0.6: `1c675f7fe6b018f3a280973698d9ada10f5c3ddd`, tree `1a7daa109e066b0c79d7f411b9db15615640b4e7`
- P0.7 final: `4434fc60feb652a7806d286f54c2175b979cbb4b`, tree `24a9961639dd7d8388fe8353a6e2e7eb8b955f03`

The original P0.1 → P0.2 → P0.4 commits form a direct linear chain from the baseline. P0.6 does not directly descend from the original P0.4 SHA: it descends from the clean P0.5 replay `c812d4d`. This is not content drift: original P0.4 `c4a506c` and replay `c812d4d` have the exact same Git tree `d821f6804a4a57dace95664e2249024e3d48b717`. P0.7 directly descends from P0.6.

Baseline → P0.7 contains 23 files, 2,153 insertions and 20 deletions. `git diff --check` passed.

## Complete file scope

```text
HKNA/update_report/update_137.md
HKNA/update_report/update_138.md
HKNA/update_report/update_140.md
HKNA/update_report/update_142.md
backend/app/agents/chat_orchestrator.py
backend/app/datasource/tushare_client.py
backend/app/routers/company_v2_debug.py
backend/app/services/stock_eod_numeric_validation.py
backend/app/services/tushare_eod_gateway.py
backend/docs/artifacts/phase7d_p0_2_company_and_stock_research_matrix.md
backend/docs/artifacts/phase7d_p0_2_tushare_eod_gateway.md
backend/docs/artifacts/phase7d_p0_2_tushare_eod_runtime.json
backend/docs/artifacts/phase7d_p0_4_public_response_allowlist.md
backend/docs/artifacts/phase7d_p0_4_public_response_allowlist_matrix.json
backend/tests/fundamental/test_phase7d_p0_1_public_company_history.py
backend/tests/fundamental/test_phase7d_p0_2_tushare_eod_gateway.py
backend/tests/fundamental/test_phase7d_p0_6_stock_eod_numeric_validation.py
backend/tests/test_phase7d_p0_7_theme_fail_closed.py
frontend/src/api/companyV2.js
frontend/src/tests/phase7dP01CompanyModuleIsolation.test.js
frontend/src/tests/phase7dP02TushareEodCompanyPage.test.js
frontend/src/tests/researchFulfillment.test.js
frontend/src/views/CompanyV2View.vue
```

## Approved functional scope

### Anonymous Company history

The public response is projected through module-specific positive allowlists. Unknown modules, scalar fields, nested objects, lists and unknown warning codes are denied by default.

- `profitability`: `period`, `roe`, `gross_margin`, `net_margin`, `net_profit`
- `growth`: `period`, `main_business_revenue`, `net_profit`, `net_profit_yoy`, `parent_net_profit_yoy`, `equity_yoy`, `asset_yoy`, `eps_yoy`
- `cashflow_quality`: `period`, `ocf_to_np`, `ocf_to_revenue`
- `solvency`: `period`, `current_ratio`, `quick_ratio`, `cash_ratio`, `debt_ratio`, `equity_multiplier`
- `operation_capability`: `period`, `asset_turnover`, `inventory_turnover`, `receivable_turnover`
- `dupont`: `period`, `roe`, `net_margin`, `asset_turnover`, `equity_multiplier`, `dupont_formula_status`

Warnings use only four controlled local codes/messages: `CFO_TO_NP_DENOMINATOR_SENSITIVE`, `DUPONT_FORMULA_MISMATCH`, `FIELD_CONFLICT`, and `OUTLIER_REQUIRES_REVIEW`. Provider messages are not copied. Anonymous history remains HTTP 200 and does not return `AUTH_REQUIRED`.

### Company and EOD modules

Company profile/history and EOD profile/quote/valuation/financial modules retain independent status and availability. One failed module does not erase successful modules or the entire page. Profile exceptions return the fixed public message `PUBLIC_PROFILE_UNAVAILABLE`, without `str(exc)`.

The Tushare gateway permits only structured `stock_basic`, `daily`, `daily_basic`, `fina_indicator`, and explicitly mapped `index_daily`. Public EOD facts are restricted to approved profile, OHLCV, valuation and financial fields with source, unit, freshness and `as_of`. It is explicitly EOD/not real-time.

### Request-local numeric evidence

Stock research builds request-local evidence containing metric, canonical/display values, unit, as-of date, required financial report period, approved source and request-local evidence ID. Explicit rounding and approved CNY unit conversions are supported. Fabricated values, wrong units, stale/missing report periods, missing sources and unexplained integer tokens fail validation. Validation failure returns safe `partial` output and removes unverified numbers. This module does not import or modify the global Report RAG numeric validator.

### Theme fail-closed route

Unresolved industry/theme/supply-chain/beneficiary-company questions return the stable contract:

```text
fulfillment=unavailable
reason_code=NO_APPROVED_INDUSTRY_NEWS_SOURCE
scope=unapproved_industry_theme_research
sources=[]
as_of=null
requires_symbol=false
```

This route runs before entity resolution, LLM generation and market/news Providers. Explicit stock symbols and reliable company names retain priority for stock EOD research.

### Frontend

The Company page consumes the public history/EOD contracts, displays module-level success/unavailable/partial state and empty-data limitations, and does not present unavailable research as completed.

## Explicit exclusions

The baseline → candidate file list and content diff contain no:

- Dockerfile, Compose, dependency, lockfile, migration or `.env` changes;
- Token/key value or new Provider credential configuration;
- Tushare news endpoint or implementation;
- AKShare, Eastmoney, Sina or Tencent production fallback/call path;
- global authentication change;
- RAG/citation validator or global Report RAG numeric-validator change;
- deployment, migration, rollout or capacity expansion.

The only `tushare_client.py` credential-related change removes the prior token-prefix log and replaces it with `credential configured`; no credential value is added. Documentation/tests mention forbidden Providers only as zero-call assertions or exclusions.

The primary worktree remains on baseline and contains unrelated pre-existing tracked modifications and untracked files. Review diff, tests and images were obtained from Git objects and fixed candidate images; primary-worktree business files were never mounted or copied into the candidate runtime.

## P0.7.2 pure-image runtime gate

Session `72ba95bf-03b4-479a-93e0-3f7f998be7f1` ran Q1 → Q2 → Q3 → Q4 once each, serially, with each atomic JSON record persisted before continuing. These are request-local controlled-fixture results, not live market validation.

| Q | fulfillment / reason | scope | as_of | LLM | Tushare boundary | AKShare / Eastmoney / Sina / Tencent | Live Provider |
|---|---|---|---|---:|---:|---:|---:|
| Q1 | `fulfilled` / null; profile non-empty; history no AUTH_REQUIRED | `company_profile_and_eod` | `2026-08-31` | 0 | 4 fake-client calls | 0 / 0 / 0 / 0 | 0 |
| Q2 | `fulfilled` / null; `600519.SH`; EOD/non-real-time; numeric valid | `stock_eod_research` | `2026-08-31` | 0 | 1 fake-gateway call | 0 / 0 / 0 / 0 | 0 |
| Q3 | `fulfilled` / null; report period `2026-06-30`; valid=true; unsupported=[] | `stock_eod_research` | `2026-08-31` | 0 | 1 fake-gateway call | 0 / 0 / 0 / 0 | 0 |
| Q4 | `unavailable / NO_APPROVED_INDUSTRY_NEWS_SOURCE` | `unapproved_industry_theme_research` | null | 0 | 0 | 0 / 0 / 0 / 0 | 0 |

The separate P0.2 artifact records controlled live Tushare EOD validation on 2026-09-03: `stock_basic`, `daily`, `daily_basic`, and `fina_indicator` were each called twice; `index_daily`, Tushare news, AKShare, Eastmoney, Sina and Tencent were zero. The raw Token value was not recorded. P0.2 evidence is not represented as part of the fixture-only P0.7.2 session.

## Image identity and integrity

- Backend: `sha256:2a7984bc6785285249e2d7343c8f86225a54c8eb7302583283419d63d52717b1`
- Frontend: `sha256:02dbad039d46b4ae7e632190a83c9c10e0681a2620346bebe771f8c997650228`
- Both OCI revisions: `4434fc60feb652a7806d286f54c2175b979cbb4b`
- Runtime/inspection/test containers: `Mounts=[]`; runtime validation was network-disabled.

Five critical backend source hashes matched byte-for-byte between the candidate Git tree and backend image:

```text
a81e32cf0c224b78a2f627fbc4003d7efa3008deddc671b455e692a6b26d356d  chat_orchestrator.py
891353fcae05bf00e71020747b79c9941413c70badb7dd88d5af2efa69571923  tushare_client.py
2a190ab710e60f8f5284c3d145c1e0e33c3f275d85939fe55acb555da3426017  company_v2_debug.py
d2dbbcf098b9d0c9f18003593eab21dcbcfea0d25994ebee933e3dae6565faa7  stock_eod_numeric_validation.py
7a944ea72938fa27ee0dce01c0c392f1981cbd16453e3c9278ffa8cd1a337e3c  tushare_eod_gateway.py
```

Image config/history scans found zero embedded bearer credentials, application Token/API-key assignments, Authorization values or credential-bearing database/Redis URLs. P0.7.2 response JSON found zero such values. The backend base image exposes a standard Python-distribution `GPG_KEY` environment variable name; it is not an application credential or Provider Token.

## Verification

Candidate-source tests were exported directly from Git object `4434fc…`, copied into a new no-mount/no-network backend-image container, and run against image application code:

```text
56 passed, 1 warning in 1.93s
```

The warning is Python 3.13 deprecation notice from passlib's `crypt` import, not a functional failure. The original production image omits test files; two preliminary commands failed before collection due to an incorrect image-relative path and missing `PYTHONPATH`. No tests ran in either preliminary container. The corrected independent container passed all 56 tests.

P0.2/P0.4 recorded broader prior gates: backend related tests passed, frontend release suite passed with zero worker startup timeout, frontend production build passed, Python compile/JSON validation/secret scan/diff check passed. P0.8 additionally passed baseline→candidate `git diff --check`.

## Independent pre-existing Report RAG test issue

`backend/tests/test_phase6w_r1_2_numeric_pipeline.py` remains a separate follow-up: 7 failed and 15 passed identically at baseline `5dad722`, P0.5 `c812d4d` and final candidate `4434fc6`.

Classification: `PRE_EXISTING_TEST_INFRA`, mechanism `FIXTURE_CONTRACT_DRIFT`. The fixture patches `DeepSeekClient` but does not provide the settings API-key contract; `RuntimeError("AI API Key 未配置")` occurs before client construction. Neither the mock nor live Provider is called. This is not a candidate regression and does not authorize changes to the global numeric validator, Report RAG logic or assertions.

## Non-code prerequisites before public release

1. Obtain written Owner/legal confirmation that the Tushare agreement permits commercial display, caching, redistribution and AI-generated summaries for the intended public product. Technical approval is not licensing approval.
2. Obtain explicit deployment authorization and apply server resource controls: never build backend and frontend concurrently; deploy them sequentially. On low-memory servers, prefer importing the already verified images instead of building locally.

No push, merge, deployment, migration, rollout or business-code modification was performed in this review.
