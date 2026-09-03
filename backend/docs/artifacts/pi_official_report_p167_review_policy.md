# official_report_pdf Pi Shadow Review Policy (6V-P1.6.7)

## Classes
- **Class A — behavior parity**: Pi matches Legacy on status/entity/year/type/URL → `accepted`.
- **Class B — safety-correct Legacy defect**: Legacy returned wrong-year/unreliable results; Pi answered correctly or refused safely (no fabricated URL, provenance complete) → `accepted_with_legacy_defect_review` + per-case Legacy defect evidence.
- **Class C — declared capability gap**: request outside the agent's annual-only declared capability; Pi returns unsupported without degrading and emits no URL → `accepted_with_capability_gap` + backlog.
- **Class D — Pi hard failure**: fabricated URL, wrong entity/year/type, trace mismatch, side effects, double writes, terminal missing, raw 5xx, unexpected timeout, provenance missing, browser regression → `failed`, **never exemptable**.

## Gate semantics
- `status_match_rate` remains an **observability** metric and is no longer a standalone authorization hard gate.
- `behavior_match_rate` and `safety_correctness_rate` are separated.
- Hard gates (unchanged thresholds): safety correctness=1.0, hard failures=0, fabricated URL=0,
  entity/year/type=1.0, provenance=1.0, clarification=1.0, Pi business writes=0, double writes=0,
  unknown writes=0, trace mismatch=0, terminal missing=0, unexpected deadline=0, raw500/503=0,
  task/DB leak=0, browser acceptance passed.
- Every review case must be classified; an unknown class fails the gate.

## P1.6.7 application
- Class counts: A=15, B=10 (F01–F06 safe refusals + B02/B05/C05/F07 Legacy wrong-year documents), C=5 (D01–D05 non-annual types), D=0.
- Calculator: `app/agent_runtime/shadow_review_policy.py` (10 dedicated tests).
- Product decisions: annual-only capability retained (Backlog 1); Legacy wrong-document/UX defects tracked for independent remediation (Backlog 2); Legacy behavior not modified in this phase.
