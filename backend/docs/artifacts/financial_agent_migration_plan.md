# Financial Agent Runtime Migration Plan

## Feature Flag

`CHAT_RUNTIME_MODE`:

- `legacy`: current production path, default.
- `shadow`: legacy answers users; layered runtime runs in the background with a new DB session and does not write messages.
- `layered_v1`: layered runtime handles first migrated scenarios; failures fall back to legacy in `chat_orchestrator`.

## Stage 1 Scope

Migrated first:

1. explicit company financial report analysis
2. multi-turn financial report comparison
3. official PDF lookup
4. company financial snapshot Q&A
5. simple quote query

Not migrated yet:

- technical analysis
- news sentiment
- research report generation
- watchlist writes
- broad comprehensive analysis

## Shadow Comparison

Shadow compares:

- route intent
- resolved entities
- plan steps
- tool capabilities
- answer status/error code

Shadow does not:

- double write messages
- call write tools
- expose output to users
- reuse the streaming request DB session

## Gate Criteria

Before switching default to `layered_v1`:

- no private daemon-loop RAG access on Chat request path
- no DB session across LLM call
- normal UI hides internal fields
- disclaimer appears once
- first five scenarios pass browser acceptance
- 20 concurrent Chat requests show no connection leak

## Rollback

Set `CHAT_RUNTIME_MODE=legacy`. No migration is required and legacy code remains intact.
