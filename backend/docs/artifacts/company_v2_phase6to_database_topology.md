# Phase 6T-O Database Topology

- Database host: `aws-1-ap-northeast-2.pooler.supabase.com`
- Database region: `ap-northeast-2`
- Endpoint type: transaction pooler on port `6543`
- Driver: `postgresql+asyncpg`
- Pool: `AsyncAdaptedQueuePool`
- Pool size: `5`
- Max overflow: `10`
- `statement_cache_size=0`
- `pool_pre_ping=false`

## Assessment

The host region and pooler region are aligned. The local execution environment is estimated to be in the United States, so the current path is likely cross-continent and not representative of same-region deployment latency.

The shell in this turn also failed repeated DNS resolution for the pooler hostname, so no same-region live acceptance was performed here.
