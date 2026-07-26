# Phase 6T-M Job Trace

Real admission tracing after connection-pool reuse and direct INSERT optimization.

## Connection Cold Create

- elapsed: `2740.98ms`
- SQL queries: `15`
- report: `report_id=1`, `report_year=2024`

## Steady-State Create

- p50: `400.88ms`
- p95: `405.57ms`
- sample count: `4`
- SQL queries per steady sample: `1`

## Note

The steady-state path is much faster than the cold first request, but it still sits above the `300ms` gate.
