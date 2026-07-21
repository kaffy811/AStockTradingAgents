# P1.10 Selected Coverage Policy

## Definition

**selected_unique_entity_instances** = number of unique `(ts_code, normalized_year)` pairs
in cases that satisfy ALL of:
1. eligibility = true (annual report request, not known-unavailable by policy)
2. bucket_selected = true (canary routing decision = pi_canary)
3. pi_started = true (correlation header sent, Pi shadow execution attempted)
4. terminal_complete = true (agent_completed event received, terminal_count=1)

**normalized_year** = `str(requested_year)` if explicit year was requested, else `"latest"`.

## Exclusions (must NOT count toward threshold)

| Category | Reason |
|---|---|
| Demo / known-unavailable | Policy-excluded: is_known_unavailable=True in CanaryRequest |
| Warm-up requests | No correlation header; not tracked in formal metrics |
| Rollout-not-selected | bucket_selected=False |
| Multi-turn setup turns | Setup turn has no correlation; only the followup turn counts |
| Non-eligible requests | Clarification, unsupported type, etc. |
| Direct Agent calls | Bypass Auth/SSE/eligibility stack |
| Fixture/simulation | Offline — no real HTTP/DB/Pi execution |

## Staging DB Constraint

The staging database contains `KIND_ANNUAL_FULL` annual reports for exactly **11 stocks**.
No additional stocks are available for eligible requests (stocks outside this set
would return `REPORT_NOT_FOUND` which is correct behavior, but they are not included
in the ENTITIES corpus to avoid contaminating the eligible pool with uniformly-unavailable
symbols).

This means:
- `unique_stocks_in_selected` = 11 (all eligible stocks exercised)
- `unique_entity_instances_in_selected` = unique (stock, year) pairs ≥ 20 (target)

The 11-stock vs 20-stock gap is a **staging corpus constraint**, not a canary policy gap.
Resolution: add more stocks' annual reports to staging DB before 5% promotion review.

## P1.10 Coverage Targets

| Metric | Target | Counting Rule |
|---|---|---|
| selected_unique_entity_instances | ≥ 20 | (ts_code, year) pairs, selected-only |
| unique_stocks | 11 (all) | stock symbols, selected-only |
| query_styles | ≥ 6 | S1–S6 |
| years_covered | latest + 2025 + 2024 + ≥1 historical | — |
| multi_turn_executions | ≥ 10 | S5_followup counted |

## P1.9 Retrospective

P1.9 reported "11 eligible + 9 demo = 20" entities using DEMO_UNAVAILABLE_ENTITIES.
This mixed selected and non-selected entity counts.

P1.10 adopts selected-only accounting. The P1.9 selected corpus had:
- unique_stocks = 11
- unique_entity_instances (stock, year) = ~25+ (W1+W2 combined year diversity)

P1.9 gate metrics (safety, timeout, fallback, zero-tolerance) remain valid and unchanged.
