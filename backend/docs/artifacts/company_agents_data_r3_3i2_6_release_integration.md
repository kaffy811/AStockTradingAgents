# Phase 6W-R3.3I.2.6 — Release Integration Readiness Audit

## Final decision

`PURE_IMAGE_PROVENANCE_NOT_READY`

Traffic: `HOLD_1_PERCENT`

The final pure image for commit `154c65c7` is reproducible and its source hashes match Git. However, the successful Q3 trace was executed by an earlier snapshot image, not by the final pure-commit image. Source equivalence is not substituted for runtime image provenance. The Q3 result is therefore excluded from release evidence, and no integration branch, integration runtime request, or integration commit was created.

## 1. Workspace boundary

- Main workspace branch/HEAD: `release/demo-staging` / `b055da8495c54bb37625f0b0e0f94b4d4a627de2`.
- Fix branch/HEAD: `r33e-pgvector-portability` / `154c65c7df236db74fd37ea8167ca15e72241f0a`.
- Main workspace historical dirty files remained untouched: `backend/Dockerfile`, `backend/app/main.py`, `backend/app/services/report_embedding_provider.py`, `backend/pyproject.toml`, `backend/uv.lock`.
- No reset, clean, checkout, merge, cherry-pick, or overwrite was performed in the main workspace.
- No `r33i-agent-integrity-rc` branch was created because the Step 1 provenance gate failed.

## 2. Pure image evidence

### Final pure-commit image

- Tag: `tradingagents-backend:rc-r33i2-5-154c65c`.
- Image digest/ID: `sha256:911cf927b7255f920cacadc750af7ffce6632a5b73f8dfb87caa961aed3b0383`.
- OCI revision: `154c65c7df236db74fd37ea8167ca15e72241f0a`.
- Source: `pure-detached-worktree`.
- Commit: `154c65c7df236db74fd37ea8167ca15e72241f0a`.

| Key file | Git blob at `154c65c7` | Image SHA-256 |
|---|---|---|
| `backend/app/agent/report_chat_copilot_agent.py` | `167aaf6359f55473a5278b3eff94a9554e09c601` | `f75847ed1f6826b8c9619df0b3133d91ea1ae9e68f754a481740e155569fb13d` |
| `backend/app/services/report_derived_fact_service.py` | `6b6c7cefedac838a8185671c1387dd005a20eb30` | `cd5462036d7ed4c1b869371ac44229ba16f811507c358468bbd02aa641d1d096` |

For both files, `git rev-parse HEAD:path == git hash-object path`; image bytes produce the recorded SHA-256. Thus OCI revision and source content are valid.

### Image that actually ran successful Q3

- Tag: `tradingagents-backend:rc-r33i2-5-snapshot`.
- Digest: `sha256:08587ed18a9c2ed59c996bb76bc2f45b5876b05f6418fafa7ce0e42466e01e42`.
- OCI revision: `r33i2-5-snapshot-36f67bc69e9f`.
- OCI source: `28870a13-plus-scoped-diff-36f67bc69e9f`.
- Container: `ee83239bb769e54b7ebaa284a05e0eb6e5e22ea72454e486a77724abcf74a26e`.
- Mounts: `[]`; no source bind mount.
- Network: isolated `tradingagents-r33i-run-net`.
- PostgreSQL: `r33i-run-postgres`, container `0c513420c58202462f9eb50a0eab6c2eaff6a8f27bcad61229f8a4b2e8535d41`.
- Redis: `r33i-run-redis`, container `f4b5dc55b5a4e67a53fa942707119c930341f3205b73fc2ed7e22fd2a45fceab`.

Successful request `9cf98947`, trace `819c10bf-dcc6-4aaa-a817-1bef4346dae1`, persistently records:

```text
git_sha = r33i2-5-snapshot-36f67bc69e9f
runtime_image_identity = sha256:08587ed18a9c2ed59c996bb76bc2f45b5876b05f6418fafa7ce0e42466e01e42
final_status = completed
```

This does not equal final image digest `sha256:911cf9...` or OCI revision `154c65c7...`. The later final image was rebuilt with matching application hashes but did not receive a Q3 request. Therefore the acceptance statement “Q3 succeeded on the pure `154c65c7` image” cannot be proven.

## 3. Commit graph and dependency audit

- Merge base: `b055da8495c54bb37625f0b0e0f94b4d4a627de2`.
- Reverse path to fix head:
  1. `79323b7` — vector migration portability.
  2. `5e9977a` — structured trace evidence provenance.
  3. `28870a1` — derived operands and canonical citation boundary.
  4. `154c65c` — request-local formula constant boundary.

| Commit | Purpose | Actual dependency | Required for RC | Out-of-scope files |
|---|---|---|---|---|
| `79323b7` | Vector migration portability | Parent of `5e9977a` in Git history | Not functionally required by this credibility fix; must not enter via whole-branch merge | Yes: multiple migrations, `pyproject.toml`, `uv.lock`, vector support and unrelated artifact |
| `5e9977a` | Trace input and structured-evidence audit | Base migration `q5r6s7t8u9v0` already exists on release; adds trace service APIs and `input_payload` schema used downstream | Semantically required by `28870a` as authored | Yes for this feature-only scope: trace migration and trace model/service changes |
| `28870a1` | Structured operands, derived facts, canonical citation validation, strict harness/tests | Directly based on and calls APIs introduced by `5e9977a` | Yes, but not safely replayable alone | No Docker/dependency/migration in its own diff; includes phase artifacts/harness/tests |
| `154c65c` | Provenanced request-local ratio formula policy | Directly depends on `28870a1` service/Agent implementation | Yes after `28870a1` | No Docker/dependency/migration in its own diff |

Evidence of semantic dependency: `28870a`'s `report_chat_copilot_agent.py` calls `structured_financial_snapshot()`, which is absent at release HEAD and introduced by `5e9977a`. It also relies on durable trace `input_payload`; the corresponding Alembic revision is in `5e9977a`. `numeric_token_provenance()` already exists at release HEAD, so that symbol alone is not the dependency.

The full branch diff includes forbidden release content: vector and trace migrations, `backend/pyproject.toml`, `backend/uv.lock`, migration support code, and unrelated artifacts. `git diff --check release/demo-staging..r33e-pgvector-portability` also reports pre-existing trailing whitespace in the `79323b7` vector artifact. The individual `28870a` and `154c65c` commits passed their own staged diff checks.

No Dockerfile, `main.py`, embedding-provider, warmup, or frontend change exists in the committed branch range; the similarly named files in the main workspace are uncommitted historical dirty changes and were not touched.

Conflict status is deliberately `not tested`: proving replay conflicts would require creating the Step 3 integration worktree, which was not authorized after the mandatory Step 1 gate failed. No semantic conflict was auto-resolved or guessed.

## 4. Integration candidate, tests, image, and runtime

Not executed because pure-image runtime provenance was not ready:

- No temporary `r33i-agent-integrity-rc` branch or integration commit.
- No cherry-pick or replay.
- No integration 48-test run, imports/static validation, or integration image build.
- No additional Q3 request.
- No migration execution. A trace-schema migration dependency exists in the authored chain; it cannot be described as “No migration required” without a separate scoped integration decision.

Prior phase results—48 tests passed and snapshot Q3 completed—remain valid development evidence but are not promoted to release evidence for the final `154c65c7` image.

## 5. Operational declaration

- Commit created in this phase: no.
- Push: no.
- Merge into `release/demo-staging`: no.
- Deployment: no.
- Migration: no.
- Production container/database/Redis mutation: no.
- Traffic expansion: no.

Final status: `PURE_IMAGE_PROVENANCE_NOT_READY`

Traffic decision: `HOLD_1_PERCENT`
