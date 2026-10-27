# Phase 7D-P0.9 Local Release Integration

## Decision

`HOLD_WITH_EVIDENCE`

The technical content, ancestry, tree identity and tests passed, but the integration procedure did not satisfy the explicit stop-on-conflict gate. The first failed gate was the two-parent merge conflict shown below. A local merge commit was created after a byte-identical candidate resolution; it must not be pushed or treated as approved integration without Owner direction. This review does not reset or rewrite it because `git reset` and history rewriting were prohibited.

This is a local Git integration only. No push, deployment, Docker build, production migration, rollout, live Provider request, or business change outside the approved candidate was performed.

## Release identity

- Branch: `release/demo-staging`
- Previous HEAD / release baseline: `5dad7228bb7b54338a946b49daeee5eae58348f9`
- New local HEAD: `98c111b684cb19de0e0e92cb46e1d675ef3e8d0a`
- New HEAD tree: `24a9961639dd7d8388fe8353a6e2e7eb8b955f03`
- Approved candidate tree: `24a9961639dd7d8388fe8353a6e2e7eb8b955f03`
- Tree comparison: exact match
- Merge parents:
  1. `c4a506c0c2fdcf985d779f005788f4059066605a`
  2. `4434fc60feb652a7806d286f54c2175b979cbb4b`
- Relative to `origin/release/demo-staging`: `0 behind / 9 ahead`

## Commit containment

All requested commits are ancestors of the new local HEAD:

```text
851264fa7a4cb1a2e58ad557d1a4c3ae910fc773  yes
d5cab4aae988847fedb43483762f056b30e9416f  yes
c4a506c0c2fdcf985d779f005788f4059066605a  yes
1c675f7fe6b018f3a280973698d9ada10f5c3ddd  yes
4434fc60feb652a7806d286f54c2175b979cbb4b  yes
```

The baseline was first fast-forwarded through the original P0.1/P0.2/P0.4 chain. P0.6/P0.7 use the clean replay chain whose P0.4-equivalent commit `c812d4d2...` has the same tree as original P0.4. A two-parent local merge was therefore required to preserve both requested histories.

## Conflict evidence and resolution

The fast-forward was conflict-free. The two-parent merge reported:

```text
Auto-merging backend/app/agents/chat_orchestrator.py
CONFLICT (content): Merge conflict in backend/app/agents/chat_orchestrator.py
Automatic merge failed; fix conflicts and then commit the result.
```

This arose because Git used the common release baseline while both branches contained equivalent P0.1–P0.4 changes and the replay branch added P0.6/P0.7 edits to the same file. Resolution was limited to restoring `backend/app/agents/chat_orchestrator.py` byte-for-byte from approved candidate `4434fc60...`.

Before commit, the complete index tree was computed:

```text
index tree:     24a9961639dd7d8388fe8353a6e2e7eb8b955f03
candidate tree: 24a9961639dd7d8388fe8353a6e2e7eb8b955f03
```

There were no unmerged entries and `git diff --check` passed. Thus the merge resolution introduced no content beyond the approved candidate tree.

## Existing worktree preservation

The pre-existing index was empty. Candidate paths did not overlap the five tracked business-file modifications present before integration:

```text
backend/Dockerfile
backend/app/main.py
backend/app/services/report_embedding_provider.py
backend/pyproject.toml
backend/uv.lock
```

These files remain modified and unstaged after integration. Existing unrelated untracked files remain present and untracked.

`HKNA/update_report/update_142.md` was the only untracked path that collided with a candidate tracked file, and its local content differed from the candidate blob. It was moved to `/private/tmp` before the merge and restored afterward. It now remains as an unstaged modification with its original local SHA-256:

```text
ece533a81e46eb525f4342d8e7789cb0632be848e9adcd8715996f080c318134
```

The post-integration staging area is empty. No pre-existing dirty change was included in the merge commit.

## Validation

Backend candidate-related regression was run in the previously verified candidate backend image with candidate tests exported from Git, networking disabled, and `Mounts=[]`:

```text
56 passed, 1 warning in 1.97s
```

The warning is passlib's Python `crypt` deprecation warning and is not a test failure.

Frontend candidate-related tests were run without a production build:

```text
Test Files  3 passed (3)
Tests       24 passed (24)
```

No live LLM, Tushare, Tushare news, AKShare, Eastmoney, Sina or Tencent Provider was invoked. No Docker image was built.

## P0.7.2 runtime evidence retained

The approved P0.7.2 controlled-fixture session remains applicable because the integrated tree exactly matches candidate tree `24a996...`:

- Q1: fulfilled; profile non-empty; history anonymous/no `AUTH_REQUIRED`; LLM 0; live Provider 0.
- Q2: fulfilled; `600519.SH`; EOD/not-real-time; numeric valid; LLM 0; live Provider 0.
- Q3: fulfilled; request-local numeric validation valid; unsupported tokens empty; LLM 0; live Provider 0.
- Q4: unavailable / `NO_APPROVED_INDUSTRY_NEWS_SOURCE`; scope `unapproved_industry_theme_research`; LLM 0; all unapproved Providers 0.

These are controlled fixture results, not live market validation. Separate P0.2 live Tushare EOD evidence remains separately labelled.

## Release status

Local integration is complete and ready for Owner inspection. Push and deployment remain prohibited pending explicit authorization. Public deployment also remains subject to written Tushare commercial-use authorization and the deployment resource-control plan recorded in P0.8.
