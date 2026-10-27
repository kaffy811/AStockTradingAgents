# Phase 7D-P0.9.2 Isolated Local Fast-forward Attribution

## Decision

`HOLD_WITH_EVIDENCE`

No merge was executed. The mandatory fast-forward ancestry precondition failed before the authorized `git merge --ff-only` command.

## First failed gate

- Gate: `RELEASE_IS_ANCESTOR_OF_CANDIDATE`
- Command:

```text
git -C /private/tmp/phase7d_p0_9_2_isolated merge-base --is-ancestor release/demo-staging 4434fc60feb652a7806d286f54c2175b979cbb4b
```

- Exit code: `1`
- stdout: empty
- stderr: empty

Git documents exit code 1 from `merge-base --is-ancestor` as a false ancestry result. Because this validation failed, the authorized command below was not executed:

```text
git merge --ff-only 4434fc60feb652a7806d286f54c2175b979cbb4b
```

## Root cause

Local `release/demo-staging` no longer points to the release baseline. P0.9 already created the following two-parent local merge commit:

```text
release/demo-staging HEAD = 98c111b684cb19de0e0e92cb46e1d675ef3e8d0a
parents = c4a506c0c2fdcf985d779f005788f4059066605a 4434fc60feb652a7806d286f54c2175b979cbb4b
```

Therefore the candidate is an ancestor of the local release branch, not the reverse:

```text
is-ancestor release/demo-staging -> 4434fc60: exit 1
is-ancestor 4434fc60 -> release/demo-staging: exit 0
```

A fast-forward can only move a ref to a descendant. It cannot move `98c111b...` backward to its parent `4434fc60...`.

## Identities and content comparison

| Object | Commit | Tree |
|---|---|---|
| Isolated worktree start | `98c111b684cb19de0e0e92cb46e1d675ef3e8d0a` | `24a9961639dd7d8388fe8353a6e2e7eb8b955f03` |
| Local `release/demo-staging` | `98c111b684cb19de0e0e92cb46e1d675ef3e8d0a` | `24a9961639dd7d8388fe8353a6e2e7eb8b955f03` |
| Candidate | `4434fc60feb652a7806d286f54c2175b979cbb4b` | `24a9961639dd7d8388fe8353a6e2e7eb8b955f03` |

`git diff --quiet 4434fc60... release/demo-staging` exited 0. The current local release commit and candidate have no file differences and have identical trees. The failure is exclusively ref ancestry/history shape, not content drift.

## Isolation evidence

- New detached worktree: `/private/tmp/phase7d_p0_9_2_isolated`
- Worktree start: local `release/demo-staging` at `98c111b...`
- Worktree status: clean
- Main-worktree state before adding P0.9.2 artifacts:
  - `tracked_unstaged_or_mixed=6`
  - `untracked=112`
  - `staged=0`
- No main-worktree tracked or untracked file was copied into the isolated worktree or integration history.
- The three P0.9.2 records add three untracked files, so the expected main-worktree untracked count after artifact generation is 115; the original 112 remain preserved.

## Scope and operations

Because no integration command ran, the previously reviewed candidate content and P0.8 scope remain unchanged. No business code, candidate tree, branch pointer, index entry, tracked dirty file or existing untracked file was changed in this phase.

Not performed:

- push or remote-server connection;
- merge, ordinary merge, rebase or cherry-pick;
- reset, checkout, stash or clean;
- deployment, Docker build, migration or traffic expansion;
- live LLM or market/news Provider call.

## Required Owner decision

The requested exact fast-forward is impossible from the current local branch state. The smallest next action requires new authorization for one of these choices:

1. Accept existing local merge commit `98c111b...` for deploy review because its tree is already exactly the approved candidate tree and `4434fc60...` is its parent; or
2. Explicitly authorize moving/recreating the local branch pointer from a clean isolated worktree. That is not a fast-forward and was prohibited in P0.9.2.

Until Owner selects one, do not push or deploy.
