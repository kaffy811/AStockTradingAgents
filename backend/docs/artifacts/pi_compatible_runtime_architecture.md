# Pi-Compatible Runtime Architecture

Phase: 6V-P0/P1

## Runtime Placement

New module:

`backend/app/agent_runtime/`

It is separate from legacy `chat_orchestrator` and existing `agents/financial_runtime`. The first integration is shadow only and is invoked after L0/L1 have already produced intent, context, and plan.

## Flow

1. Legacy chat path continues normally.
2. If `AGENT_EXECUTOR_MODE=pi_compatible_shadow` and `PI_AGENT_SHADOW_ENABLED=true`, start a read-only shadow run.
3. L0 router and L1 context/planner stay in `agents/financial_runtime`.
4. Pi-Compatible executor receives a structured request and `FinancialSessionContext`.
5. `PiFinancialToolAdapter` maps allowed capabilities to `FinancialToolRegistry`.
6. `OfficialReportPdfAgent` uses deterministic path when entity/year/tool evidence is sufficient.
7. Runtime emits internal events and returns a `PiAgentRunResult`.
8. Shadow comparison is in-memory/log-only and must not write assistant messages or business state.

## Runtime Does Not Own

- Auth.
- DB session.
- Entity resolver internals.
- Domain service implementation.
- Provider credentials.
- Prompt sets P1-P4.
- Compliance policy.
- Frontend UI rendering.

## Safety Defaults

- Read-only.
- Agent allowlist.
- Tool allowlist.
- Deadline.
- Max turns.
- Max tool calls.
- Bounded parallelism.
- Payload truncation.
- No LLM compaction this phase.

## First Agent

`official_report_pdf_pi_v1` only.

Allowed tools:

- `resolve_security`
- `get_official_reports`

The agent must not generate or infer PDF URLs. The selected URL must come from verified official report data and provenance.
