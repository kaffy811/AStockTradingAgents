# Pi-Compatible Event Protocol

Phase: 6V-P0/P1

## Event Envelope

```json
{
  "schema_version": "pi_financial_event_v1",
  "trace_id": "trace_x",
  "run_id": "run_x",
  "event_id": "event_x",
  "event_type": "run_start",
  "timestamp": "2026-07-18T00:00:00+00:00",
  "sequence": 0,
  "payload": {}
}
```

## Internal Event Types

- `run_start`
- `turn_start`
- `model_start`
- `model_text_delta`
- `tool_call_start`
- `tool_call_validation_failed`
- `tool_execution_start`
- `tool_execution_update`
- `tool_execution_end`
- `model_end`
- `turn_end`
- `compliance_start`
- `compliance_end`
- `run_end`
- `run_failed`
- `run_cancelled`

## UI Mapping

Internal events map to user-facing phases only:

- 问题分析
- 数据检索
- 综合处理
- 风险审核
- 回答生成

## Hidden From Normal UI

- Chain-of-thought.
- Prompt text.
- Internal agent IDs.
- Raw tool arguments.
- DB table names.
- Internal report/chunk IDs.
- Provider secrets.
- Shadow diagnostics.
