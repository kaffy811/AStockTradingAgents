# Pi Mono Adoption Decision

Phase: 6V-P0

## Decision

Adopt Scheme B: Python Pi-Compatible Runtime.

## Comparison

| Dimension | Scheme A: Node Pi Runtime Service | Scheme B: Python Pi-Compatible Runtime |
|---|---|---|
| Development complexity | Higher: service, gateway, auth, transport | Lower: native backend module |
| Deployment complexity | Higher: Node service, health checks, versioning | Lower: same FastAPI deployment |
| Latency | Extra hop Python to Node to Python | In-process async calls |
| DB/session lifecycle | Harder to prove session isolation | Runtime can avoid DB handle entirely |
| Tool safety | Requires Financial Tool Gateway | Uses `FinancialToolRegistry` directly through adapter |
| Tracing | Cross-service correlation required | Native trace/run/event IDs |
| Cancellation | Cross-process cancellation required | Native `asyncio` cancellation |
| Streaming | HTTP/gRPC bridge needed | Native SSE mapping available |
| Upgrade maintenance | Track pi-mono TS APIs | Stable internal protocol |
| License | MIT, but vendoring burden if copied | No source vendoring |
| Testing | Multi-process integration | Hermetic Python unit tests |
| Financial service reuse | Indirect via gateway | Direct through existing domain services |
| Failure isolation | Better process isolation | Lower operational blast radius for prototype |

## Why Not Scheme A Now

`pi-mono` is TypeScript, but Phase 6V-P1 needs only agent-loop semantics, not CLI/Web UI implementation. A new Node microservice would increase the trusted surface and require a Python financial tool gateway while still depending on the same Python services for official report data.

## Adopted Boundary

TradingAgents owns financial routing, context, data fabric, domain agents, drafting, compliance, and presentation. The Pi-Compatible module only owns execution mechanics.

## Rollout

Default remains disabled:

- `AGENT_EXECUTOR_MODE=legacy`
- `PI_AGENT_SHADOW_ENABLED=false`
- `PI_AGENT_ALLOWED_AGENTS=official_report_pdf_pi_v1`

Current decision: `do_not_enable_pi_compatible`.
