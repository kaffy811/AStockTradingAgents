# Phase 6T-L Trace

Real acceptance was executed against the live database-backed repository.

## Database Connectivity

- DNS resolution: passed
- TCP connectivity: passed
- DB authentication: passed
- `SELECT 1`: passed
- RAG tables readable: passed

## 601686 Permanent RAG

- `report_id=1`
- `symbol=601686`
- `report_year=2024`
- `report_type=annual`
- `repository_backend=database`
- `persistent=true`
- `active_rag_document_id=71`
- `active_generation=1`
- `persisted_chunk_count=296`
- `rag_status=indexed`

## Job Create Trace

- `p50_ms=1723.65`
- `p95_ms=6923.74`
- SQL queries per sample: `16, 2, 2, 2, 2`
- provider calls: `0`
- RAG retrieval calls: `0`
- extractor calls: `0`

## Warm Trace

- `p50_ms=1443.31`
- `p95_ms=1462.91`
- cache hit: `true`
- provider calls: `0`
- RAG retrieval calls: `0`
- extractor calls: `0`
- speedup ratio: `1.07x`

## Singleflight

All 5 allowlist symbols passed the 3-request singleflight check:

- `compute_count=1`
- `leader_count=1`
- `reused_count=2`
- `all_results_equal=true`

## Cancel

- cancel success: `5/5`
- success cache pollution: `false`

## Acceptance Result

The live acceptance did not satisfy the Phase 6T-L performance gate:

- job create latency exceeded the gate
- warm path latency exceeded the target on p50
- warm speedup was not meaningful enough for rollout

The gate remains on hold.
