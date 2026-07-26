# Phase 6T-N Create Trace

## Steady-state create

- p50: `1367.75 ms`
- p95: `2097.94 ms`
- max: `2386.90 ms`
- samples: `50`

## Cold connection create

- total: `12349.89 ms`
- SQL queries: `19`
- DB round trips: `20`
- provider calls: `0`
- RAG retrieval calls: `0`
- extractor calls: `0`

## Conclusion

The job admission path is lighter than before, but the steady-state median still exceeds the `300 ms` gate in the current remote DB environment.
