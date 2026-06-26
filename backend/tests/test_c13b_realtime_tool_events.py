"""
C13-b: Real-time Tool Event Tests.

Tests for safe_emit() helper and ToolRegistry.call() with event_callback:
1. safe_emit with no callback is a no-op
2. safe_emit calls callback with correct args
3. safe_emit swallows exceptions from callback
4. ToolRegistry.call() emits tool_started before tool runs
5. ToolRegistry.call() emits tool_completed on success
6. ToolRegistry.call() emits tool_completed on exception
7. ToolRegistry.call() without event_callback still returns ToolResult
8. tool_completed payload has required fields: tool_name, status, ok, duration_ms
9. tool_started payload has required fields: tool_name, permission_level, source
10. Unknown tool name still emits tool_completed with ok=False
"""
from __future__ import annotations

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock


# ── 1. safe_emit tests ────────────────────────────────────────────────────────

class TestSafeEmit:

    @pytest.mark.asyncio
    async def test_no_callback_is_noop(self):
        """safe_emit with None callback must not raise."""
        from app.agents.chat_events import safe_emit
        # Should not raise
        await safe_emit(None, "tool_started", {"tool_name": "x"})

    @pytest.mark.asyncio
    async def test_calls_callback_with_correct_args(self):
        """safe_emit calls callback(event_type, payload)."""
        from app.agents.chat_events import safe_emit

        received = []

        async def cb(event_type, payload):
            received.append((event_type, payload))

        await safe_emit(cb, "tool_started", {"tool_name": "test_tool"})
        assert len(received) == 1
        assert received[0][0] == "tool_started"
        assert received[0][1]["tool_name"] == "test_tool"

    @pytest.mark.asyncio
    async def test_swallows_callback_exceptions(self):
        """safe_emit must not propagate callback exceptions."""
        from app.agents.chat_events import safe_emit

        async def bad_cb(event_type, payload):
            raise RuntimeError("callback crashed")

        # Must not raise
        await safe_emit(bad_cb, "tool_started", {"tool_name": "x"})

    @pytest.mark.asyncio
    async def test_empty_payload_defaults_to_dict(self):
        """safe_emit with no payload sends empty dict."""
        from app.agents.chat_events import safe_emit

        received = []

        async def cb(event_type, payload):
            received.append((event_type, payload))

        await safe_emit(cb, "skill_started")
        assert received[0][1] == {}

    @pytest.mark.asyncio
    async def test_callback_receives_full_payload(self):
        """Payload dict is passed through unmodified."""
        from app.agents.chat_events import safe_emit

        received_payload = {}

        async def cb(event_type, payload):
            received_payload.update(payload)

        data = {"tool_name": "get_quote_tool", "source": "tool_registry", "permission_level": "read_only"}
        await safe_emit(cb, "tool_started", data)
        assert received_payload == data


# ── 2. ToolRegistry event_callback integration ────────────────────────────────

class TestToolRegistryEventCallback:

    def _make_registry_with_mock_tool(self, tool_name="mock_tool", raise_exc=False):
        from app.agents.chat_tools.registry import ToolRegistry
        from app.agents.chat_tools.tool_result import ToolResult

        registry = ToolRegistry()

        mock_tool = MagicMock()
        mock_tool.name = tool_name
        mock_tool.permission_level = "read_only"

        if raise_exc:
            mock_tool.run = AsyncMock(side_effect=RuntimeError("boom"))
        else:
            mock_result = ToolResult(ok=True, tool_name=tool_name, summary="OK")
            mock_tool.run = AsyncMock(return_value=mock_result)

        registry.register(mock_tool)
        return registry

    @pytest.mark.asyncio
    async def test_emits_tool_started_before_run(self):
        """tool_started must be emitted before tool.run() is called."""
        registry = self._make_registry_with_mock_tool()

        emitted_order = []
        run_order = []

        original_run = registry._tools["mock_tool"].run

        async def tracked_run(**kwargs):
            run_order.append("run")
            return await original_run(**kwargs)

        registry._tools["mock_tool"].run = tracked_run

        async def cb(event_type, payload):
            emitted_order.append(event_type)

        db = AsyncMock()
        await registry.call("mock_tool", db, event_callback=cb)

        assert emitted_order[0] == "tool_started", f"First event was {emitted_order[0]}"

    @pytest.mark.asyncio
    async def test_emits_tool_completed_on_success(self):
        """tool_completed must be emitted after successful tool run."""
        registry = self._make_registry_with_mock_tool()

        events = []

        async def cb(event_type, payload):
            events.append((event_type, payload))

        db = AsyncMock()
        await registry.call("mock_tool", db, event_callback=cb)

        types = [e[0] for e in events]
        assert "tool_completed" in types
        completed = next(e[1] for e in events if e[0] == "tool_completed")
        assert completed["ok"] is True
        assert completed["status"] == "success"

    @pytest.mark.asyncio
    async def test_emits_tool_completed_on_exception(self):
        """tool_completed with ok=False must be emitted when tool raises."""
        registry = self._make_registry_with_mock_tool(raise_exc=True)

        events = []

        async def cb(event_type, payload):
            events.append((event_type, payload))

        db = AsyncMock()
        result = await registry.call("mock_tool", db, event_callback=cb)

        assert result.ok is False
        types = [e[0] for e in events]
        assert "tool_completed" in types
        completed = next(e[1] for e in events if e[0] == "tool_completed")
        assert completed["ok"] is False
        assert completed["status"] == "failed"

    @pytest.mark.asyncio
    async def test_no_event_callback_returns_tool_result(self):
        """Registry without event_callback still returns valid ToolResult."""
        registry = self._make_registry_with_mock_tool()

        db = AsyncMock()
        result = await registry.call("mock_tool", db)
        assert result.ok is True
        assert result.tool_name == "mock_tool"

    @pytest.mark.asyncio
    async def test_tool_completed_has_required_fields(self):
        """tool_completed payload must have tool_name, status, ok, duration_ms."""
        registry = self._make_registry_with_mock_tool()

        events = []

        async def cb(event_type, payload):
            events.append((event_type, payload))

        db = AsyncMock()
        await registry.call("mock_tool", db, event_callback=cb)

        completed = next(e[1] for e in events if e[0] == "tool_completed")
        for field in ("tool_name", "status", "ok", "duration_ms"):
            assert field in completed, f"Missing field: {field}"

    @pytest.mark.asyncio
    async def test_tool_started_has_required_fields(self):
        """tool_started payload must have tool_name, permission_level, source."""
        registry = self._make_registry_with_mock_tool()

        events = []

        async def cb(event_type, payload):
            events.append((event_type, payload))

        db = AsyncMock()
        await registry.call("mock_tool", db, event_callback=cb)

        started = next(e[1] for e in events if e[0] == "tool_started")
        for field in ("tool_name", "permission_level", "source"):
            assert field in started, f"Missing field: {field}"

    @pytest.mark.asyncio
    async def test_unknown_tool_emits_tool_completed_with_ok_false(self):
        """Unknown tool name: emits tool_completed(ok=False), returns ToolResult(ok=False)."""
        from app.agents.chat_tools.registry import ToolRegistry

        registry = ToolRegistry()
        events = []

        async def cb(event_type, payload):
            events.append((event_type, payload))

        db = AsyncMock()
        result = await registry.call("nonexistent_tool", db, event_callback=cb)

        assert result.ok is False
        types = [e[0] for e in events]
        assert "tool_completed" in types
        completed = next(e[1] for e in events if e[0] == "tool_completed")
        assert completed["ok"] is False

    @pytest.mark.asyncio
    async def test_event_callback_failure_does_not_crash_registry(self):
        """If event_callback raises, registry must still return ToolResult."""
        registry = self._make_registry_with_mock_tool()

        async def bad_cb(event_type, payload):
            raise RuntimeError("callback exploded")

        db = AsyncMock()
        result = await registry.call("mock_tool", db, event_callback=bad_cb)
        assert result.ok is True

    @pytest.mark.asyncio
    async def test_tool_name_in_completed_matches_called_tool(self):
        """tool_completed.tool_name matches the tool name passed to call()."""
        registry = self._make_registry_with_mock_tool(tool_name="get_quote_tool")

        events = []

        async def cb(event_type, payload):
            events.append((event_type, payload))

        db = AsyncMock()
        await registry.call("get_quote_tool", db, event_callback=cb)

        completed = next(e[1] for e in events if e[0] == "tool_completed")
        assert completed["tool_name"] == "get_quote_tool"
