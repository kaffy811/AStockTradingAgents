# Phase 6W-R3.4.1A — Local Release Branch Fast-Forward Evidence

## Final status

```text
RELEASE_BRANCH_FAST_FORWARDED_LOCAL_ONLY
Traffic: HOLD_1_PERCENT
```

## Merge identity

| Item | Result |
|---|---|
| Branch | `release/demo-staging` |
| Pre-merge HEAD | `b055da8495c54bb37625f0b0e0f94b4d4a627de2` |
| Authorized candidate | `e8985471d62ce74e5cd99b61b9eadf27a13878ce` |
| Post-merge HEAD | `e8985471d62ce74e5cd99b61b9eadf27a13878ce` |
| Merge mode | `git merge --ff-only` |
| Merge commit created | false |
| Staging area after merge | empty |
| `git diff --check` | pass |

The candidate was verified as a descendant of the baseline before the merge. All ten candidate commits are present between the former baseline and the new local release HEAD.

## Preserved local pre-merge evidence

Six untracked local files collided with paths tracked by the candidate. Before moving them, each file was copied to a timestamped directory and the copy hash was verified. The verified copy was then retained under `verified-copy/`, and the original was moved—never deleted or overwritten—to the backup root using its original relative path.

```text
backup directory: /private/tmp/tradingagents-r341-untracked-evidence-20260901T034641Z-LU3qb7
manifest: /private/tmp/tradingagents-r341-untracked-evidence-20260901T034641Z-LU3qb7/manifest.json
copy hash verification: passed
post-move hash verification: passed
```

| Preserved relative path | Local SHA-256 | Candidate blob SHA-256 | Match | Local→candidate numstat |
|---|---|---|---:|---|
| `HKNA/update_report/update_101.md` | `2019cea844c722ca0cd4e31b3d1d61f5574290da330439176267bc9298ba56e6` | `2019cea844c722ca0cd4e31b3d1d61f5574290da330439176267bc9298ba56e6` | true | 0/0 |
| `HKNA/update_report/update_103.md` | `265cbd9aeed770d29db75e1f9600bcd987e605efdec4609491f6d1b16932d321` | `5c20ad7ac3d7bfc98387acb494c12c25ecba69e3c4fdb58a67bfc3f56ef2b51f` | false | 0 insertions / 1 deletion |
| `backend/docs/artifacts/company_agents_data_r3_3i2_3_citation_claim_boundary.md` | `a296ad9d6c34525a1b2d7336e160c37e17cf922b3fc7451071deddda34f8e2e2` | `a296ad9d6c34525a1b2d7336e160c37e17cf922b3fc7451071deddda34f8e2e2` | true | 0/0 |
| `backend/docs/artifacts/company_agents_data_r3_3i2_3_citation_claim_boundary.json` | `29a338d8bd1e9c5e60407569c012a77284eb6d117fff4334f043662622b56194` | `29a338d8bd1e9c5e60407569c012a77284eb6d117fff4334f043662622b56194` | true | 0/0 |
| `backend/docs/artifacts/company_agents_data_r3_3i2_5_formula_constant_boundary.md` | `6540bd6e3dc39ad1ef616cb1bebdb23f4fe5ceb76445dede9f1e4246145add4e` | `4f0ad3e710a33d453e51785c5baa040a1c37e3d3c29d12a22331a493aa62c766` | false | 0 insertions / 8 deletions |
| `backend/docs/artifacts/company_agents_data_r3_3i2_5_formula_constant_boundary.json` | `5b7ae8a04040244579f09e0be829d627a006bbbd582343b2c5d9195a5e6c8d21` | `62eaa5afaf99e418e133dc6b5a1c16824ad74eeebc2e5eda23181337fd0b5cc1` | false | 0 insertions / 8 deletions |

After the move, the collision paths were absent from the pre-merge worktree. The fast-forward then populated those paths with the candidate-tracked versions. The preserved local versions remain recoverable from the backup directory.

## Candidate-delivered files

The fast-forward delivered the audited 52-file candidate diff: migration bootstrap and vector compatibility, trace input migration, report Agent provenance and derived-fact services, provider error normalization and trace propagation, direct tests, the serial diagnostic harness, phase artifacts, and update reports. It did not deliver any of the five historical dirty paths below.

## Untouched historical tracked dirty files

The following hashes were identical before collision handling, immediately before merge, and after merge:

| Path | SHA-256 |
|---|---|
| `backend/Dockerfile` | `40aff42aaf653798a5c9d69fd7b21cc05df1b7079dddfdfcec69ba67f18575e6` |
| `backend/app/main.py` | `b2d83bb84a95528640e56f166d69d9f49eba1245a8995bd852b9c3aa5253be7c` |
| `backend/app/services/report_embedding_provider.py` | `9638b7ec5abfa0a6d870110d40d92c0bcd086b5a767deb11ff907a9ad8a2ec5f` |
| `backend/pyproject.toml` | `feb14c5e4bbe0516b3af771eb221b6582553481e97c4d4f681a2c239c94f2160` |
| `backend/uv.lock` | `6af92400f792c0ec8487b303a6274ad63ab41b2ad8ec2853163c6011cac0988e` |

## Action boundary

```text
push=false
deploy=false
production migration=false
image rebuild=false
production restart=false
traffic expansion=false
```

The local release branch is fast-forwarded only. A separate Owner authorization is required for any staging or production deployment. Traffic remains `HOLD_1_PERCENT`.
