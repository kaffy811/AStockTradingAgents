# Phase 7D-P0.7.2 Harness Independence

## Final decision

`RUNTIME_GATE_READY`

## Candidate identity

- Commit: `4434fc60feb652a7806d286f54c2175b979cbb4b`
- Tree: `24a9961639dd7d8388fe8353a6e2e7eb8b955f03`
- Backend image: `sha256:2a7984bc6785285249e2d7343c8f86225a54c8eb7302583283419d63d52717b1`
- Frontend image: `sha256:02dbad039d46b4ae7e632190a83c9c10e0681a2620346bebe771f8c997650228`
- Both OCI revisions: `4434fc60feb652a7806d286f54c2175b979cbb4b`
- Backend runtime container and frontend inspection container: `Mounts=[]`, network disabled.

The dirty primary worktree was not used as runtime input. The fixed candidate images were used directly.

## Import-chain attribution

The P0.7.1 harness contained a top-level `import pandas as pd`. Running it with the image's system Python produced:

```text
Traceback (most recent call last):
  File "/tmp/phase7d_p0_7_1_harness.py", line 12, in <module>
    import pandas as pd
ModuleNotFoundError: No module named 'pandas'
```

After removing that harness import, the same incorrect system-Python invocation failed earlier in the application import chain:

```text
Traceback (most recent call last):
  File "/tmp/phase7d_p0_7_2_harness.py", line 12, in <module>
    from app.agents import chat_orchestrator as orchestrator
  File "/app/app/agents/chat_orchestrator.py", line 18, in <module>
    from sqlalchemy.ext.asyncio import AsyncSession
ModuleNotFoundError: No module named 'sqlalchemy'
```

This proved the failure was caused by bypassing the image's declared `uv run` environment, not by a missing production package. Under `uv run python`, both pandas and SQLAlchemy imported from `/app/.venv`; application import then reached the expected mandatory settings validation.

The P0.7.2 harness has no pandas import. Its request-local fake tabular results use a minimal `StdlibTable` implemented only with `dict`, `list`, sorting and indexing. It patches only the gateway's request-local table type check during Q1. No package was installed and no candidate, Dockerfile, dependency file, Provider, RAG, validator, cache or timeout was changed.

## Harness validation

- Harness: `/private/tmp/phase7d_p0_7_2_harness.py`
- Harness SHA-256: `136b2e206300b506210370740e447ea4992ae190cb4f9d2831f94815dcdaf5bf`
- `python -m py_compile`: PASS
- Fixture: `/private/tmp/phase7d_p0_7_2_fixture.json`
- Fixture SHA-256: `3516ac46dd8f0b82232ad38b2a76a5ece708a861a97c3db7325a600c360dce36`
- `python -m json.tool`: PASS
- Atomic session JSON SHA-256: `ad2b19d0ff4e5c889b267de9d2034e2097411cfd5f1e05b3839ff4695d592fdc`
- Q1, Q2, Q3, Q4 and session JSON records: JSON validation PASS.

## New isolated session

- Session ID: `72ba95bf-03b4-479a-93e0-3f7f998be7f1`
- Started: `2026-09-09T00:56:46.863734+00:00`
- Completed: `2026-09-09T00:56:47.099069+00:00`
- Execution: Q1 → Q2 → Q3 → Q4, one invocation each.
- Every Q record was atomically written, fsynced, renamed and JSON-read before the next query.

| Order | Query | Result | LLM | Tushare boundary | AKShare / Eastmoney / Sina / Tencent | Live calls |
|---:|---|---|---:|---:|---:|---:|
| 1 | CN/000725 公司资料 + EOD | fulfilled; profile non-empty; no AUTH_REQUIRED; all modules fulfilled | 0 | 4 | 0 / 0 / 0 / 0 | 0 |
| 2 | 贵州茅台近期情况 | fulfilled; 600519.SH; EOD/non-realtime wording; numeric valid | 0 | 1 | 0 / 0 / 0 / 0 | 0 |
| 3 | 600519 财务指标、ROE、估值 | fulfilled; source/as-of/report period present; valid=true; unsupported=[] | 0 | 1 | 0 / 0 / 0 / 0 | 0 |
| 4 | AI 半导体设备主题问题 | unavailable / NO_APPROVED_INDUSTRY_NEWS_SOURCE; scope=unapproved_industry_theme_research | 0 | 0 | 0 / 0 / 0 / 0 | 0 |

All data-bearing results were request-local controlled fixture results. The Tushare counts above count calls to fake gateway/client boundaries only; they are not network or live-provider calls and must not be represented as current market validation. Existing P0.2 Tushare runtime evidence remains separate and was not rerun or reused here.

## Git state

No business commit was created. The candidate SHA/tree and images were unchanged. The primary worktree remains dirty with pre-existing tracked modifications and many untracked artifacts; none was mounted into or copied into the runtime container. Only the requested documentation files were added or clarified, and the harness/fixture remain under `/private/tmp`.
