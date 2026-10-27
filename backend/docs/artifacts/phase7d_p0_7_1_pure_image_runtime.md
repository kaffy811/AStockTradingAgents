# Phase 7D-P0.7.1 Pure-Image Runtime Gate

## Decision

`HOLD_WITH_EVIDENCE`

## Candidate and images

- Candidate: `4434fc60feb652a7806d286f54c2175b979cbb4b`
- Git tree: `24a9961639dd7d8388fe8353a6e2e7eb8b955f03`
- Backend image: `sha256:2a7984bc6785285249e2d7343c8f86225a54c8eb7302583283419d63d52717b1`
- Frontend image: `sha256:02dbad039d46b4ae7e632190a83c9c10e0681a2620346bebe771f8c997650228`
- Both OCI revisions: full candidate SHA.
- Backend runtime and frontend inspection containers: `Mounts=[]`.

## Harness validation

- Harness SHA-256: `bd5611720a46551a3949410d486453d8376b470a41d669c78081b1e1d328d94d`
- Fixture SHA-256: `fde89fdd2e1272bed5a44013e043d55684d6e3321e1685b7e655bcc3b4ae714b`
- `python -m py_compile`: passed.
- `python -m json.tool`: passed.
- Harness and fixture remained in `/private/tmp` and were not written into the candidate commit.

An initial pre-request container produced `HARNESS_ERROR: ModuleNotFoundError: No module named 'app'` because `PYTHONPATH=/app` was absent. It executed zero queries and is recorded separately. A new complete session was then created with the harness environment corrected; this did not retry any application request.

## Complete session

- Session ID: `50fe39cc-2d9c-4df7-b4ed-1360e4e8b8ff`
- Started: `2026-09-08T04:24:20.599080+00:00`
- Completed: `2026-09-08T04:24:20.826726+00:00`
- Status: passed.

Each query ran once and was atomically persisted before the next query began.

| Query | Result | Key evidence |
|---|---|---|
| Q1 | PASS | profile non-empty; history AUTH_REQUIRED=false; all four modules fulfilled |
| Q2 | PASS | `600519.SH`; EOD wording present; numeric validation valid |
| Q3 | PASS | source/as_of/report period present; valid=true; unsupported=[] |
| Q4 | PASS | unavailable / NO_APPROVED_INDUSTRY_NEWS_SOURCE; LLM=0; unapproved providers=0 |

The harness used request-local controlled structured facts for Company/EOD validation; it did not call live market, news, Tushare, or LLM Providers. Recorded Tushare counts represent calls to the request-local fake gateway/client boundary, not live network calls.

No business code, candidate commit, assertion, Dockerfile, dependency, Token, Provider, RAG, validator, route, or frontend logic was modified in P0.7.1.

## Superseding fail-stop evidence

A fresh no-mount, network-disabled session passed py_compile and json.tool, then
stopped before Q1 with: ModuleNotFoundError: No module named 'pandas'.
This is HARNESS_ERROR. Q1-Q4 were NOT_EXECUTED and LLM/live Provider calls were
zero. Earlier runtime results do not count under the new-session requirement.
