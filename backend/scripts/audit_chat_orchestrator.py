#!/usr/bin/env python3
"""
C15 Audit: Chat Orchestrator Full Chain Verification.

Usage: uv run python scripts/audit_chat_orchestrator.py --message "贵州茅台最新财报表现如何？"

Runs process_message() with a mock DB and traces every routing decision.
"""
from __future__ import annotations

import argparse
import asyncio
import sys
import uuid

sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent.parent))


async def audit_orchestrator(message: str) -> None:
    print(f"[C15_AUDIT] message: {message!r}")

    from unittest.mock import AsyncMock, MagicMock, patch
    from app.agents.chat_tools.tool_result import ToolResult

    user_id = uuid.UUID("00000000-0000-0000-0000-000000000099")
    mock_db = AsyncMock()

    # Default tool response: ok=False (no real DB)
    async def fake_tool_call(tool_name, db, **kwargs):
        print(f"[C15_AUDIT]   tool_called: {tool_name}")
        return ToolResult(
            ok=False,
            tool_name=tool_name,
            summary=f"{tool_name}: mock no-DB",
            data={"items": [], "count": 0, "market": "CN", "symbol": "600519"},
        )

    events_emitted: list[str] = []

    async def event_callback(event_type: str, payload: dict) -> None:
        events_emitted.append(event_type)
        print(f"[C15_AUDIT]   event: {event_type}")

    with patch("app.agents.chat_orchestrator._registry.call", side_effect=fake_tool_call):
        try:
            from app.agents.chat_orchestrator import process_message
            result = await process_message(
                content=message,
                db=mock_db,
                user_id=user_id,
                output_language="zh-CN",
                session_id=uuid.uuid4(),
                event_callback=event_callback,
            )
        except Exception as e:
            print(f"[C15_AUDIT] process_message ERROR: {type(e).__name__}: {e}")
            return

    meta = result.metadata or {}
    answer_len = len(result.answer or "")
    print(f"[C15_AUDIT] --- RESULT ---")
    print(f"[C15_AUDIT] safety_rejected: {meta.get('intent') == 'safety_blocked'}")
    print(f"[C15_AUDIT] action_intent: {meta.get('intent') if 'confirmation' in str(result.confirmation) else 'none'}")
    print(f"[C15_AUDIT] planner_used: {meta.get('planner_used', False)}")
    print(f"[C15_AUDIT] selected_skill: {meta.get('skill_name') or meta.get('handler') or 'none'}")
    print(f"[C15_AUDIT] source: {meta.get('source', 'unknown')}")
    print(f"[C15_AUDIT] answer_length: {answer_len}")
    print(f"[C15_AUDIT] answer_preview: {(result.answer or '')[:120]!r}")
    print(f"[C15_AUDIT] cards_count: {len(result.cards or [])}")
    print(f"[C15_AUDIT] confirmation_required: {result.confirmation is not None}")
    print(f"[C15_AUDIT] events_emitted: {events_emitted}")
    print(f"[C15_AUDIT] tool_events_count: {len(result.tool_events or [])}")

    if not result.answer or not result.answer.strip():
        print("[C15_AUDIT] WARNING: answer is EMPTY")
    elif "你好！我是 TradingAgents Chat Copilot" in result.answer:
        print("[C15_AUDIT] WARNING: answer is DEFAULT GREETING — no real research was performed")
    elif "内部错误" in result.answer or "受限" in result.answer:
        print("[C15_AUDIT] WARNING: answer contains error message — skill or LLM failed")
    else:
        print("[C15_AUDIT] OK: answer appears to be a research response")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--message", default="贵州茅台最新财报表现如何？")
    args = parser.parse_args()
    asyncio.run(audit_orchestrator(args.message))


if __name__ == "__main__":
    main()
