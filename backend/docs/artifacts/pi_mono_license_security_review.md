# Pi Mono License And Security Review

Phase: 6V-P0

## License

`pi-mono/LICENSE` declares MIT License.

Conclusion: MIT permits use, modification, copying, distribution, sublicensing, and private/commercial use when copyright and license notices are preserved. This phase does not copy source code from pi-mono into TradingAgents. It only implements compatible concepts in Python, so no vendored license notice is required for copied files.

## Security Review

High-risk pi-mono components are excluded:

- Coding tools: `bash`, `read`, `write`, `edit`, `grep`, `find`, `ls`.
- Browser JS REPL and artifact execution.
- Slack bot workspace automation.
- GPU pod SSH/vLLM management.
- OAuth credential storage and provider login flows.
- TUI/Web UI replacement.

Allowed concepts are protocol and execution-shape only:

- Tool allowlist.
- Schema validation.
- Bounded loop.
- Event lifecycle.
- Context transform.
- Cancellation/deadline.

## Current Project Constraints

- Financial data remains behind `FinancialToolRegistry`.
- Runtime does not receive `AsyncSession`.
- No business writes in shadow.
- No prompt or chain-of-thought persistence.
- No arbitrary network or code execution.
- No migration required in this phase.

## Decision

Security posture supports a clean-room Python Pi-Compatible runtime. Direct TypeScript runtime reuse is not justified for Phase 6V-P1 because it would require a new service boundary and tool gateway without improving financial data governance.
