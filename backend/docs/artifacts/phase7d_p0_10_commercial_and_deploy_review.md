# Phase 7D-P0.10 Commercial Authorization and Deployment Review

## Decision

`OWNER_COMMERCIAL_AUTHORIZATION_REQUIRED`

The local release is technically ready for an Owner push decision, but public deployment of Tushare-derived data is not authorized by the evidence available in this repository. A successful Token call or a 2000/2100-point account proves endpoint access only; it does not prove commercial display, caching, redistribution, or AI-summary rights.

No push, remote connection, deployment, image build, migration, rollout, branch change, staging change or business-code modification was performed.

## Release identity

```text
release/demo-staging = 98c111b684cb19de0e0e92cb46e1d675ef3e8d0a
tree                 = 24a9961639dd7d8388fe8353a6e2e7eb8b955f03
candidate parent     = 4434fc60feb652a7806d286f54c2175b979cbb4b
candidate tree       = 24a9961639dd7d8388fe8353a6e2e7eb8b955f03
```

P0.9.3 established that merge commit `98c111b...` contains no file content beyond the approved candidate and is accepted as the local release integration result.

## Technical gates already passed

1. Anonymous Company history uses module-specific positive allowlists; unknown fields and provider/debug content are denied by default.
2. Company profile/history and EOD modules isolate failures; a failed module does not erase other successful page content, and profile exceptions do not expose `str(exc)`.
3. The approved Tushare EOD gateway covers `stock_basic`, `daily`, `daily_basic`, `fina_indicator`, and only explicitly mapped `index_daily`; output is EOD/not real-time.
4. Stock research uses request-local numeric evidence with metric, canonical/display value, unit, as-of date, financial report period, source, evidence ID and unsupported-token validation. It does not modify the global Report RAG validator.
5. Unresolved industry/theme/news questions fail closed with `unavailable / NO_APPROVED_INDUSTRY_NEWS_SOURCE` before LLM or Provider execution.
6. P0.7.2 pure-image Q1–Q4 gate passed in a controlled, no-mount/no-network fixture session. Q4 recorded zero LLM, Tushare-news, AKShare, Eastmoney, Sina and Tencent calls.
7. P0.2 separately recorded controlled live access to approved Tushare EOD endpoints; it did not call Tushare news or public scraping Providers. It is endpoint/runtime evidence, not licensing evidence.
8. P0.8 candidate regression passed 56 backend tests in the verified image; P0.9 passed 24 related frontend tests. P0.9.3 verified candidate/merge tree identity and prohibited-scope cleanliness.
9. Baseline-to-release content contains no Tushare news implementation or AKShare/Eastmoney/Sina/Tencent production fallback in this slice.

These gates establish software behavior and release integrity only. They do not grant data rights.

## Commercial authorization evidence

### What is proven

- The P0.2 runtime artifact records that the configured account could call the selected EOD endpoints at that time.
- Official endpoint documentation states that `daily_basic` and `fina_indicator` require at least 2000 points, while `daily` has a lower basic threshold. This describes access and frequency tiers.
- The product already exposes source/as-of metadata, EOD/non-real-time wording, controlled limitations and an investment disclaimer.

### What is not proven

The repository contains no executed commercial data agreement, authorization letter, enterprise license, invoice-linked rights schedule, or Tushare communication granting this public website permission to:

- display Tushare-derived values to unauthenticated/public users;
- cache or persist EOD, valuation or financial-indicator data server-side;
- redistribute those values through an API or webpage;
- use those values as evidence for AI-generated analysis summaries;
- use Tushare branding/source attribution in the intended public presentation.

### Official terms signal

The current official [Tushare Data Service Agreement](https://tushare.pro/document/1?doc_id=405) describes the ordinary service license as personal, non-transferable, revocable and non-commercial, for personal viewing. The official [points/permissions documentation](https://tushare.pro/document/1?doc_id=108%E3%80%81) explains that points determine which APIs and call frequencies an account can access. The [daily_basic documentation](https://tushare.pro/document/2?doc_id=32) and [fina_indicator documentation](https://tushare.pro/document/2?doc_id=79) confirm 2000-point access thresholds, but do not grant public-display or redistribution rights.

Tushare's AI-oriented documentation discusses AI workflows and local caching as product guidance. It does not override the explicit license terms or constitute a project-specific commercial grant. A 2100-point balance therefore appears sufficient for selected endpoint access but is insufficient evidence for the proposed commercial/public uses.

This is a release-governance finding, not a legal opinion. Owner should obtain written confirmation from Tushare or qualified counsel.

## Required written authorization checklist

Before public deployment, retain a dated written agreement or Tushare confirmation that identifies the account/entity/product and explicitly answers:

| Intended use | Required confirmation |
|---|---|
| Public website display | Permitted audience, fields, markets, delay requirements and display limits |
| Server-side cache/storage | Permitted retention, refresh cadence, database/cache scope and deletion obligations |
| Redistribution | Whether browser/API delivery is permitted and under what rate/field restrictions |
| AI analysis summaries | Whether derived text, calculations and model-generated summaries using Tushare facts are permitted |
| Attribution | Required Tushare name/logo/link wording and whether prior trademark approval is needed |
| Product wording | Required EOD/delay notices, accuracy caveats and investment disclaimer |
| 2000/2100 tier | Written confirmation that this account/tier covers the above commercial product uses, or identification of the required enterprise/data license |

Until this evidence exists, do not enable public Tushare-backed Company/EOD/stock-research responses. Endpoint availability must never be represented as licensing approval.

## Owner decision split

- **Local release integrity:** accepted.
- **Git push:** technically ready, but requires an explicit Owner push authorization. A push alone must not trigger deployment or public enablement.
- **Public deployment of Tushare-backed capability:** blocked pending written commercial authorization.
- **Deployment preparation:** may be reviewed now; no server action is authorized by this document.

## Minimal deployment plan after both approvals

### 0. Approval gate

Proceed only after both are recorded:

1. Owner explicitly authorizes pushing exact commit `98c111b...`.
2. Written Tushare commercial-use authorization covers display, cache/storage, redistribution, AI summaries and attribution.

Any ambiguity stops the release.

### 1. Push exact local release commit

Pre-push local checks:

```text
git rev-parse release/demo-staging
git rev-parse release/demo-staging^{tree}
git merge-base --is-ancestor origin/release/demo-staging release/demo-staging
git diff --name-status 4434fc60feb652a7806d286f54c2175b979cbb4b 98c111b684cb19de0e0e92cb46e1d675ef3e8d0a
```

Expected: HEAD `98c111b...`, tree `24a996...`, remote is ancestor, candidate-to-release diff empty. Then use a normal fast-forward push of the exact local ref; do not force-push:

```text
git push origin 98c111b684cb19de0e0e92cb46e1d675ef3e8d0a:refs/heads/release/demo-staging
```

Stop on any rejection or changed remote head. Do not amend, rebase or force-update.

### 2. Server read-only preflight

Connect only after separate deployment authorization. Before changing anything, record:

```text
git rev-parse HEAD
git rev-parse HEAD^{tree}
git status --short
uname -m
free -h
df -h
docker ps --format <read-only inventory>
docker inspect <current backend/frontend containers>
docker image inspect <current and candidate image references>
```

Stop if the server checkout is dirty, HEAD/ref is unexpected, free memory/disk is inadequate, current containers are unhealthy, the previous image IDs are unknown, or architecture is incompatible.

### 3. Image provenance and architecture gate

Locally verified images:

```text
backend  sha256:2a7984bc6785285249e2d7343c8f86225a54c8eb7302583283419d63d52717b1
tag      tradingagents-backend:phase7d-p0-7-4434fc6
size     243318099 bytes

frontend sha256:02dbad039d46b4ae7e632190a83c9c10e0681a2620346bebe771f8c997650228
tag      tradingagents-frontend:phase7d-p0-7-4434fc6
size     29792320 bytes

platform linux/arm64
OCI revision 4434fc60feb652a7806d286f54c2175b979cbb4b
validated tree 24a9961639dd7d8388fe8353a6e2e7eb8b955f03
```

The images' revision is the candidate parent rather than merge SHA, but P0.9.3 proved both commits have the identical tree. Record this mapping in deployment evidence.

On a 1.6GB server, prefer transferring and loading these verified images instead of building. This is allowed only if `uname -m` reports ARM64/aarch64. If the server is x86_64/amd64, stop: current images are incompatible. Build and validate linux/amd64 images on a separate adequately resourced builder in a separately authorized phase; never build them on the 1.6GB server.

After import, verify loaded image digest/ID, platform, OCI revision and expected tags. Resolve Compose service image names with a read-only `docker compose config --images`; map the verified imported images without invoking a build. Use `--no-build` for every update.

### 4. Sequential backend update

- Record the currently running backend image ID as the rollback target.
- Do not run migrations.
- Do not stop the entire stack.
- Update only backend with the imported verified image and `--no-build`.
- Wait for container health and run the minimal anonymous Company/EOD and fail-closed smoke checks.
- Confirm logs contain no credential/provider raw details.
- On any failure, stop and roll back backend before considering frontend.

### 5. Sequential frontend update

Only after backend health and smoke checks pass:

- Record the current frontend image ID.
- Update only frontend with the imported verified image and `--no-build`.
- Verify Nginx/container health, Company empty/partial states, EOD non-real-time wording and Q4 unavailable presentation.
- On any failure, stop and restore the prior frontend image.

Backend and frontend must never be built or updated concurrently.

### 6. Explicitly prohibited deployment commands/actions

- no `docker compose build` or server-side Docker build;
- no migration or Alembic command;
- no `docker compose down`;
- no `--remove-orphans`;
- no volume deletion/pruning or database cleanup;
- no parallel backend/frontend update;
- no traffic expansion or feature-source expansion;
- no unapproved news Provider enablement.

### 7. Non-destructive rollback

Before each service update, record its exact known-good image ID/tag and container configuration. If a health/smoke gate fails:

1. stop further rollout;
2. re-associate only the affected service with its recorded previous image;
3. recreate only that service with `--no-build`;
4. verify health and the previous public behavior;
5. retain logs and failed-image metadata for attribution.

Do not use destructive Git rollback, reset, force-push, `down`, volume removal, migration rollback or data deletion. If the previous image is not locally present and verified before update, do not begin deployment.

## Final Owner action

Obtain and archive written Tushare authorization before approving public deployment. After that evidence is reviewed, Owner may separately authorize the exact push and the staged deployment plan above.
