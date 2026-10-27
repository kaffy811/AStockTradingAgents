# Phase 7D-P0.7 Theme Fail-Closed Review

## Decision

`HOLD_WITH_EVIDENCE`

## Candidate

- Baseline: `1c675f7fe6b018f3a280973698d9ada10f5c3ddd`
- A commit: `4434fc60feb652a7806d286f54c2175b979cbb4b`
- A tree: `24a9961639dd7d8388fe8353a6e2e7eb8b955f03`
- Commit message: `fix(research-copilot): fail closed unapproved theme queries`

## Implemented scope

- Added a bounded industry/theme pattern covering the exact input `AI 半导体设备主题问题` and 11 additional variants.
- Kept `贵州茅台近期情况` and `600519 财务指标、ROE、估值` on `stock_eod_research`.
- Fail-closed metadata now always includes `fulfillment`, `reason_code`, `scope`, `sources`, `as_of`, `limitations`, and `requires_symbol`.
- No Docker, dependency, Token, Provider, RAG, global numeric validator, timeout, or cache TTL change.

## Tests

- Theme/Company/EOD backend combination: `68 passed, 1 warning`.
- Full frontend gate: `69 files, 764 tests passed`; worker timeout count: 0.
- Python compile and `git diff --check`: passed.
- Frontend unavailable state: `当前缺少所需数据`, `completed=false`.

## Pure-image gate

Backend and frontend images built successfully from A commit. OCI revision was set to the full A SHA.

The serial Q1–Q4 sequence did not complete: Q1 passed; Q2 harness contained a Python dictionary syntax error. Under the explicit no-retry rule, Q2 was not rerun and Q3/Q4 were not executed in that sequence. Therefore A cannot be marked ready even though the exact Q4 and 12 theme variants pass hermetic route tests with downstream resolver/EOD calls asserted at zero.

Failure text:

```text
SyntaxError: ':' expected after dictionary key
```

No live LLM or live market/news Provider was invoked by the successful A tests. The failed Q2 command did not reach application imports or Provider code.
