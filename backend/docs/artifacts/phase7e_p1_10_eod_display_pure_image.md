# Phase 7E-P1.10 EOD Display Candidate Pure-Image Gate

## Conclusion

`EOD_DISPLAY_PURE_IMAGE_READY`

Candidate `dbf2073eb06a4206dea604a7156acae461c6bb35` (tree `e4eaacd0377422df0c1a22dd0b0e358f8555cd95`) was checked out in a clean detached worktree. No live Provider, push, merge, deployment, migration, service restart, or existing Docker-resource cleanup occurred.

## Image identity

| Image | ID / digest | Platform | OCI revision | Mounts |
|---|---|---|---|---|
| backend | `sha256:265d76aa96bcae741de7af4f9797d56069d13629259558f4de1a6cf0c68d9961` | `linux/amd64` | candidate full SHA | `[]` |
| frontend | `sha256:179b56bdee4c0d19e0f58d4abd668a6c9a83ec8a717e588d419401fee5f638c8` | `linux/amd64` | candidate full SHA | `[]` |

Image `Config.Env`, labels, and full history were scanned. No business Token, Authorization value, Tushare credential, or complete database connection string was found. Base-image metadata such as Python's public `GPG_KEY` is not an application credential.

## Source identity

| Candidate file / image file | Git SHA-256 | Image SHA-256 | Result |
|---|---|---|---|
| `backend/app/agents/chat_orchestrator.py` | `1abea51b...15a09` | `1abea51b...15a09` | PASS |
| `backend/app/services/stock_eod_display.py` | `8891035a...1f929` | `8891035a...1f929` | PASS |
| `frontend/nginx.conf` / `/etc/nginx/conf.d/default.conf` | `c4948147...0295f` | `c4948147...0295f` | PASS |

## Controlled-fixture runtime

The runtime container had `Mounts=[]`. The harness and committed sanitized fixtures were copied into the transient container after creation; application source was read from the unchanged image and its hashes were checked independently.

| Query | Result | Evidence | Calls |
|---|---|---|---|
| `CN/000725 公司资料 + EOD` | `fulfilled`, `000725.SZ` | 5/5 checked; valid; unsupported `[]` | fixture 1; LLM/live/unapproved 0 |
| `贵州茅台近期情况` | `fulfilled`, `600519.SH` | 18/18 checked; valid; unsupported `[]` | fixture 1; LLM/live/unapproved 0 |
| `600519 财务指标、ROE、估值` | `fulfilled`, `600519.SH` | 18/18 checked; valid; unsupported `[]` | fixture 1; LLM/live/unapproved 0 |

Representative projections include `4168500.462 CNY_thousand -> 41.69 亿元`, `161370533.5808 CNY_10k -> 16,137.05 亿元`, `32226.11 lot -> 3.22 万手`, `19.8161 multiple -> 19.82 倍`, and `1290.88 CNY -> 1,290.88 元`. Canonical values remain in evidence metadata; machine units and unformatted canonical representations are not rendered into the answer. All output states that the data is EOD/non-real-time.

The conversion policy is deterministic backend code using `Decimal` with `ROUND_HALF_UP` at two decimal places. `lot` remains a hand-based unit and is never converted to shares.

## Static gates

- Python compile: PASS.
- JSON validation: PASS.
- `git diff --check`: PASS.
- Candidate diff and image metadata/history secret scan: PASS.
- Targeted display/numeric tests: 30 passed.

The first host test command omitted the required non-secret fixture settings and failed at application import with eight `Settings` validation errors for missing `database_url` and `secret_key`; no business assertion ran. With an in-memory SQLite placeholder and a non-secret fixture key, the same tests passed 30/30. The image runtime likewise used only those test placeholders and made no network/provider call.

## Scope and state

The gate did not modify Provider acquisition, numeric-validator strictness, routing, Dockerfiles, dependencies, Token handling, database, cache, or news capability. Candidate worktree remained detached and clean. No push, merge, or deployment was performed. These three files are uncommitted gate artifacts outside the candidate worktree.
