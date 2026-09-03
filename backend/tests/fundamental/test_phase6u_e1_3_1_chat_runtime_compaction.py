from __future__ import annotations

import json
import uuid
from types import SimpleNamespace

import pytest

import app.agents.chat_memory as chat_memory
from app.services.chat_service import compact_chat_message_metadata


def test_e1_3_1_chat_message_metadata_is_compacted_under_8kb():
    metadata = {
        "skill_name": "report_comparison_skill",
        "status": "partial_success",
        "output_language": "zh-CN",
        "source_chunks": [{"chunk_id": str(i), "text": "x" * 1000} for i in range(20)],
        "diagnostics": {"planner": "y" * 5000},
        "compliance_review": {"audit": "z" * 5000},
        "skill_data": {
            "status": "partial_success",
            "comparison_input": {
                "entities": [
                    {"market": "CN", "symbol": "600519", "name": "贵州茅台", "source_chunks": ["x"]},
                    {"market": "CN", "symbol": "000858", "name": "五粮液", "source_chunks": ["y"]},
                ],
            },
            "comparison_summary": {
                "requested_metric_count": 7,
                "left_available_metric_count": 7,
                "right_available_metric_count": 6,
                "common_metric_count": 6,
            },
        },
    }
    compact = compact_chat_message_metadata(metadata)
    encoded = json.dumps(compact, ensure_ascii=False).encode("utf-8")
    assert len(encoded) < 8 * 1024
    assert "source_chunks" not in compact
    assert "diagnostics" not in compact
    assert compact["entities"][1]["symbol"] == "000858"
    assert compact["comparison_summary"]["common_metric_count"] == 6


@pytest.mark.asyncio
async def test_e1_3_1_memory_updates_commit_once(monkeypatch):
    session = SimpleNamespace(
        session_metadata={
            chat_memory.MEMORY_KEY: {
                "memory_version": "c8_v1",
                "recent_symbols": [],
                "recent_intents": [],
            }
        }
    )
    calls = {"execute": 0, "flush": 0}

    async def _load(db, session_id, user_id):
        return session, dict(session.session_metadata[chat_memory.MEMORY_KEY])

    class _Result:
        rowcount = 1

    class _DB:
        async def execute(self, stmt):
            calls["execute"] += 1
            return _Result()

        async def flush(self):
            calls["flush"] += 1

    monkeypatch.setattr(chat_memory, "_load", _load)
    monkeypatch.setattr(chat_memory, "flag_modified", lambda *args, **kwargs: None)
    await chat_memory.apply_memory_updates(
        _DB(),
        uuid.uuid4(),
        uuid.uuid4(),
        symbols=[{"market": "CN", "symbol": "000858", "name": "五粮液"}],
        intent="report_comparison_skill",
        output_language="zh-CN",
        task_state={"skill_name": "report_comparison_skill"},
    )
    assert calls == {"execute": 1, "flush": 0}


@pytest.mark.asyncio
async def test_e1_3_1_memory_cas_conflict_merges_once(monkeypatch):
    session = SimpleNamespace(
        session_metadata={
            chat_memory.MEMORY_KEY: {
                "memory_version": "c8_v1",
                "recent_symbols": [],
                "recent_intents": [],
            }
        }
    )
    latest_session = SimpleNamespace(session_metadata={chat_memory.MEMORY_KEY: chat_memory._empty_memory()})
    loads = {"count": 0}
    calls = {"execute": 0, "flush": 0}

    async def _load(db, session_id, user_id):
        loads["count"] += 1
        if loads["count"] == 1:
            return session, dict(session.session_metadata[chat_memory.MEMORY_KEY])
        return latest_session, dict(latest_session.session_metadata[chat_memory.MEMORY_KEY])

    class _Result:
        rowcount = 0

    class _DB:
        async def execute(self, stmt):
            calls["execute"] += 1
            return _Result()

        async def flush(self):
            calls["flush"] += 1

    monkeypatch.setattr(chat_memory, "_load", _load)
    monkeypatch.setattr(chat_memory, "flag_modified", lambda *args, **kwargs: None)
    await chat_memory.apply_memory_updates(
        _DB(),
        uuid.uuid4(),
        uuid.uuid4(),
        symbols=[{"market": "CN", "symbol": "600519", "name": "贵州茅台"}],
        intent="report_explanation_skill",
    )
    assert calls == {"execute": 1, "flush": 1}
    memory = latest_session.session_metadata[chat_memory.MEMORY_KEY]
    assert memory["recent_symbols"][0]["symbol"] == "600519"
