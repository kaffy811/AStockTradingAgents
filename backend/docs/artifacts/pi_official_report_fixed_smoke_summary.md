# Official Report PDF Fixed Smoke Summary

Phase 6V-P1.6.3 executed the fixed three-case local_live Smoke through HTTP Chat API and SSE.

Result: planned=3, executed=3, accepted=3, smoke_passed=true. A01 and A02 returned verified official report PDF provenance with tool_calls=1 and llm_calls=0. A03 returned deterministic clarification_required with tool_calls=0 and llm_calls=0. Pi business side effects, extra context mutation, and double assistant writes were all 0.

Backend full passed: 3359 passed, 15 skipped. Frontend test/build passed. npm ci remains blocked by an out-of-sync lockfile entry and was not repaired in this commit.

Formal Pi path remains disabled. Recommended next step: retry Full30 in a later phase.
