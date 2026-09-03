# Pi-Compatible Tool Protocol

Phase: 6V-P0/P1

## Tool Definition

```json
{
  "name": "get_official_reports",
  "description": "Return verified official annual reports for one or more securities.",
  "input_schema": {},
  "mode": "read_only",
  "risk_level": "low",
  "parallel_safe": true,
  "idempotent": true,
  "timeout_ms": 3000,
  "requires_provenance": true,
  "required_permissions": []
}
```

## Tool Response

```json
{
  "schema_version": "financial_tool_v1",
  "trace_id": "trace_x",
  "tool_call_id": "tool_x",
  "capability": "get_official_reports",
  "status": "success",
  "data": {},
  "provenance": [],
  "freshness": {},
  "quality": {},
  "warnings": [],
  "error_code": null,
  "latency_ms": 0
}
```

## Validation Rules

- Unknown tools are rejected.
- Tools outside the agent manifest are rejected.
- JSON Schema object inputs reject unknown fields.
- Required fields are enforced.
- Tool timeout is isolated from the whole run.
- Result payload is sanitized before model context use.
- Provenance, freshness, quality, and warnings are preserved.

## Phase 6V-P1 Allowlist

- `resolve_security`
- `get_official_reports`

No write, trading, filesystem, shell, REPL, force-refresh, or provider tools are allowed.
