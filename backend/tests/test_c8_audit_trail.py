"""
Tests for Phase C8 audit trail — ToolResult audit fields and chat_safety audit builders.

Coverage:
  - ToolResult has duration_ms, started_at, permission_level fields
  - ToolRegistry.call() injects duration_ms and started_at
  - audit_tool_event returns backward-compatible + new fields
  - audit_skill_event returns event_type = skill_completed
  - audit_action_event returns event_type = action_executed
  - _result_tool_event in orchestrator includes ok, permission_level, duration_ms
"""
from __future__ import annotations

import time
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agents.chat_safety import audit_action_event, audit_skill_event, audit_tool_event
from app.agents.chat_tools.tool_result import ToolResult
from app.agents.chat_tools.registry import ToolRegistry


# ── ToolResult audit fields ────────────────────────────────────────────────────

def test_tool_result_defaults():
    r = ToolResult(ok=True, tool_name="stock_quote", summary="ok")
    assert r.duration_ms is None
    assert r.started_at is None
    assert r.permission_level == "read_only"


def test_tool_result_custom_permission():
    r = ToolResult(ok=True, tool_name="watchlist_add", summary="added", permission_level="write_watchlist")
    assert r.permission_level == "write_watchlist"


# ── ToolRegistry.call() injects timing ────────────────────────────────────────

@pytest.mark.asyncio
async def test_registry_call_injects_duration_ms():
    registry = ToolRegistry()

    async def fast_run(**kwargs):
        return ToolResult(ok=True, tool_name="stock_quote", summary="done")

    tool = MagicMock()
    tool.name = "stock_quote"
    tool.run = fast_run
    registry._tools = {"stock_quote": tool}

    db = AsyncMock()
    result = await registry.call("stock_quote", db, symbol="688146")

    assert result.duration_ms is not None
    assert isinstance(result.duration_ms, int)
    assert result.duration_ms >= 0


@pytest.mark.asyncio
async def test_registry_call_injects_started_at():
    registry = ToolRegistry()

    async def fast_run(**kwargs):
        return ToolResult(ok=True, tool_name="stock_quote", summary="done")

    tool = MagicMock()
    tool.name = "stock_quote"
    tool.run = fast_run
    registry._tools = {"stock_quote": tool}

    db = AsyncMock()
    result = await registry.call("stock_quote", db)

    assert result.started_at is not None
    # should be an ISO 8601 string
    assert "T" in result.started_at


@pytest.mark.asyncio
async def test_registry_call_unknown_tool_returns_error():
    registry = ToolRegistry()
    registry._tools = {}
    db = AsyncMock()
    result = await registry.call("nonexistent_tool", db)
    assert result.ok is False
    assert "nonexistent_tool" in (result.error or "")


# ── audit_tool_event ───────────────────────────────────────────────────────────

def test_audit_tool_event_backward_compat():
    event = audit_tool_event("stock_quote", "success", "Quote fetched")
    # backward-compatible fields for ChatToolTrace
    assert event["name"] == "stock_quote"
    assert event["status"] == "success"
    assert event["detail"] == "Quote fetched"


def test_audit_tool_event_c8_fields():
    event = audit_tool_event(
        "stock_quote", "success", "Quote fetched",
        permission_level="read_only",
        duration_ms=42,
        started_at="2026-06-18T10:00:00+00:00",
        ok=True,
    )
    assert event["event_type"] == "tool_completed"
    assert event["permission_level"] == "read_only"
    assert event["ok"] is True
    assert event["duration_ms"] == 42
    assert event["started_at"] == "2026-06-18T10:00:00+00:00"


def test_audit_tool_event_error_field():
    event = audit_tool_event("stock_quote", "error", "Fetch failed", ok=False, error="HTTP 503")
    assert event["ok"] is False
    assert event["error"] == "HTTP 503"


def test_audit_tool_event_optional_fields_omitted_when_none():
    event = audit_tool_event("stock_quote", "success", "ok")
    assert "duration_ms" not in event
    assert "started_at" not in event
    assert "completed_at" not in event
    assert "error" not in event


# ── audit_skill_event ──────────────────────────────────────────────────────────

def test_audit_skill_event_structure():
    event = audit_skill_event("anomaly_skill", status="success", required_tools=["stock_quote"])
    assert event["event_type"] == "skill_completed"
    assert event["skill_name"] == "anomaly_skill"
    assert event["status"] == "success"
    assert "stock_quote" in event["required_tools"]


def test_audit_skill_event_empty_tools():
    event = audit_skill_event("anomaly_skill")
    assert event["required_tools"] == []


# ── audit_action_event ─────────────────────────────────────────────────────────

def test_audit_action_event_structure():
    event = audit_action_event(
        action_type="add_watchlist",
        confirmation_id="conf-abc",
        status="executed",
        ok=True,
    )
    assert event["event_type"] == "action_executed"
    assert event["action_type"] == "add_watchlist"
    assert event["confirmation_id"] == "conf-abc"
    assert event["status"] == "executed"
    assert event["ok"] is True
    assert event["error"] is None


def test_audit_action_event_failed():
    event = audit_action_event(
        action_type="add_watchlist",
        confirmation_id="conf-xyz",
        status="failed",
        ok=False,
        error="Not found",
    )
    assert event["ok"] is False
    assert event["error"] == "Not found"
