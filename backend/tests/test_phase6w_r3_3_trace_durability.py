from __future__ import annotations

import asyncio
import json
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.report_analysis_trace_service import (
    ReportAnalysisTraceRecorder,
    compaction_evidence_snapshot,
    numeric_token_contexts,
    numeric_token_provenance,
    redact,
    structured_financial_snapshot,
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
        if stage_name in self.stages and not payload.get("input_payload"):
            payload = {**payload, "input_payload": self.stages[stage_name].get("input_payload") or {}}
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
                       selected=True, chunks=None, llm_delay=0, repository=None,
                       structured_result=None, question="贵州茅台财报如何？"):
    from app.agent.report_chat_copilot_agent import ReportChatCopilotAgent
    repo = repository or MemoryTraceRepository()
    recorder = ReportAnalysisTraceRecorder(request_id="req-trace-test", repository=repo)
    await recorder.initialize(question=question, session_id="private-session", market="CN",
                              symbol="600519", report_id=17, years=[2024])
    await recorder.start("S0", {"question": question})
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
        patch("app.services.report_financial_table_extractor_tool.report_financial_table_extractor_tool.extract_from_chunks",
              return_value=structured_result or {"fields": {}, "field_count": 0, "cache_key": "report_financial_fields:17:v1"}),
        patch("app.llm.deepseek_client.DeepSeekClient") as client,
    ):
        client.return_value.chat = MagicMock(side_effect=llm_call)
        result = await ReportChatCopilotAgent().chat(
            market="CN", symbol="600519", question=question, db=None,
            report_id=17, years=[2024], force_refresh=True, use_memory=False,
            trace_recorder=recorder,
        )
    await recorder.start("S8", result)
    await recorder.finish("S8", status="rejected" if result.get("status") == "failed" else "completed",
                          error_code=result.get("error_code"), output_data=result)
    await recorder.finalize(result)
    return result, recorder, repo


@pytest.mark.asyncio
async def test_derived_fact_provenance_is_visible_in_s5_and_s7():
    financial_chunk = {
        "chunk_id": 3670, "report_type": "annual", "report_year": 2024,
        "section_title": "主要会计数据", "page_start": 12, "page_end": 12,
        "content": (
            "2024年 2023年 营业收入 170,899,152,276.34 147,693,604,994.14；"
            "归属于上市公司股东的净利润 86,228,146,421.62 74,734,071,550.75。"
        ), "score": 0.9,
    }
    result, _, repo = await run_pipeline(
        question="2024年贵州茅台净利率如何？",
        chunks=[financial_chunk],
        llm_answer="按年报披露数据计算，2024年净利率为50.46%。",
        citations=[{"derived_fact_id": "C1", "evidence_ids": ["E1"], "claim": "2024年净利率为50.46%"}],
    )
    s5_facts = repo.stages["S5"]["payload"]["derived_facts"]
    s7 = repo.stages["S7"]["payload"]
    assert result["numeric_validation"]["valid"] is True
    assert s5_facts[0]["operands"]
    assert s5_facts[0]["canonical_result"]
    assert s7["derived_fact_used_ids"] == ["C1"]
    assert s7["derived_fact_citation_ids"] == ["C1"]
    assert s7["derived_fact_label_leak"] is False


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
        "contact": "alice@example.com 13800138000",
    })
    serialized = json.dumps(cleaned)
    assert "super-secret" not in serialized
    assert "sid=secret" not in serialized
    assert "user:pass" not in serialized
    assert "alice@example.com" not in serialized
    assert "13800138000" not in serialized
    assert len(cleaned["answer"]) == 12000


def test_numeric_context_sentence_keeps_full_sentence():
    contexts = numeric_token_contexts("第一句。营业收入为1708.99亿元，同比增长15.38%。下一句。", ["15.38%"])
    assert contexts == [{
        "token": "15.38%", "token_context_sentence": "营业收入为1708.99亿元，同比增长15.38%。",
        "first_observed_stage": "S6",
    }]


def test_compactor_inventory_records_kept_and_removed_tokens():
    from app.agent.report_chat_copilot_agent import financial_evidence_compactor
    pre = [{
        "chunk_id": 1,
        "content": "营业收入1708.99亿元。" + ("普通说明文字" * 200) + "期末补充数字99999元。",
    }]
    post = financial_evidence_compactor(pre, max_chars_per_chunk=80, max_total_chars=80)
    audit = compaction_evidence_snapshot(pre, post)
    assert "1708.99" in audit["pre_compaction_numeric_inventory"]
    assert audit["pre_compaction_evidence_hash"] != audit["post_compaction_evidence_hash"]
    assert "99999" in audit["removed_numeric_tokens"]
    assert any("99999" in ref["removed_tokens"] for ref in audit["removed_sentence_refs"])


def test_structured_snapshot_persists_public_field_provenance_and_cache_freshness():
    data = {
        "cache_key": "report_financial_fields:17:v1",
        "fields": {"revenue": {
            "raw_value": "170,899,152,276.34", "normalized_value": 170899152276.34,
            "unit": "元", "period_end": "2024-12-31", "source_chunk_id": 82,
            "source_document_id": 1,
        }},
    }
    current = structured_financial_snapshot(
        data, report_id=17, report_year=2024, source="regex_table_text",
        as_of="2025-04-02", cache_status="hit", expected_cache_version="v1",
        evidence_hash="evidence-hash",
    )
    stale = structured_financial_snapshot(
        data, report_id=17, report_year=2024, source="regex_table_text",
        as_of="2025-04-02", cache_status="hit", expected_cache_version="v2",
        evidence_hash="evidence-hash",
    )
    miss = structured_financial_snapshot(
        data, report_id=17, report_year=2024, source="regex_table_text",
        as_of="2025-04-02", cache_status="written", expected_cache_version="v1",
        evidence_hash="evidence-hash",
    )
    assert current["structured_fields_present"] is True
    assert current["freshness"] == "current"
    assert stale["freshness"] == "stale_version"
    assert miss["freshness"] == "fresh"
    assert current["fields"][0]["linked_evidence_ids"] == [82, 1]
    assert current["structured_data_hash"]


@pytest.mark.asyncio
async def test_stage_input_payload_survives_finish_for_structured_snapshot():
    repo = MemoryTraceRepository()
    recorder = ReportAnalysisTraceRecorder(request_id="input-retained", repository=repo)
    await recorder.start("S6", {"structured_financial_fields_snapshot": {"schema_version": "v1"}})
    await recorder.finish("S6", payload={"raw_output_absent": True})
    assert repo.stages["S6"]["input_payload"]["structured_financial_fields_snapshot"]["schema_version"] == "v1"
    assert repo.stages["S6"]["payload"]["raw_output_absent"] is True


@pytest.mark.asyncio
async def test_structured_financial_fields_snapshot_is_persisted_end_to_end():
    structured = {
        "cache_key": "report_financial_fields:17:v1", "extraction_method": "regex_table_text",
        "field_count": 1,
        "fields": {"revenue": {
            "raw_value": "1708.99", "normalized_value": 170899000000.0, "unit": "亿元",
            "period_end": "2024-12-31", "source_chunk_id": 3670, "source_document_id": 17,
        }},
    }
    result, _, repo = await run_pipeline(structured_result=structured)
    snapshot = repo.stages["S5"]["payload"]["structured_financial_fields_snapshot"]
    assert snapshot["structured_fields_present"] is True
    assert snapshot["report_id"] == 17
    assert snapshot["report_year"] == 2024
    assert snapshot["fields"][0] == {
        "field_path": "revenue", "raw_value": "1708.99", "canonical_value": 170899000000.0,
        "unit": "亿元", "period": "2024-12-31", "linked_evidence_ids": [3670, 17],
    }
    assert repo.stages["S6"]["input_payload"]["structured_financial_fields_snapshot"] == snapshot
    assert "structured_financial_fields_snapshot" not in result


@pytest.mark.asyncio
async def test_s1_metadata_tokens_and_s6_timeout_context_are_durable(monkeypatch):
    monkeypatch.setattr("app.agent.report_chat_copilot_agent._LLM_SYNTHESIS_TIMEOUT_SECONDS", 0.001)
    result, _, repo = await run_pipeline(llm_delay=0.05)
    s1 = repo.stages["S1"]["payload"]
    assert s1["selected_period"] == "2024-12-31"
    assert s1["disclosure_date"] == "2025-04-02"
    assert "2024" in s1["report_context_numeric_date_tokens"]
    s6 = repo.stages["S6"]
    assert s6["status"] == "failed"
    assert s6["payload"]["provider_error_category"] == "timeout"
    assert s6["payload"]["timeout_layer"] == "llm_synthesis"
    assert s6["payload"]["raw_output_absent"] is True
    assert s6["payload"]["duration_ms"] is not None
    assert result["status"] == "partial_success"


def test_numeric_provenance_has_exact_source_hit_matrix_without_substring_collision():
    contexts = numeric_token_provenance(
        "已接入6条证据。", ["6"],
        {"S1": {"report_id": 600519}, "S4": "", "S5": "", "structured_facts": {}, "S6": "已接入6条证据。"},
    )
    assert contexts[0]["first_observed_stage"] == "S6"
    assert contexts[0]["source_hits"] == {
        "S1": False, "S4": False, "S5": False, "structured_facts": False, "S6": True,
    }
