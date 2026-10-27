# Phase 7D-P0.12 Production Smoke and Observation Registration

## Conclusion

`PRODUCTION_MONITORING_REQUIRED`

The server, API, allowlist, container, resource, and sanitized-log smoke checks passed. The required real-browser product validation could not be completed because the browser runtime returned `No browser is available` and listed no available browser instances. API or curl output was not substituted for visual acceptance.

## Server identity and health

- Git HEAD: `98c111b684cb19de0e0e92cb46e1d675ef3e8d0a`
- Git tree: `24a9961639dd7d8388fe8353a6e2e7eb8b955f03`
- Backend image: `sha256:6e21f29a3e542847126408b98242df371681934b29c996ed94e8ae65e85a315d`
- Backend container: running, healthy, restart count 0, not OOM-killed
- Frontend image: `sha256:03120502202495dafad2eaca059d3665cf91ebfb2f653bcaa15d1dd155da170d`
- Frontend container: running, restart count 0, not OOM-killed
- Preserved server files: modified `docker-compose.staging.yml` and untracked `.env.staging.local.backup.20260728-130419`

Resources at capture time were 856 MiB available of 1.6 GiB RAM, 0 B of 4 GiB swap used, and 22 GiB free on `/` with 43% disk utilization.

## API and public-contract smoke

| Check | Result |
|---|---|
| `GET /health` | HTTP 200 |
| BOE profile | HTTP 200, `ok=true`, company name `京东方科技集团股份有限公司`, nonempty |
| BOE annual history | HTTP 200, `ok=true`, 6/6 modules available, no `AUTH_REQUIRED` |
| History positive allowlist | Zero violations |
| Token/raw/trace/provider URL/internal exception markers | Zero matches |
| `http://127.0.0.1:18080/` | HTTP 200 |
| `https://aastock.cloud/` | HTTP 200 |

The history response top-level keys were limited to the approved public contract. Module and row keys were validated against the module-specific positive allowlists in the deployed source tree.

## Log evidence

Only sanitized counters were collected from the deployed backend and kernel logs. Counts were zero for HTTP 5xx, health failures, OOM, disk I/O errors, `AUTH_REQUIRED`, Tushare failures/timeouts, AKShare/Eastmoney/Sina/Tencent or Tushare-news references, and public leak markers. This is a point-in-time internal operational check, not a production SLA.

## Browser acceptance blocker

The browser connection attempt returned:

```text
No browser is available
```

Browser discovery returned an empty list. Consequently the following remain visually unverified:

- BOE Company page shows a company name/profile rather than only the stock code.
- The Maotai recent-status UI visibly labels data as EOD/non-real-time and displays its source.
- `AI 半导体设备主题问题` visibly shows unavailable data, does not show completed research, and does not enter default LLM generation.

No alternative browser surface or HTTP-only result was presented as manual browsing evidence.

## 24-hour observation registration

- Start: `2026-09-10T00:59:53Z`
- End: `2026-09-11T00:59:53Z`
- No timer, cron job, scheduled scraper, or automatic polling task was created.

During this window, record only: 5xx/health failures/container restarts; Tushare failure rate/timeouts; Company profile/history empty-data ratio; abnormal memory/swap/disk use; and user-visible errors.

No code, container, migration, traffic, Provider, news-source, or fail-closed configuration was changed.

