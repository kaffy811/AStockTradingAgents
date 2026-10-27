# Phase 6W-R3.3C — Pure Commit Release Image Provenance Gate

Generated: 2026-08-27 (America/New_York)  
Decision: `PURE_COMMIT_CANDIDATE_IMAGE_READY`  
Traffic: `HOLD_1_PERCENT`

## 1. Baseline and workspace protection

- HEAD: `b055da8495c54bb37625f0b0e0f94b4d4a627de2`
- Branch: `release/demo-staging`
- Git tree: `235e56a392bf3d8f7aa666593d7f7c09c5228cfc`
- `git diff --check`: PASS
- Staged files: none
- Existing tracked dirty files, preserved unchanged:
  - `backend/Dockerfile`
  - `backend/app/main.py`
  - `backend/app/services/report_embedding_provider.py`
  - `backend/pyproject.toml`
  - `backend/uv.lock`
- Existing untracked files were preserved. At the pre-build audit they comprised `HKNA/docs/suggestion/suggest2.md` through `suggest6.md`, `HKNA/update_report/update_96.md`, the previously generated `backend/docs/artifacts/company_agents_data_*` artifacts listed by `git status --short`, and `memory/project_phase6w_r14_staging_smoke.md`.
- No reset, checkout, clean, migration, commit, push, deployment, or traffic change was performed.

## 2. Isolated build context

- Temporary worktree: `/private/tmp/tradingagents-r33c.qT7SsC`
- Mode: detached HEAD
- Worktree HEAD: `b055da8495c54bb37625f0b0e0f94b4d4a627de2`
- Worktree tree: `235e56a392bf3d8f7aa666593d7f7c09c5228cfc`
- `git branch --show-current`: empty, confirming detached state
- `git status --short`: empty
- `git diff --check`: PASS
- Build context: `/private/tmp/tradingagents-r33c.qT7SsC/backend`

The worktree was created by Git from the exact commit. No files were copied from the main dirty workspace. It was removed with `git worktree remove` after evidence collection.

## 3. Candidate build

Sanitized command:

```bash
docker build \
  --label org.opencontainers.image.revision=b055da8495c54bb37625f0b0e0f94b4d4a627de2 \
  --label org.opencontainers.image.created=2026-08-27T23:52:37Z \
  --label org.opencontainers.image.source=TradingAgents \
  -t tradingagents-backend:rc-b055da8 .
```

- Tag: `tradingagents-backend:rc-b055da8`
- Image ID / local repo digest: `sha256:fb9b69812eec90fd280eaf36c2a2d557a129f4ff25afa62e67f9787f969fba29`
- Build manifest: `sha256:3ab16c8fa07bf4362f6523f3cb80b9ecb10be74b3f74b5d27c547736d6a2d462`
- Image config: `sha256:ecf56021441c4471919c8beab717abf9304cedea800d4e421524c3ce67e118cf`
- Image created: `2026-08-27T23:52:59.229679127Z`
- Size: `241,787,036` bytes
- OCI labels: revision, created, and source all exactly match the requested values.

## 4. Git-to-image content verification

All values below are SHA-256 content hashes. Each candidate value equals the clean worktree value.

| File | Git blob | Clean commit / candidate SHA-256 | Result |
|---|---|---|---|
| `app/agent/report_chat_copilot_agent.py` | `563d6b8958ed4befda347ffe8339444fe2c640ef` | `d36dc52268b87ef94f5b8e110f4f5fe63feff9740e6b9d932571f1b172771c95` | MATCH |
| `app/routers/report_chat.py` | `37d878b845bdc1567e501d921f010bd722f2403a` | `e851669e68dffb9277446a7b99b33a1903bc1f2e2148ff07d571c6f87212f572` | MATCH |
| `app/core/database.py` | `3fafb59398e719d08884d7e25862c5068e3ab9f7` | `f1e26047b3cf3b82b4bbc65d096e3dcb4e42a9a93870233b0ed8382be0a68f94` | MATCH |
| `app/models/report_analysis_trace.py` | `8f02b5350b0923a7fd429124de7371d0f5ad0bbc` | `ada655897082022c6438bcf689f25f72939dd8776126890378dfa1cccca90090` | MATCH |
| `app/services/report_analysis_trace_service.py` | `7caf7d51b79079eb5ecfb8c0de1f1026dce4bf2e` | `4bedae6e858098442e41d20dee43c5b7c57d1feac742f29c3cf569f788c7ad46` | MATCH |
| `alembic/versions/2026_08_26_0001-q5r6s7t8u9v0_report_analysis_traces.py` | `a5d9d92e88cdd5826e082923485de7a049cf2a86` | `c111de9d8a6fbf0782618a0102106cd2b19a26953069d2918fa8d76a36f17e77` | MATCH |

Dirty-sensitive files also match the clean commit, not the main workspace variants:

| File | Clean/candidate SHA-256 | Main dirty SHA-256 | Result |
|---|---|---|---|
| `app/main.py` | `57d25ff1af5d3ef232270547ab9f5dd817d7dc67dfc2607613f5e3a70bb4a0a9` | `b2d83bb84a95528640e56f166d69d9f49eba1245a8995bd852b9c3aa5253be7c` | CLEAN |
| `app/services/report_embedding_provider.py` | `2f2973b538311266a2868e8625b07a06a4612c11dd1e4ab11aabaaa77144c2d0` | `9638b7ec5abfa0a6d870110d40d92c0bcd086b5a767deb11ff907a9ad8a2ec5f` | CLEAN |
| `pyproject.toml` | `eea6e5a7e479d50e6377a34217a1bec623a0499e40e8673ccd626bda2c42c8fb` | `feb14c5e4bbe0516b3af771eb221b6582553481e97c4d4f681a2c239c94f2160` | CLEAN |
| `uv.lock` | `74f8a749593d70aec78ef721e6609590d684dc97ed0182d89f13bac7760d3de0` | `6af92400f792c0ec8487b303a6274ad63ab41b2ad8ec2853163c6011cac0988e` | CLEAN |

The Dockerfile is not copied into the runtime filesystem. Its clean worktree SHA-256 is `c848ee9e10e1f9f61d63b8bd2ef363617ba01c9ff5b312177ed647e6977873a7`; the main dirty variant is `40aff42aaf653798a5c9d69fd7b21cc05df1b7079dddfdfcec69ba67f18575e6`. Candidate build history contains zero matches for the dirty model-preload commands or model identifier. The candidate therefore excludes the uncommitted sentence-transformers dependency/model preload, embedding-provider edit, lockfile change, and startup pool warmup.

## 5. Offline import verification

The candidate was run with `--network none`, an ephemeral local SQLite URL, and a non-production placeholder secret solely to satisfy configuration validation. No external service was contacted.

Imported successfully:

- `app.models.report_analysis_trace`
- `app.services.report_analysis_trace_service`
- `app.agent.report_chat_copilot_agent`
- `app.routers.report_chat`

Result: `IMPORT_OK`.

An initial import without placeholder settings failed before module loading because `DATABASE_URL` and `SECRET_KEY` are required configuration fields. This was a configuration precondition, not an image or module defect.

## 6. Secret scan

Only counts and non-secret classification were recorded; no environment values or possible secret contents were printed.

- Docker history high-confidence secret matches: `0`
- Configured sensitive environment keys: `0`
- Application/alembic high-confidence secret-content file matches: `0`
- Sensitive-extension filename hits: `1`, identified as the public CA trust bundle `/app/.venv/lib/python3.12/site-packages/certifi/cacert.pem`; it is dependency trust material, not a private key or credential.
- `.dockerignore` excludes `.env` and `.env.*` from the build context.

Result: no secret found in the inspected history, configured environment, or application filesystem scope.

## 7. Current runtime versus candidate

| Item | Current running image | `b055da8` candidate image |
|---|---|---|
| Image digest | `sha256:48a50ce2435e379c46f0ed0afa1878a5f9c8e9f223dcb418bb4bbc1a944987db` | `sha256:fb9b69812eec90fd280eaf36c2a2d557a129f4ff25afa62e67f9787f969fba29` |
| Source SHA | Dirty / no OCI revision proof | OCI revision `b055da8495c54bb37625f0b0e0f94b4d4a627de2` |
| Trace durability | Three trace model/service/migration files absent | Present, hash-matched, imports pass |
| Warmup dirty code | Present in dirty runtime baseline | Absent; `main.py` matches commit |
| Dependency dirty code | Present in dirty runtime baseline | Absent; provider/project/lock hashes match commit |
| Release candidate | No | Candidate only; pending later real-environment validation |

Current production container identity before candidate work:

- Container: `c9567bfdfec4892823d7a5febd09d1cba2e4fac2ba6dd300082f74bfd0140bee`
- Created: `2026-08-23T01:34:13.297204344Z`
- Started: `2026-08-23T01:34:14.117434553Z`
- Image: `sha256:48a50ce2435e379c46f0ed0afa1878a5f9c8e9f223dcb418bb4bbc1a944987db`
- Bind mounts: none

The same identity, image, start timestamp, running state, and empty mount list were observed after the build and offline checks. No compose lifecycle command was used.

## 8. Gate decision

- Isolated worktree clean: PASS
- Candidate revision label equals exact source SHA: PASS
- Candidate source hashes match Git commit: PASS
- Dirty code excluded: PASS
- Trace durability imports: PASS
- Secret scan: PASS
- Current production container untouched: PASS

`PURE_COMMIT_CANDIDATE_IMAGE_READY`

Candidate image built does not mean deployed. This candidate has not been connected to production DB/Redis, served HTTP, received traffic, or passed a later real-environment release validation. It is not authorization to expand traffic.

Final traffic decision: `HOLD_1_PERCENT`.
