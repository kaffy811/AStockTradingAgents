# Pi-Compatible Agent Contracts

Phase: 6V-P0/P1

## Run Request

```json
{
  "schema_version": "pi_financial_runtime_v1",
  "trace_id": "trace_x",
  "run_id": "run_x",
  "conversation_id": "conversation_x",
  "user_id": "user_x",
  "intent": "official_report_pdf",
  "entities": [],
  "context": {},
  "execution_plan": {},
  "allowed_tools": [],
  "model_profile": "tool_routing_light",
  "budgets": {
    "deadline_ms": 5000,
    "max_turns": 3,
    "max_tool_calls": 4,
    "max_parallel_tools": 2,
    "max_output_tokens": 1000
  },
  "runtime_mode": "shadow",
  "read_only": true
}
```

## Run Result

```json
{
  "schema_version": "pi_financial_runtime_v1",
  "trace_id": "trace_x",
  "run_id": "run_x",
  "status": "success",
  "agent_id": "official_report_pdf_pi_v1",
  "turn_count": 0,
  "tool_call_count": 0,
  "events": [],
  "findings": [],
  "evidence_ids": [],
  "structured_answer": {},
  "error": null,
  "metrics": {
    "latency_ms": 0,
    "model_calls": 0,
    "tool_calls": 0,
    "input_tokens": 0,
    "output_tokens": 0
  }
}
```

## Capability Manifest

`official_report_pdf_pi_v1`:

- Purpose: return a verified official report PDF.
- Supported intent: `official_report_pdf`.
- Supported market: `CN`.
- Execution mode: `pi_compatible`.
- Model profile: `tool_routing_light`.
- Allowed tools: `resolve_security`, `get_official_reports`.
- Max turns: 3.
- Max tool calls: 4.
- Deadline: 5000 ms.
- Read only: true.
- Output schema: `OfficialReportPdfAnswerV1`.
- Fallback: `legacy_official_report_pdf`.

## Error Codes

- `AGENT_DEADLINE_EXCEEDED`
- `AGENT_CANCELLED`
- `AGENT_MAX_TURNS_EXCEEDED`
- `AGENT_MAX_TOOL_CALLS_EXCEEDED`
- `AGENT_TOOL_NOT_ALLOWED`
- `AGENT_TOOL_ARGUMENT_INVALID`
- `AGENT_TOOL_TIMEOUT`
- `AGENT_MODEL_UNAVAILABLE`
- `AGENT_OUTPUT_SCHEMA_INVALID`
- `AGENT_CONTEXT_TOO_LARGE`
- `AGENT_INTERNAL_ERROR`
