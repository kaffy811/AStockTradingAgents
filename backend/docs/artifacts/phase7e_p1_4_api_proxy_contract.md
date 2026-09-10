# Phase 7E-P1.4 — Production API Reverse-Proxy Contract

## Conclusion

`OWNER_RELEASE_REVIEW_READY`

The candidate is based on production revision `fdcdc264e9178f7bb432f9101092b08c78af1ee6` and changes only frontend Nginx routing, dedicated contract tests, and delivery documentation. It uses no live data, production Token, database, or external Provider.

## Root cause and corrected rules

The deployed configuration only had `location ^~ /api/v1/`. Requests under `/api/v2/` and `/health` therefore reached the generic `location /` block, whose `try_files` returned `index.html` with HTTP 200.

The candidate replaces the version-specific API boundary with:

- `location = /api` → backend;
- `location ^~ /api/` → backend, preserving v1 and covering v2/future versions;
- `location = /health` → backend `/health`;
- `location ^~ /health/` → backend, so unknown health subpaths preserve backend 404;
- `proxy_intercept_errors off` in API and health proxy blocks;
- `location /` remains the only SPA `try_files ... /index.html` fallback.

`proxy_pass http://backend:8000` intentionally has no URI suffix in the `/api/` block, so the original `/api/v1/...` or `/api/v2/...` path and query string are forwarded unchanged. The exact `/health` block uses `proxy_pass http://backend:8000/health` to map precisely to the backend liveness endpoint.

## Automated tests

Two test layers were added:

1. `phase7eP14ApiProxyContract.test.js` verifies the Nginx location precedence, version-independent API boundary, health boundary, non-interception of errors, and isolated SPA fallback.
2. `nginx_proxy_contract_harness.py` supplies a standard-library mock backend and checks real HTTP responses from the pure frontend image. It contains no production credentials or data.

Targeted Vitest: 1 file, 5 tests passed. Full frontend gate: 70 files, 769 tests passed, zero failures and zero worker timeouts.

## Pure frontend image

| Property | Result |
|---|---|
| Image | `tradingagents-frontend:phase7e-p1-4-api-proxy-contract` |
| Image ID | `sha256:55a533d74711e0c038847d01ca91dc650ca618aa3f4669d92875ad9f331b945e` |
| Platform | `linux/amd64` |
| OCI revision | `fdcdc264e9178f7bb432f9101092b08c78af1ee6` |
| Frontend mounts | `[]` |
| Mock backend mounts | `[]` |
| `nginx -t` | passed |
| Production build | passed |

The image was built locally from the isolated candidate worktree. The mock backend used controlled fixture JSON only; no live stock data or real Token was used.

## HTTP contract matrix

| Path | HTTP | Content-Type | Result |
|---|---:|---|---|
| `/api/v1/ping` | 200 | `application/json` | v1 remains proxied |
| `/api/v2/company/CN/000725/profile` | 200 | `application/json` | v2 profile is never HTML |
| `/api/v2/company/CN/000725/history?period=annual` | 200 | `application/json` | query and backend JSON preserved |
| `/api/v1/unauthorized` | 401 | `application/json` | backend status/body preserved |
| `/api/v1/forbidden` | 403 | `application/json` | backend status/body preserved |
| `/api/v2/missing` | 404 | `application/json` | no SPA rewrite |
| `/api/v2/invalid` | 422 | `application/json` | no SPA rewrite |
| `/api/v2/failure` | 500 | `application/json` | no SPA rewrite |
| `/health` | 200 | `application/json` | real backend health |
| `/health/missing` | 404 | `application/json` | no SPA rewrite |
| `/stocks/CN/000725` | 200 | `text/html` | frontend page still uses SPA fallback |

All API/health mock responses retained the backend fixture request ID. HTTP contract result: 11 passed, 0 failed.

## Scope audit

Changed files are limited to:

- `frontend/nginx.conf`
- `frontend/src/tests/phase7eP14ApiProxyContract.test.js`
- `frontend/tests/nginx_proxy_contract_harness.py`
- this review, runtime JSON, and `update_161.md`

No backend route, stock identifier routing, Tushare, CNINFO, database, Docker Compose, dependency, lockfile, Token, migration, RAG, UI wording, scheduler, news Provider, or `.SZ/.SH` handling was changed.

## Remaining release boundary

This is a local candidate only. It has not been pushed, merged, or deployed. Owner release review should verify the final diff and commit identity, then authorize a separate frontend-only deployment and public `/api/v2`/`/health` smoke if accepted.
