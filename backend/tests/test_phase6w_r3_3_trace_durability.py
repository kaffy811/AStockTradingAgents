from __future__ import annotations

import asyncio
import json
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.report_analysis_trace_service import (
    ReportAnalysisTraceRecorder,
    numeric_token_contexts,
    redact,
)


class MemoryTraceRepository:
    def __init__(self, fail: bool = False):
        self.fail = fail
        self.header = None
        self.stages = {}
        self.final = None

    async def create_trace(self, payload):
        if self.fail:
            raise RuntimeError("store unavailable")
        self.header = payload

    async def upsert_stage(self, trace_id, stage_name, payload):
        if self.fail:
            raise RuntimeError("store unavailable")
        self.stages[stage_name] = payload

    async def finalize_trace(self, trace_id, payload):
        if self.fail:
            raise RuntimeError("store unavailable")
        self.final = payload


def selection():
    from app.agent.report_context import ReportSelection
    return ReportSelection(
        report_id=17, symbol="600519", market="CN", ts_code="600519.SH",
        stock_name="贵州茅台", report_year=2024, report_type="annual",
        period_end="2024-12-31", title="贵州茅台2024年年度报告",
        disclosure_date="2025-04-02", selection_reason="explicit_report_id",
        parsed=True, rag_status="indexed",
    )


def chunk():
    return {
        "chunk_id": 3670, "report_type": "annual", "report_year": 2024,
        "section_title": "主要会计数据", "page_start": 12, "page_end": 12,
        "content": "2024年营业收入1708.99亿元，同比增长15.38%。", "score": 0.9,
    }


async def run_pipeline(*, llm_answer="营业收入1708.99亿元，同比增长15.38%。", citations=None,
                       selected=True, chunks=None, llm_delay=0, repository=None):
    from app.agent.report_chat_copilot_agent import ReportChatCopilotAgent
    repo = repository or MemoryTraceRepository()
    recorder = ReportAnalysisTraceRecorder(request_id="req-trace-test", repository=repo)
    await recorder.initialize(question="贵州茅台财报如何？", session_id="private-session", market="CN",
                              symbol="600519", report_id=17, years=[2024])
    await recorder.start("S0", {"question": "贵州茅台财报如何？"})
    await recorder.finish("S0", payload={"request_accepted": True})
    rag_chunks = [chunk()] if chunks is None else chunks
    payload = json.dumps({
        "answer": llm_answer, "confidence": "high", "evidence_used": [],
        "data_limitations": [], "disclaimer": "仅供参考",
        "citations": citations if citations is not None else [{"evidence_id": "E1", "claim": "营业收入1708.99亿元"}],
    }, ensure_ascii=False)

    def llm_call(*args, **kwargs):
        if llm_delay:
            time.sleep(llm_delay)
        return payload

    with (
        patch("app.agent.report_chat_cache.read_cache", new_callable=AsyncMock, return_value=None),
        patch("app.agent.report_chat_cache.write_cache", new_callable=AsyncMock),
        patch("app.agent.report_chat_session_memory.load_memory", new_callable=AsyncMock, return_value=[]),
        patch("app.agent.report_chat_session_memory.append_turn", new_callable=AsyncMock),
        patch("app.agent.report_chat_copilot_agent.resolve_report_selection", new_callable=AsyncMock,
              return_value=selection() if selected else None),
        patch("app.agent.report_chat_copilot_agent._cache_get_json", new_callable=AsyncMock, return_value=None),
        patch("app.agent.report_chat_copilot_agent._cache_set_json", new_callable=AsyncMock),
        patch("app.agent.report_chat_copilot_agent._query_indexed_report_db_evidence", new_callable=AsyncMock,
              return_value={"chunks": rag_chunks, "partial": False, "errors": [],
                            "provider": "indexed_report_db", "search_mode": "indexed_db_lexical"}),
        patch("app.llm.deepseek_client.DeepSeekClient") as client,
    ):
        client.return_value.chat = MagicMock(side_effect=llm_call)
        result = await ReportChatCopilotAgent().chat(
            market="CN", symbol="600519", question="贵州茅台财报如何？", db=None,
            report_id=17, years=[2024], force_refresh=True, use_memory=False,
            trace_recorder=recorder,
        )
    await recorder.start("S8", result)
    await recorder.finish("S8", status="rejected" if result.get("status") == "failed" else "completed",
                          error_code=result.get("error_code"), output_data=result)
    await recorder.finalize(result)
    return result, recorder, repo


@pytest.mark.asyncio
async def test_completed_pipeline_persists_s0_through_s8_in_order():
    result, recorder, repo = await run_pipeline()
    assert result["status"] == "completed"
    assert list(repo.stages) == [f"S{i}" for i in range(9)]
    assert all(repo.stages[f"S{i}"]["status"] == "completed" for i in range(9))
    assert repo.final["final_status"] == "completed"
    assert "trace_id" not in result


@pytest.mark.asyncio
async def test_report_selection_failure_preserves_s0_s1_and_s8():
    result, _, repo = await run_pipeline(selected=False)
    assert repo.stages["S1"]["status"] == "failed"
    assert repo.stages["S1"]["error_code"] == "REPORT_SELECTION_FAILED"
    assert set(repo.stages) == {"S0", "S1", "S8"}
    assert result["partial"] is True


@pytest.mark.asyncio
async def test_retrieval_failure_preserves_s2_and_raw_empty_evidence_stages():
    result, _, repo = await run_pipeline(chunks=[])
    assert repo.stages["S2"]["status"] == "completed"
    assert repo.stages["S3"]["payload"]["retrieved_evidence_ids"] == []
    assert repo.stages["S4"]["payload"]["evidence_chars"] == 0
    assert result["error_code"] == "NO_REPORT_EVIDENCE"


@pytest.mark.asyncio
async def test_llm_timeout_leaves_s6_failed(monkeypatch):
    monkeypatch.setattr("app.agent.report_chat_copilot_agent._LLM_SYNTHESIS_TIMEOUT_SECONDS", 0.001)
    result, _, repo = await run_pipeline(llm_delay=0.05)
    assert repo.stages["S6"]["status"] == "failed"
    assert repo.stages["S6"]["error_code"] == "REPORT_LLM_TIMEOUT"
    assert result["status"] == "partial_success"


@pytest.mark.asyncio
async def test_citation_validation_failure_is_persisted_at_s7():
    result, _, repo = await run_pipeline(citations=[{"evidence_id": "E99", "claim": "营业收入"}])
    assert repo.stages["S7"]["status"] == "failed"
    assert repo.stages["S7"]["error_code"] == "CITATION_VALIDATION_FAILED"
    assert "CITATION_VALIDATION_FAILED" in result["errors"]


@pytest.mark.asyncio
async def test_numeric_failure_saves_token_and_complete_sentence():
    answer = "营业收入1708.99亿元。模型另称门店达到99999家，但证据没有该数字。"
    result, _, repo = await run_pipeline(llm_answer=answer)
    contexts = repo.stages["S7"]["payload"]["token_contexts"]
    assert result["numeric_validation"]["valid"] is False
    assert any(item["token"] == "99999" for item in contexts)
    assert any("模型另称门店达到99999家" in item["token_context_sentence"] for item in contexts)
    assert all(item["first_observed_stage"] == "S6" for item in contexts)


@pytest.mark.asyncio
async def test_finalizer_rejection_is_durable():
    repo = MemoryTraceRepository()
    recorder = ReportAnalysisTraceRecorder(request_id="rejected", repository=repo)
    await recorder.initialize(question="q", session_id=None, market="CN", symbol="600519", report_id=17, years=[2024])
    await recorder.start("S8", {"status": "rejected"})
    await recorder.finish("S8", status="rejected", error_code="FINALIZER_REJECTED", output_data={"partial": True})
    await recorder.finalize({"status": "rejected", "partial": True})
    assert repo.stages["S8"]["status"] == "rejected"
    assert repo.final["partial"] is True


@pytest.mark.asyncio
async def test_trace_store_failure_does_not_break_safe_business_result(caplog):
    result, recorder, _ = await run_pipeline(repository=MemoryTraceRepository(fail=True))
    assert "answer" in result
    assert recorder.persistence_failed is True
    assert "trace_id" not in result
    assert "trace persistence failed" in caplog.text


def test_secret_redaction_and_text_bounding():
    cleaned = redact({
        "Authorization": "Bearer super-secret", "cookie": "sid=secret",
        "nested": "postgresql+asyncpg://user:pass@host/db", "answer": "x" * 13000,
    })
    serialized = json.dumps(cleaned)
    assert "super-secret" not in serialized
    assert "sid=secret" not in serialized
    assert "user:pass" not in serialized
    assert len(cleaned["answer"]) == 12000


def test_numeric_context_sentence_keeps_full_sentence():
    contexts = numeric_token_contexts("第一句。营业收入为1708.99亿元，同比增长15.38%。下一句。", ["15.38%"])
    assert contexts == [{
        "token": "15.38%", "token_context_sentence": "营业收入为1708.99亿元，同比增长15.38%。",
        "first_observed_stage": "S6",
    }]
