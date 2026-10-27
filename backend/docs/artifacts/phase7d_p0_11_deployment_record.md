# Phase 7D-P0.11 Deployment Record

## Final conclusion

`DEPLOYMENT_COMPLETE`

The fixed release was built from a new clean isolated worktree, transferred as locally built Linux AMD64 images, and deployed to `aastock.cloud` in backend-then-frontend order. All required runtime gates passed. The final deployment attempt did not trigger rollback.

## Release and isolation

- Local release: `98c111b684cb19de0e0e92cb46e1d675ef3e8d0a`
- Remote release: `98c111b684cb19de0e0e92cb46e1d675ef3e8d0a`
- Server release: `98c111b684cb19de0e0e92cb46e1d675ef3e8d0a`
- Git tree: `24a9961639dd7d8388fe8353a6e2e7eb8b955f03`
- Isolated build worktree: `/private/tmp/phase7d_p0_11_retry.mBNgDx/worktree`
- Remote ancestor check: passed; divergence was `0 0`
- Push: normal non-force push; result `Everything up-to-date`
- Main worktree was not a deployment input. It was only recorded as 6 tracked changes, 125 untracked entries, and 0 staged files after creation of requested artifacts.

## Image identities and transfer

| Service | Versioned tag | Image ID / digest | Platform | OCI revision | Source tree | Tar SHA-256 |
|---|---|---|---|---|---|---|
| backend | `tradingagents-backend:phase7d-p0-11-r2-98c111b-amd64` | `sha256:6e21f29a3e542847126408b98242df371681934b29c996ed94e8ae65e85a315d` | `linux/amd64` | `98c111b…` | `24a9961…` | `eb216e2d5cd0e3a753dc1dcf53c9bfadb27697eafeddb0c956ae3c772e3f609b` |
| frontend | `tradingagents-frontend:phase7d-p0-11-r2-98c111b-amd64` | `sha256:03120502202495dafad2eaca059d3665cf91ebfb2f653bcaa15d1dd155da170d` | `linux/amd64` | `98c111b…` | `24a9961…` | `39f445f42698ac86961e7251ec47f1b4447f0be77379f76c7e6601368cdf3ac2` |

Backend and frontend were built sequentially. The two server-side SHA-256 values exactly matched the local archives. Image configuration/history scans reported zero credential-pattern matches. No image was built on the server.

## Server preflight and preserved state

- Active Compose repository: `/opt/tradingagents`
- Pre-switch backend `/health`: HTTP 200
- Available memory: 854 MiB of 1.6 GiB
- Free disk on `/`: 22 GiB
- Preserved tracked modification: `docker-compose.staging.yml`
- Preserved untracked backup: `.env.staging.local.backup.20260728-130419`
- Overlap with the release diff: none
- Staged files: none

Strict host-key checking and public-key authentication were used for `admin@aastock.cloud`.

## Rollback protection

Before loading or switching the final-attempt images, the running images were tagged as:

- `aastock-mvp-backend:rollback-pre-phase7d-p0-11-r2-de3377b`
- `aastock-mvp-frontend:rollback-pre-phase7d-p0-11-r2-d89780a`

No old image, container, or volume was explicitly deleted. The final attempt did not invoke either rollback path. An earlier attempt in the same Phase did automatically restore the old backend when its Company API evidence session did not complete; that history is retained here, but it is not the final state.

## Backend switch and Company API acceptance

| Gate | Result |
|---|---|
| Backend image before | `sha256:de3377b3081876400226ef1e817574122083be83eeb8fcfb1206d1118c95d790` |
| Backend image after | `sha256:6e21f29a3e542847126408b98242df371681934b29c996ed94e8ae65e85a315d` |
| Backend container after | `8243d6fe795acce9df496674adc29dd60964bc4c7b1387baccf755834feb7508` |
| `/health` | HTTP 200, `{"status":"ok"}`, healthy |
| `/api/v2/company/CN/000725/profile` | HTTP 200; nonempty; no `AUTH_REQUIRED` |
| `/api/v2/company/CN/000725/history?period=annual` | HTTP 200; no `AUTH_REQUIRED` |

The profile response exposed the expected public Company fields. The history response included its public coverage, module status, period, source, warnings, and availability fields. Response bodies were kept as server-local acceptance evidence; no Token was recorded.

## Frontend and site acceptance

| Gate | Result |
|---|---|
| Frontend image before | `sha256:d89780ae4b5ec49e8ff8fd1b58e92141b357e07920e9f37de2cf8e6a1d10baad` |
| Frontend image after | `sha256:03120502202495dafad2eaca059d3665cf91ebfb2f653bcaa15d1dd155da170d` |
| Frontend container after | `386aa1b3caf399468c8433f39be57776f11d808e62f184e515bf4519d657cbf1` |
| `http://127.0.0.1:18080/` | HTTP 200 |
| `https://aastock.cloud/` | HTTP 200 |

Final server resources were 848 MiB available memory and 22 GiB free disk (`43%` used on `/`).

## Authorization and prohibited-operation audit

The Owner confirmed that the Tushare EOD authorization covers public commercial display, server-side caching, and AI research summaries. Only this conclusion is recorded; no Token or private customer-support information is stored.

No migration, `docker compose down`, `--remove-orphans`, server Docker build, force push, parallel build, traffic expansion, or explicit image/volume/container cleanup was performed.

