# CompanyV2 Page Acceptance Report — Phase 6O-3

Generated: 2026-07-09T00:29:24

## Scope

- Routes checked by API/static acceptance:
  - `/stocks/CN/600519?company_v2=1`
  - `/stocks/CN/000725?company_v2=1`
  - `/stocks/CN/601686?company_v2=1`
- Browser automation status: in-app browser unavailable in this Codex session (`No browser is available`), Playwright/Puppeteer not installed. Visual screenshots were not captured.
- Replacement decision: gate only; legacy Company Tab remains available.

## Scroll / Layout Checks

- `CompanyV2View.vue` has no `height: 100vh` or `overflow: hidden` page lock.
- Tables/JSON use horizontal overflow only; no nested vertical scroll container was added.
- Bottom sentinel added: `<div data-testid="company-v2-bottom-sentinel" />`.
- RawJsonDrawer is inline expand/collapse, not a body-locking overlay; closing it does not mutate `body.style.overflow`.

## API Acceptance Summary

| Symbol | modules_renderable | modules_unavailable | providers_timeout | baostock_aggregate_calls | cache second call |
| --- | ---: | ---: | ---: | ---: | --- |
| 600519 | 11 | 0 | 0 | 1 | hit, latency ~7ms |
| 000725 | 11 | 0 | 0 | 1 | hit, latency ~6ms |
| 601686 | 11 | 0 | 0 | 1 | hit, latency ~6ms |

## Module Visibility

For all three symbols, the live `debug/full?include_raw=false` response reports 11 renderable modules and 0 unavailable modules.
Financial modules render via fallback tables:

- profitability
- growth
- cashflow_quality
- solvency
- operation_capability
- dupont

## DataSourceBanner / Copy

- Forbidden legacy copy absent from CompanyV2 payload and frontend source:
  `DATA_MODE=free：BaoStock 和 AkShare 均未返回数据，请检查 ENABLE_BAOSTOCK / ENABLE_AKSHARE 配置。`
- CompanyV2 DebugPanel uses structured messages derived from `diagnosis.primary_issue`.

## Raw / Security

- `include_raw=false` responses do not contain `raw_full`.
- Checked payloads do not contain `secret`, `token`, or `local_path`.

## Console Errors / Screenshots

- Not visually verified because no browser surface is available in this session.
- Recommended manual follow-up: open the three URLs in a local browser and confirm the bottom sentinel is reachable after expanding/collapsing RawJsonDrawer.

## Replacement Gate Recommendation

- Recommend setting `VITE_COMPANY_TAB_VERSION=v2` for staged/default Company Tab evaluation.
- Do not delete legacy yet. Proceed to Phase 6O-4 only after one manual browser pass confirms scroll-to-bottom and no console errors.
