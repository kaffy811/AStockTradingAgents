#!/usr/bin/env python3
"""
C15 Audit: RAG Pipeline Verification.

Usage: uv run python scripts/audit_rag_pipeline.py --query "贵州茅台最新财报表现如何？"

Tests RAG retrieval without a real DB session.
"""
from __future__ import annotations

import argparse
import asyncio
import sys

sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent.parent))


async def audit_rag(query: str) -> None:
    print(f"[C15_AUDIT] query: {query!r}")

    # Extract stock hint
    try:
        from app.agents.chat_rag.retriever import _extract_hint
        hint = _extract_hint(query)
        print(f"[C15_AUDIT] stock_resolved: {bool(hint)}")
        if hint:
            print(f"[C15_AUDIT] resolved_symbol: {hint.get('market')}/{hint.get('symbol')} ({hint.get('name')})")
        else:
            print("[C15_AUDIT] resolved_symbol: none — query contains no recognizable stock code or name")
    except Exception as e:
        print(f"[C15_AUDIT] hint_extract_error: {e}")
        hint = None

    # Test ToolRegistry mock to count what tools RAG would call
    from unittest.mock import AsyncMock, MagicMock
    from app.agents.chat_tools.tool_result import ToolResult
    from app.agents.chat_skills.base import SkillContext

    mock_tr = MagicMock()
    called_tools: list[str] = []

    async def fake_call(tool_name, db, **kwargs):
        called_tools.append(tool_name)
        print(f"[C15_AUDIT]   rag_tool_called: {tool_name} kwargs={list(kwargs.keys())}")
        return ToolResult(
            ok=False,
            tool_name=tool_name,
            summary="mock — no DB",
            data={"items": [], "count": 0},
        )

    mock_tr.call = fake_call

    ctx = SkillContext(
        db=MagicMock(),
        user_id="audit-user-000",
        output_language="zh-CN",
        tool_registry=mock_tr,
        event_callback=None,
    )

    # Run RAG retriever
    try:
        from app.agents.chat_rag.retriever import retrieve_context
        rag_result = await retrieve_context(query, ctx)
        print(f"[C15_AUDIT] rag_ok: {rag_result.ok}")
        print(f"[C15_AUDIT] rag_tools_called: {called_tools}")
        print(f"[C15_AUDIT] documents_count: {len(rag_result.documents)}")
        if rag_result.documents:
            source_types = [d.source_type for d in rag_result.documents]
            print(f"[C15_AUDIT] source_types: {source_types}")
        else:
            print("[C15_AUDIT] source_types: [] (no documents retrieved — DB/API returned empty)")
        if rag_result.error:
            print(f"[C15_AUDIT] rag_error: {rag_result.error}")
    except Exception as e:
        print(f"[C15_AUDIT] rag_retriever_error: {type(e).__name__}: {e}")
        return

    # Run RAG Review
    try:
        from app.agents.chat_rag import RAGReviewCoordinator
        coordinator = RAGReviewCoordinator()
        coordinator.review(rag_result)
        # Check if review_result or confidence was set
        conf = getattr(rag_result, "overall_confidence", None)
        approved = getattr(rag_result, "approved", None)
        reviewed = getattr(rag_result, "reviewed", None)
        print(f"[C15_AUDIT] review_executed: {reviewed}")
        print(f"[C15_AUDIT] review_confidence: {conf}")
        print(f"[C15_AUDIT] review_approved: {approved}")
        fmt = coordinator.format_for_answer(rag_result)
        print(f"[C15_AUDIT] review_format_chars: {len(fmt)}")
    except Exception as e:
        print(f"[C15_AUDIT] review_error: {type(e).__name__}: {e}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--query", default="贵州茅台最新财报表现如何？")
    args = parser.parse_args()
    asyncio.run(audit_rag(args.query))


if __name__ == "__main__":
    main()
