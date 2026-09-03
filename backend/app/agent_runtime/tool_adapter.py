"""Adapter from FinancialToolRegistry to Pi-compatible tool definitions."""
from __future__ import annotations

import asyncio
import time
from dataclasses import asdict
from typing import Any

from app.agent_runtime.contracts import (
    PiToolCall,
    PiToolDefinition,
    PiToolResponse,
    STATUS_FAILED,
    STATUS_SUCCESS,
)
from app.agent_runtime.errors import (
    AGENT_TOOL_ARGUMENT_INVALID,
    AGENT_TOOL_NOT_ALLOWED,
    AGENT_TOOL_TIMEOUT,
    PI_SHADOW_WRITE_FORBIDDEN,
)
from app.core.config import settings
from app.agents.financial_runtime.contracts import FinancialSessionContext, ToolResponse as FinancialToolResponse
from app.agents.financial_runtime.tool_runtime import financial_tool_registry


class ToolSchemaError(ValueError):
    pass


def _validate_type(value: Any, expected: str) -> bool:
    if expected == "object":
        return isinstance(value, dict)
    if expected == "array":
        return isinstance(value, list)
    if expected == "string":
        return isinstance(value, str)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return isinstance(value, int | float) and not isinstance(value, bool)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "null":
        return value is None
    return True


def validate_json_schema(payload: dict[str, Any], schema: dict[str, Any]) -> None:
    """Validate the object subset used by Phase 6V-P1 tool schemas."""

    if schema.get("type") != "object":
        raise ToolSchemaError("tool schema root must be object")
    if not isinstance(payload, dict):
        raise ToolSchemaError("tool arguments must be object")

    properties = schema.get("properties") or {}
    required = set(schema.get("required") or [])
    additional = bool(schema.get("additionalProperties", True))

    for key in required:
        if key not in payload:
            raise ToolSchemaError(f"missing required field: {key}")
    if not additional:
        unknown = sorted(set(payload) - set(properties))
        if unknown:
            raise ToolSchemaError(f"unknown field(s): {', '.join(unknown)}")

    for key, value in payload.items():
        prop_schema = properties.get(key)
        if not prop_schema:
            continue
        expected = prop_schema.get("type")
        if isinstance(expected, list):
            if not any(_validate_type(value, item) for item in expected):
                raise ToolSchemaError(f"invalid type for {key}")
        elif isinstance(expected, str) and not _validate_type(value, expected):
            raise ToolSchemaError(f"invalid type for {key}")


def _entity_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": True,
        "properties": {
            "market": {"type": "string"},
            "symbol": {"type": "string"},
            "ts_code": {"type": "string"},
            "short_name": {"type": "string"},
        },
    }


class PiFinancialToolAdapter:
    def __init__(self, registry: Any = None) -> None:
        self.registry = registry or financial_tool_registry
        self._definitions: dict[str, PiToolDefinition] = {
            "resolve_security": PiToolDefinition(
                name="resolve_security",
                description="Resolve a security entity from a user query.",
                input_schema={
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["query"],
                    "properties": {"query": {"type": "string"}},
                },
                timeout_ms=1500,
            ),
            "get_official_reports": PiToolDefinition(
                name="get_official_reports",
                description="Return verified official annual reports for securities.",
                input_schema={
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "entity": _entity_schema(),
                        "entities": {"type": "array"},
                        "report_year": {"type": ["integer", "null"]},
                        "report_type": {"type": ["string", "null"]},
                    },
                },
                timeout_ms=int(getattr(settings, "pi_official_report_tool_timeout_ms", 10000)),
            ),
        }

    def get_definition(self, name: str) -> PiToolDefinition | None:
        return self._definitions.get(name)

    def definitions_for(self, allowed_tools: list[str]) -> list[PiToolDefinition]:
        return [tool for name in allowed_tools if (tool := self.get_definition(name))]

    async def execute(
        self,
        call: PiToolCall,
        *,
        trace_id: str,
        context: FinancialSessionContext,
        allowed_tools: set[str],
    ) -> PiToolResponse:
        started = time.perf_counter()
        definition = self.get_definition(call.name)
        if definition is None:
            return self._error(call, trace_id, AGENT_TOOL_NOT_ALLOWED, "Tool is unknown", started)
        if call.name not in allowed_tools:
            return self._error(call, trace_id, AGENT_TOOL_NOT_ALLOWED, "Tool is not allowed for this agent", started)
        if definition.mode != "read_only":
            # Shadow persistence boundary: any non-read-only tool is rejected
            # outright — Pi shadow must never persist business writes.
            return self._error(call, trace_id, PI_SHADOW_WRITE_FORBIDDEN, "Pi shadow write tools are forbidden", started)
        try:
            validate_json_schema(call.arguments, definition.input_schema)
        except ToolSchemaError as exc:
            return self._error(call, trace_id, AGENT_TOOL_ARGUMENT_INVALID, str(exc), started)

        try:
            resp = await asyncio.wait_for(
                self.registry.call(call.name, call.arguments, trace_id=trace_id, context=context),
                timeout=max(0.001, definition.timeout_ms / 1000),
            )
        except asyncio.CancelledError:
            raise
        except asyncio.TimeoutError:
            return self._error(call, trace_id, AGENT_TOOL_TIMEOUT, f"{call.name} timed out", started)

        return self._from_financial_response(resp, fallback_call=call, started=started)

    def _from_financial_response(
        self,
        resp: FinancialToolResponse,
        *,
        fallback_call: PiToolCall,
        started: float,
    ) -> PiToolResponse:
        return PiToolResponse(
            trace_id=resp.trace_id,
            tool_call_id=resp.tool_call_id or fallback_call.id,
            capability=resp.capability or fallback_call.name,
            status=resp.status,
            data=_sanitize_tool_data(resp.data),
            provenance=list(resp.provenance or []),
            freshness=dict(resp.freshness or {}),
            quality=dict(resp.quality or {}),
            warnings=list(resp.warnings or []),
            error_code=resp.error_code,
            error=resp.error,
            latency_ms=resp.latency_ms or int((time.perf_counter() - started) * 1000),
        )

    def _error(
        self,
        call: PiToolCall,
        trace_id: str,
        code: str,
        message: str,
        started: float,
    ) -> PiToolResponse:
        return PiToolResponse(
            trace_id=trace_id,
            tool_call_id=call.id,
            capability=call.name,
            status=STATUS_FAILED,
            error_code=code,
            error={"code": code, "message": message},
            quality={"status": "unavailable"},
            latency_ms=int((time.perf_counter() - started) * 1000),
        )


def _sanitize_tool_data(data: dict[str, Any]) -> dict[str, Any]:
    """Keep model-facing tool data bounded and DTO-like."""

    def clean(value: Any, depth: int = 0) -> Any:
        if depth > 6:
            return "[truncated]"
        if hasattr(value, "to_dict"):
            value = value.to_dict()
        elif hasattr(value, "__dataclass_fields__"):
            value = asdict(value)
        if isinstance(value, dict):
            return {str(k): clean(v, depth + 1) for k, v in value.items()}
        if isinstance(value, list):
            return [clean(item, depth + 1) for item in value[:20]]
        if isinstance(value, str) and len(value) > 4000:
            return value[:4000] + "\n[truncated]"
        return value

    return clean(data or {})
